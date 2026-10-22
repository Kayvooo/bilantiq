"""Passwort vergessen: Link per E-Mail, Einmal-Token, danach neues Passwort.

Entwurfsentscheidungen:

- Keine Konto-Enumeration: ``POST /auth/passwort/vergessen`` antwortet immer gleich (202 mit festem Text), egal ob die
  Adresse registriert, das Konto geloescht oder der Versand moeglich ist. Die Antwortzeit wird auf eine Mindestdauer
  aufgefuellt, und die Mail geht erst NACH der Antwort raus (Hintergrundaufgabe), sonst verraet die SMTP-Laufzeit, ob es
  das Konto gibt. Das IP- und das Konto-Limit (``app/core/ratelimit.py``) gelten fuer bekannte und unbekannte Adressen
  gleichermassen; das Konto-Limit schuetzt ein fremdes Postfach vor Mail-Flut.
- Token: 256 Bit Zufall (``secrets.token_hex(32)``), in der Datenbank nur als HMAC-SHA256 (``blind_index``), einmalig
  verwendbar, 60 Minuten gueltig; eine neue Anforderung entwertet alle aelteren Tokens des Kontos. Im Link steht
  zusaetzlich die Nutzer-ID (``<nutzer-id>.<token>``): Sie ist kein Geheimnis (steht in jedem JWT) und erlaubt, den Mandanten
  fuer die RLS ueber ``bq_mandant_des_nutzers`` (Migration 0035) zu finden, bevor eine RLS-geschuetzte Tabelle gelesen wird.
- Nach dem Zuruecksetzen: alle Sitzungen und Pre-MFA-Tokens werden entwertet (``invalidate_security_context``), eine
  ausstehende MFA-Neueinrichtung verworfen. MFA bleibt AKTIV; wer sie eingerichtet hat, braucht beim Anmelden weiter einen
  Code oder Wiederherstellungscode. Das Zuruecksetzen per E-Mail umgeht den zweiten Faktor bewusst nicht. Eine bestehende
  Kontosperre (Fehlversuche) bleibt bestehen, damit der Reset kein Weg ist, den Zaehler zurueckzusetzen.
- Die Routen (``/auth/passwort/vergessen``, ``/auth/passwort/zuruecksetzen``) werden in ``app/auth/routes.py`` am
  Auth-Router registriert, die Logik steht hier.
- Der Link nutzt das URL-Fragment (``#passwort-zuruecksetzen/...``): Fragmente werden nie an den Server gesendet, landen
  also weder im Zugriffslog von Caddy/API noch in Referer-Headern.
"""
from __future__ import annotations

import hmac
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.models import PasswortResetToken, User
from app.auth.schemas import PasswortVergessenRequest, PasswortVergessenResponse, PasswortZuruecksetzenRequest
from app.auth.security_service import invalidate_security_context
from app.config import settings
from app.core import mailer, ratelimit
from app.core.audit_log import record as record_audit
from app.core.crypto import decrypt_field, lookup_hash
from app.core.key_management import blind_index
from app.core.rls_lookup import mandant_des_nutzers
from app.core.security import hash_password
from app.db import get_db, set_rls_mandant

logger = logging.getLogger("bilantiq.passwort_reset")

GUELTIGKEIT_MINUTEN = 60
VERGESSEN_PRO_IP = (10, 3600)
VERGESSEN_PRO_KONTO = (3, 3600)
ZURUECKSETZEN_PRO_IP = (20, 900)
# Mindestdauer der Antwort auf /vergessen (Sekunden), gleicht bekannte und unbekannte Adressen zeitlich an.
MIN_ANTWORTZEIT_SEKUNDEN = 0.4

ANTWORT_TEXT = "Wenn zu dieser E-Mail-Adresse ein Konto existiert, haben wir einen Link zum Zurücksetzen des Passworts gesendet."
UNGUELTIGER_LINK = "Der Link ist ungültig oder abgelaufen. Bitte fordere einen neuen an."

