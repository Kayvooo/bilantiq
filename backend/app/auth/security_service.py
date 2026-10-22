from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.models import AuthSession, User
from app.config import settings
from app.core.security import create_token


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def create_full_session(
    db: Session,
    *,
    user: User,
    mandant_id: str,
    user_agent: str | None,
    remember_device: bool = False,
) -> tuple[AuthSession, str]:
    now = _now()
    lifetime_minutes = settings.remember_device_days * 24 * 60 if remember_device else settings.access_token_minutes
    expires = now + timedelta(minutes=lifetime_minutes)
    session = AuthSession(
        user_id=user.id,
        mandant_id=mandant_id,
        user_agent=(user_agent or "")[:500] or None,
        erstellt_am=now,
        laeuft_ab_am=expires,
    )
    db.add(session)
    db.flush()
    token = create_token(
        user_id=user.id,
        scope="full",
        mandant_id=mandant_id,
        minutes=lifetime_minutes,
        session_id=session.id,
        security_version=user.security_version,
    )
    return session, token


def revoke_sessions(
    db: Session,
    *,
    user_id: str,
    except_session_id: str | None = None,
) -> int:
    now = _now()
    query = db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.widerrufen_am.is_(None),
    )
    if except_session_id is not None:
        query = query.filter(AuthSession.id != except_session_id)
    return query.update({AuthSession.widerrufen_am: now}, synchronize_session=False)


def invalidate_security_context(db: Session, user: User) -> None:
    user.security_version += 1
    revoke_sessions(db, user_id=user.id)


def session_is_valid(db: Session, *, session_id: str, user: User, mandant_id: str) -> bool:
    now = _now()
    session = db.get(AuthSession, session_id)
    return bool(
        session
        and session.user_id == user.id
        and session.mandant_id == mandant_id
        and session.widerrufen_am is None
        and _aware(session.laeuft_ab_am) > now
    )
