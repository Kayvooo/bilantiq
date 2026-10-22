"""Missbrauchsschutz und Reply-To fuer den Dokumentenversand per E-Mail (Rechnung, Angebot, Mahnung).

Ohne Begrenzung koennte ein angemeldeter Nutzer ueber ``/versenden`` beliebig viele
E-Mails mit frei waehlbarem Text an beliebige Empfaenger ausloesen -- ein Risiko fuer den Ruf der
Absenderdomain (Spam/Phishing ueber Bilantiq).

Versandlimit je Mandant
-----------------------
Gezaehlt wird aus dem **Audit-Log** (erfolgreiche Versandaktionen der letzten Stunde/24 Stunden), nicht im
Arbeitsspeicher: Das ueberlebt Neustarts, gilt auch bei mehreren Prozessen und braucht keine neue Tabelle.
Defaults: ``email_limit_pro_stunde`` und ``email_limit_pro_tag`` in ``app/config.py``.

Grenzen (ehrlich):
- Gezaehlt werden nur *erfolgreiche* Versandaktionen; fehlgeschlagene SMTP-Versuche zaehlen nicht.
- Parallele Anfragen im selben Moment koennen das Limit um wenige Mails ueberschreiten (kein Sperren der Zaehlung).
- Das Limit gilt je Mandant. Wer viele Konten registriert (Registrierung ist nur je IP begrenzt), hat je Konto
  ein eigenes Kontingent. Das Limit ist ein Schutzgurt, kein vollstaendiger Spam-Schutz.
- Sicherheitsmails (E-Mail-Aenderung) haben ihren eigenen Zaehler (``app/security/routes.py``).

Reply-To
--------
Der Absender ist immer die Systemadresse (``smtp_absender`` bzw. ``smtp_user``); Antworten gingen sonst an ``noreply@``. Ein eigenes
Kontaktadress-Feld am Mandanten gibt es nicht (es braeuchte eine Migration). Deshalb wird die Anmelde-Adresse des
versendenden Nutzers als Reply-To verwendet, sofern gueltig. Das macht diese Adresse fuer den Empfaenger
sichtbar -- abschaltbar mit ``EMAIL_REPLY_TO_NUTZER=false``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core import mailer
from app.core.audit_log import AuditLogEintrag
from app.core.crypto import decrypt_field

# Audit-Aktionen der erfolgreichen Versandrouten (siehe app/invoices, app/quotes, app/mahnwesen).
VERSAND_AKTIONEN = ("rechnung_versendet", "angebot_versendet_email", "mahnung_versendet")


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _aware(wert: datetime) -> datetime:
    return wert.replace(tzinfo=timezone.utc) if wert.tzinfo is None else wert


def pruefe_email_aktiv() -> None:
    """Wirft 503 mit verstaendlicher Meldung, wenn auf dieser Instanz kein SMTP eingerichtet ist."""
    if not settings.email_aktiv:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=mailer.EMAIL_NICHT_EINGERICHTET)


def pruefe_versandlimit(db: Session, mandant_id: str) -> None:
    """Wirft 503, wenn SMTP fehlt, und 429 mit ``Retry-After``, wenn der Mandant sein Stunden- oder
    Tageskontingent ausgeschoepft hat. Jede Versandroute ruft diese Pruefung vor dem Rendern auf."""
    pruefe_email_aktiv()
    jetzt = _jetzt()
    for limit, fenster in ((settings.email_limit_pro_stunde, timedelta(hours=1)), (settings.email_limit_pro_tag, timedelta(days=1))):
        if limit <= 0:
            continue  # 0 = Limit aus
        seit = jetzt - fenster
        basis = db.query(AuditLogEintrag).filter(
            AuditLogEintrag.mandant_id == mandant_id,
            AuditLogEintrag.aktion.in_(VERSAND_AKTIONEN),
            AuditLogEintrag.zeitpunkt > seit,
        )
        if basis.count() >= limit:
            aeltester = basis.with_entities(func.min(AuditLogEintrag.zeitpunkt)).scalar()
            warten = int(max(60.0, (_aware(aeltester) + fenster - jetzt).total_seconds())) if aeltester else 3600
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Versandlimit erreicht ({limit} E-Mails pro {'Stunde' if fenster < timedelta(days=1) else '24 Stunden'}). "
                    "Bitte später erneut versuchen oder die Unterlagen als PDF herunterladen."
                ),
                headers={"Retry-After": str(warten)},
            )


def antwort_an_adresse(db: Session, user_id: str) -> str | None:
    """Reply-To fuer ausgehende Dokumente: Adresse des versendenden Nutzers, wenn gueltig (sonst None)."""
    if not settings.email_reply_to_nutzer:
        return None
    from app.auth.models import User

    user = db.get(User, user_id)
    if user is None or user.geloescht_am is not None:
        return None
    try:
        adresse = decrypt_field(user.email_encrypted)
        return mailer._adresse(adresse, "Antwort-an")
    except Exception:
        return None