_TOKEN_FORMAT = re.compile(r"^([0-9a-fA-F-]{36})\.([0-9a-f]{64})$")


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _aware(wert: datetime) -> datetime:
    return wert if wert.tzinfo is not None else wert.replace(tzinfo=timezone.utc)


def _token_hash(geheimnis: str) -> str:
    return blind_index(geheimnis, purpose="passwort-reset")


def _auffuellen(start: float) -> None:
    rest = MIN_ANTWORTZEIT_SEKUNDEN - (time.monotonic() - start)
    if rest > 0:
        time.sleep(rest)


def _sende_hintergrund(empfaenger: str, betreff: str, text: str) -> None:
    try:
        mailer.sende_text_email(empfaenger, betreff, text)
    except Exception as exc:  # noqa: BLE001 - der Fehler darf weder die Antwort noch den Zustand veraendern
        # Kein Link/Token und keine Adresse im Log, nur die Fehlerart.
        logger.error("E-Mail zur Passwort-Rücksetzung konnte nicht versendet werden (%s).", type(exc).__name__)


def _reset_text(link: str) -> str:
    return (
        "Hallo,\n\n"
        "für dein Bilantiq-Konto wurde das Zurücksetzen des Passworts angefordert. Über diesen Link kannst du ein neues "
        f"Passwort festlegen:\n\n{link}\n\n"
        f"Der Link ist {GUELTIGKEIT_MINUTEN} Minuten gültig und kann nur einmal verwendet werden. Wenn du das nicht "
        "angefordert hast, kannst du diese Nachricht ignorieren, dein Passwort bleibt dann unverändert.\n\n"
        "Hast du die Zwei-Faktor-Anmeldung eingerichtet, bleibt sie auch nach dem Zurücksetzen aktiv."
    )


_GEAENDERT_TEXT = (
    "Hallo,\n\n"
    "das Passwort deines Bilantiq-Kontos wurde soeben über den Link „Passwort vergessen“ geändert. Alle angemeldeten Geräte "
    "wurden abgemeldet.\n\n"
    "Warst du das nicht, ist möglicherweise dein Postfach in fremder Hand: Fordere sofort ein neues Passwort an, sichere "
    "dein Postfach und melde dich beim Bilantiq-Support."
)


def passwort_vergessen(
    payload: PasswortVergessenRequest,
    request: Request,
    hintergrund: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PasswortVergessenResponse:
    start = time.monotonic()
    # Ohne SMTP gibt es keinen Reset-Weg per E-Mail. Die Antwort ist fuer ALLE Adressen gleich (keine Konto-Enumeration)
    # und sagt ehrlich, dass E-Mail fehlt, statt eine Mail vorzutaeuschen. Weg fuer Betreiber: docs/self-hosting.md.
    if not settings.email_aktiv:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Passwort zurücksetzen per E-Mail ist auf dieser Instanz nicht möglich, weil kein E-Mail-Versand "
                "eingerichtet ist. Die Betreiberin oder der Betreiber kann das Passwort auf dem Server zurücksetzen "
                "(docs/self-hosting.md, Abschnitt Konto wiederherstellen)."
            ),
        )
    ratelimit.begrenze_ip(request, "passwort-vergessen", limit=VERGESSEN_PRO_IP[0], fenster_sekunden=VERGESSEN_PRO_IP[1])
    schluessel = lookup_hash(str(payload.email))
    ratelimit.begrenze(f"passwort-vergessen:konto:{schluessel}", limit=VERGESSEN_PRO_KONTO[0], fenster_sekunden=VERGESSEN_PRO_KONTO[1])

    user = db.query(User).filter(User.email_lookup_hash == schluessel).first()
    mandant_id = mandant_des_nutzers(db, user.id) if user is not None and user.geloescht_am is None else None
    if user is not None and mandant_id is not None:
        if not settings.app_frontend_url:
            logger.error("APP_FRONTEND_URL ist nicht gesetzt: Es kann keine Passwort-Reset-Mail erzeugt werden.")
        else:
            set_rls_mandant(db, mandant_id)
            geheimnis = secrets.token_hex(32)  # 256 Bit
            jetzt = _jetzt()
            db.query(PasswortResetToken).filter(PasswortResetToken.user_id == user.id).delete(synchronize_session=False)
            db.add(PasswortResetToken(
                user_id=user.id, mandant_id=mandant_id, token_hash=_token_hash(geheimnis),
                erstellt_am=jetzt, ablauf_am=jetzt + timedelta(minutes=GUELTIGKEIT_MINUTEN),
            ))
            record_audit(db, aktion="passwort_reset_angefordert", mandant_id=mandant_id, user_id=user.id)
            db.commit()
            link = f"{settings.app_frontend_url.strip().rstrip('/')}/#passwort-zuruecksetzen/{user.id}.{geheimnis}"
            hintergrund.add_task(
                _sende_hintergrund, decrypt_field(user.email_encrypted), "Bilantiq: Passwort zurücksetzen", _reset_text(link),
            )
    _auffuellen(start)
    return PasswortVergessenResponse(detail=ANTWORT_TEXT)


