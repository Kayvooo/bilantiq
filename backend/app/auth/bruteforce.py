"""Schutz vor Durchprobieren von Passwoertern und MFA-Codes (konto-bezogen, dauerhaft in der Datenbank).

Ein sechsstelliger TOTP-Code hat nur 10^6 Moeglichkeiten (mit ``valid_window=1`` sind drei davon gleichzeitig
gueltig). Ohne Begrenzung waere er bei bekanntem Passwort in kurzer Zeit zu erraten. Deshalb teilen sich alle
Pruefungen, die ein Geheimnis abfragen, einen Fehlversuchszaehler pro Konto:

- Anmeldung mit Passwort (``POST /auth/login``),
- MFA-Code beim Anmelden und bei der Ersteinrichtung (``/auth/login/mfa``, ``/auth/mfa/verify``),
- Passwort und MFA-Code bei sicherheitsrelevanten Aenderungen (Passwort aendern, MFA deaktivieren/neu einrichten,
  E-Mail-Aenderung).

Nach ``settings.failed_login_limit`` Fehlversuchen ist das Konto fuer ``settings.failed_login_lock_minutes`` gesperrt.
Der Zaehler wird erst nach einer vollstaendig erfolgreichen Anmeldung (bei aktivem MFA: nach dem Code) zurueckgesetzt,
sonst koennte ein Angreifer mit bekanntem Passwort den Zaehler durch erneutes Anmelden immer wieder auf null stellen.

Bekannte Grenze: Wer E-Mail-Adresse und Konto kennt, kann es durch absichtliche Fehlversuche voruebergehend sperren
(Preis dieses Schutzes; die Sperre ist zeitlich begrenzt und im Audit-Log sichtbar).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.models import User
from app.config import settings
from app.core.audit_log import record as record_audit


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _aware(wert: datetime | None) -> datetime | None:
    """SQLite liefert Zeitstempel ohne Zeitzone zurueck, Postgres mit."""
    if wert is not None and wert.tzinfo is None:
        return wert.replace(tzinfo=timezone.utc)
    return wert


def ist_gesperrt(user: User) -> bool:
    gesperrt_bis = _aware(user.locked_until)
    return gesperrt_bis is not None and gesperrt_bis > _jetzt()


def pruefe_nicht_gesperrt(user: User) -> None:
    """Fuer Pruefungen mit bereits authentifiziertem Nutzer (nicht fuer den Login selbst, der bleibt generisch)."""
    if ist_gesperrt(user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Fehlversuche. Das Konto ist vorübergehend gesperrt, bitte später erneut versuchen.",
        )


def registriere_fehlversuch(db: Session, user: User, *, mandant_id: str | None, aktion: str) -> None:
    """Zaehlt einen falschen Passwort-/Code-Versuch, sperrt ggf. das Konto und schreibt das Audit-Log (committet)."""
    user.failed_login_count += 1
    gerade_gesperrt = user.failed_login_count >= settings.failed_login_limit
    if gerade_gesperrt:
        user.locked_until = _jetzt() + timedelta(minutes=settings.failed_login_lock_minutes)
    record_audit(db, aktion=aktion, mandant_id=mandant_id, user_id=user.id)
    if gerade_gesperrt:
        record_audit(db, aktion="konto_gesperrt", mandant_id=mandant_id, user_id=user.id, kontext=aktion)
    db.commit()


def setze_zurueck(user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None


def pruefe_geheimnis(
    db: Session,
    user: User,
    *,
    ist_korrekt: Callable[[], bool],
    mandant_id: str | None,
    aktion: str,
    fehlertext: str,
) -> None:
    """Gemeinsamer Ablauf fuer eingeloggte Pruefungen: gesperrt -> 429, falsch -> zaehlen und 400."""
    pruefe_nicht_gesperrt(user)
    if ist_korrekt():
        return
    registriere_fehlversuch(db, user, mandant_id=mandant_id, aktion=aktion)
    if ist_gesperrt(user):
        pruefe_nicht_gesperrt(user)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=fehlertext)
