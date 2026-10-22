"""Frische MFA-Bestaetigung fuer sensible Aktionen (docs/specs/mfa-pflicht.md).

Ablauf: Die Aktion antwortet ohne gueltige Bestaetigung mit HTTP 428. Der Client holt mit ``POST /auth/bestaetigung`` (aktueller
TOTP- oder Wiederherstellungscode) ein kurzlebiges Token und wiederholt den Aufruf mit dem Header ``X-Bestaetigung``.

Das Token ist ein signiertes JWT (scope ``bestaetigung``), gebunden an Konto, Sitzung, Mandant, ``security_version`` und
Aktionsklasse. Es gilt ``settings.bestaetigung_minuten`` Minuten und ist nicht auf einen einzelnen Aufruf beschraenkt. Es ist
kein Zugriffstoken: ``require_full_auth`` akzeptiert nur ``scope == "full"``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import bruteforce, mfa_service
from app.auth.dependencies import require_owner
from app.auth.models import User
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core.crypto import decrypt_field
from app.core.security import create_token, decode_access_token
from app.db import get_db

SCOPE = "bestaetigung"
AKTIONEN = ("iban_aendern", "benutzer_verwalten", "gesamtexport")
HEADER = "X-Bestaetigung"

BESTAETIGUNG_ERFORDERLICH = (
    "Bitte bestätige die Aktion mit einem aktuellen Code aus deiner Authenticator-App (oder einem Wiederherstellungscode)."
)


def _benoetigt_bestaetigung(user: User) -> bool:
    """MFA_PFLICHT=aus (nur Entwicklung/Tests) schaltet auch die Bestaetigung ab. Ohne MFA im Konto gibt es nichts zu bestaetigen
    (ausser bei Rollen ohne Pflicht moeglich, dort sind die geschuetzten Aktionen ohnehin Owner-only)."""
    return settings.mfa_pflicht != "aus" and user.mfa_enabled


def pruefe_zweiten_faktor(db: Session, user: User, eingabe: str, *, mandant_id: str) -> None:
    """Aktueller TOTP-Code (einmal verbrauchbar) oder Wiederherstellungscode, mit Fehlversuchszaehler und Sperre."""
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA ist nicht eingerichtet.")
    code = eingabe.strip()
    if mfa_service.ist_totp_format(code):
        secret = decrypt_field(user.mfa_secret_encrypted)
        bruteforce.pruefe_geheimnis(
            db, user, ist_korrekt=lambda: mfa_service.verbrauche_totp(db, user, secret=secret, code=code),
            mandant_id=mandant_id, aktion="mfa_code_falsch", fehlertext="Der Code ist falsch oder abgelaufen.",
        )
    else:
        bruteforce.pruefe_geheimnis(
            db, user, ist_korrekt=lambda: mfa_service.verbrauche_wiederherstellungscode(db, user, code),
            mandant_id=mandant_id, aktion="mfa_wiederherstellungscode_falsch",
            fehlertext="Der Code oder Wiederherstellungscode ist falsch oder bereits verwendet.",
        )
        record_audit(db, aktion="mfa_wiederherstellungscode_verwendet", mandant_id=mandant_id, user_id=user.id, kontext="bestaetigung")
    bruteforce.setze_zurueck(user)


def erteile_bestaetigung(db: Session, auth: dict, aktion: str, code: str) -> tuple[str, datetime]:
    """Prueft den zweiten Faktor und stellt das Bestaetigungs-Token aus. Der Aufrufer committet."""
    user = db.get(User, auth["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung ist nicht mehr gueltig.")
    pruefe_zweiten_faktor(db, user, code, mandant_id=auth["mandant_id"])
    minuten = settings.bestaetigung_minuten
    token = create_token(
        user_id=user.id, scope=SCOPE, mandant_id=auth["mandant_id"], minutes=minuten, session_id=auth["sid"],
        security_version=user.security_version, zusatz={"aktion": aktion},
    )
    record_audit(db, aktion="bestaetigung_erteilt", mandant_id=auth["mandant_id"], user_id=user.id, kontext=aktion)
    return token, datetime.now(timezone.utc) + timedelta(minutes=minuten)


def pruefe_bestaetigung(db: Session, auth: dict, aktion: str, token: str | None) -> None:
    """Wirft 428, wenn keine gueltige Bestaetigung fuer genau diese Sitzung, dieses Konto und diese Aktionsklasse vorliegt."""
    user = db.get(User, auth["sub"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung ist nicht mehr gueltig.")
    if not _benoetigt_bestaetigung(user):
        return
    verlangt = HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail=BESTAETIGUNG_ERFORDERLICH)
    if not token:
        raise verlangt
    try:
        daten = decode_access_token(token)
    except jwt.PyJWTError:
        raise verlangt from None
    if (
        daten.get("scope") != SCOPE
        or daten.get("aktion") != aktion
        or daten.get("sub") != auth["sub"]
        or daten.get("sid") != auth.get("sid")
        or daten.get("mandant_id") != auth["mandant_id"]
        or daten.get("sv") != user.security_version
    ):
        raise verlangt


def verlange_bestaetigung(aktion: str):
    """FastAPI-Abhaengigkeit: Owner UND frische Bestaetigung der Aktionsklasse ``aktion``."""
    assert aktion in AKTIONEN

    def _verlange(
        auth: dict = Depends(require_owner),
        x_bestaetigung: str | None = Header(default=None, alias=HEADER),
        db: Session = Depends(get_db),
    ) -> dict:
        pruefe_bestaetigung(db, auth, aktion, x_bestaetigung)
        return auth

    return _verlange
