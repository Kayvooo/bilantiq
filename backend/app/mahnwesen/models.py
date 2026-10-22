import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Mahnung(Base):
    """One dunning notice for one invoice. Immutable once created — issuing a new
    stage never edits an earlier one, it just adds the next row (see routes.py, which
    derives the next `stufe` from how many rows already exist for the invoice)."""

    __tablename__ = "mahnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id"), index=True)
    stufe: Mapped[int] = mapped_column(Integer)  # 1 Zahlungserinnerung, 2 = 1. Mahnung, 3 = 2. Mahnung
    mahngebuehr: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    neue_faelligkeit: Mapped[date] = mapped_column(Date)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # E-Mail-Versand (app/core/mailer.py) -- kein Entwurfsstatus hier noetig, eine
    # Mahnung ist laut Docstring oben immer sofort "final" (nichts wird als Entwurf
    # angelegt).
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
