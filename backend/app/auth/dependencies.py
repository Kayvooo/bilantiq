import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import get_db, set_rls_mandant
from app.auth.models import Mitgliedschaft, User
from app.auth.mfa_richtlinie import MFA_EINRICHTUNG_ERFORDERLICH, mfa_erforderlich
from app.auth.security_service import session_is_valid

_bearer = HTTPBearer(auto_error=False)


def _decode_or_401(token: str | None) -> dict:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")
    try:
        return decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungueltiges oder abgelaufenes Token.") from exc


def require_pre_mfa(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> dict:
    payload = _decode_or_401(credentials.credentials if credentials else None)
    if payload.get("scope") != "pre_mfa":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA-Schritt erforderlich.")
    user = db.get(User, payload.get("sub"))
    mandant_id = payload.get("mandant_id")
    if (
        user is None
        or user.geloescht_am is not None
        or payload.get("sv") != user.security_version
        or not isinstance(mandant_id, str)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Anmeldung ist nicht mehr gueltig.")
    # Auch der MFA-Schritt schreibt Audit-Einträge des Mandanten; das signierte Token nennt ihn.
    set_rls_mandant(db, mandant_id)
    return payload


def require_full_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> dict:
    payload = _decode_or_401(credentials.credentials if credentials else None)
    if payload.get("scope") != "full":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA-Bestaetigung erforderlich.")
    user = db.get(User, payload.get("sub"))
    mandant_id = payload.get("mandant_id")
    session_id = payload.get("sid")
    if not isinstance(mandant_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung ist nicht mehr gueltig.")
    # PostgreSQL-RLS muss vor dem Lesen von auth_sessions/mitgliedschaften gesetzt
    # sein. Der Wert stammt aus dem signierten JWT und wird direkt danach gegen
    # Session + Membership validiert.
    set_rls_mandant(db, mandant_id)
    if (
        user is None
        or user.geloescht_am is not None
        or payload.get("sv") != user.security_version
        or not isinstance(session_id, str)
        or not session_is_valid(db, session_id=session_id, user=user, mandant_id=mandant_id)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung ist nicht mehr gueltig.")
    mitgliedschaft = (
        db.query(Mitgliedschaft)
        .filter(Mitgliedschaft.user_id == user.id, Mitgliedschaft.mandant_id == mandant_id)
        .first()
    )
    if mitgliedschaft is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung ist nicht mehr gueltig.")
    # MFA-Pflicht (docs/specs/mfa-pflicht.md): Rolle und MFA-Stand stammen aus der Datenbank, nicht aus dem Token. Das trifft
    # auch Sitzungen, die vor der Einfuehrung der Pflicht ausgestellt wurden. 401 (nicht 403), damit das Frontend die
    # Sitzung verwirft und zur Anmeldung leitet, dort beginnt die Einrichtung.
    if mfa_erforderlich(mitgliedschaft.rolle) and not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MFA_EINRICHTUNG_ERFORDERLICH)
    return payload


def ist_owner(db: Session, auth: dict) -> bool:
    """Aktuelle Mandantenrolle aus der Mitgliedschaft (nicht aus dem JWT)."""
    mitgliedschaft = (
        db.query(Mitgliedschaft)
        .filter(Mitgliedschaft.user_id == auth["sub"], Mitgliedschaft.mandant_id == auth["mandant_id"])
        .first()
    )
    return mitgliedschaft is not None and mitgliedschaft.rolle == "owner"


def require_owner(auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> dict:
    """Prüft die aktuelle Mandantenrolle aus der Mitgliedschaft, nicht aus dem JWT."""
    if not ist_owner(db, auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur der Owner darf das.")
    return auth
