import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.encrypted_types import EncryptedText
from app.db import Base


class AuditLogAppendOnlyError(Exception):
    """Raised when code attempts to modify or delete an existing audit log entry."""


class AuditLogEintrag(Base):
    __tablename__ = "audit_log_eintraege"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mandant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    aktion: Mapped[str] = mapped_column(String(100))
    kontext: Mapped[str] = mapped_column(EncryptedText("audit.kontext"), default="")
    zeitpunkt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


@event.listens_for(Session, "before_flush")
def _forbid_audit_log_mutation(session: Session, _flush_context, _instances) -> None:
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, AuditLogEintrag):
            raise AuditLogAppendOnlyError(
                "Audit-Log-Eintraege sind unveraenderlich: Update/Delete ist nicht erlaubt."
            )


def record(db: Session, *, aktion: str, mandant_id: str | None = None, user_id: str | None = None, kontext: str = "") -> AuditLogEintrag:
    eintrag = AuditLogEintrag(mandant_id=mandant_id, user_id=user_id, aktion=aktion, kontext=kontext)
    db.add(eintrag)
    return eintrag