def passwort_zuruecksetzen(
    payload: PasswortZuruecksetzenRequest,
    request: Request,
    hintergrund: BackgroundTasks,
    db: Session = Depends(get_db),
) -> None:
    ratelimit.begrenze_ip(request, "passwort-zuruecksetzen", limit=ZURUECKSETZEN_PRO_IP[0], fenster_sekunden=ZURUECKSETZEN_PRO_IP[1])
    ungueltig = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=UNGUELTIGER_LINK)
    passt = _TOKEN_FORMAT.fullmatch(payload.token.strip())
    if passt is None:
        raise ungueltig
    user_id, geheimnis = passt.group(1), passt.group(2)
    user = db.get(User, user_id)
    if user is None or user.geloescht_am is not None:
        raise ungueltig
    mandant_id = mandant_des_nutzers(db, user.id)
    if mandant_id is None:
        raise ungueltig
    set_rls_mandant(db, mandant_id)

    erwartet = _token_hash(geheimnis)
    zeile = db.query(PasswortResetToken).filter(PasswortResetToken.user_id == user.id, PasswortResetToken.token_hash == erwartet).first()
    if zeile is None or not hmac.compare_digest(zeile.token_hash, erwartet):
        raise ungueltig
    jetzt = _jetzt()
    if zeile.verbraucht_am is not None or _aware(zeile.ablauf_am) <= jetzt:
        record_audit(db, aktion="passwort_reset_abgelehnt", mandant_id=mandant_id, user_id=user.id,
                     kontext="verbraucht" if zeile.verbraucht_am is not None else "abgelaufen")
        db.commit()
        raise ungueltig
    # Atomar verbrauchen: bei zwei gleichzeitigen Anfragen gewinnt genau eine.
    verbraucht = db.execute(
        update(PasswortResetToken)
        .where(PasswortResetToken.id == zeile.id, PasswortResetToken.verbraucht_am.is_(None))
        .values(verbraucht_am=jetzt)
        .execution_options(synchronize_session=False)
    )
    if verbraucht.rowcount != 1:
        db.rollback()
        raise ungueltig

    user.passwort_hash = hash_password(payload.neues_passwort)
    user.passwort_geaendert_am = jetzt
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_erstellt_am = None
    invalidate_security_context(db, user)
    db.query(PasswortResetToken).filter(PasswortResetToken.user_id == user.id, PasswortResetToken.id != zeile.id).delete(synchronize_session=False)
    record_audit(db, aktion="passwort_zurueckgesetzt", mandant_id=mandant_id, user_id=user.id)
    db.commit()
    hintergrund.add_task(_sende_hintergrund, decrypt_field(user.email_encrypted), "Bilantiq: Dein Passwort wurde geändert", _GEAENDERT_TEXT)
