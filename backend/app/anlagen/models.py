import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Anlage(Base):
    """Anlagegut mit linearer AfA (§7 EStG). Nutzungsdauer wird manuell erfasst --
    es sind keine amtlichen AfA-Tabellen (Nutzungsdauer je Anlagegut-Kategorie)
    hinterlegt, siehe Annahmen in der Spec. Der AfA-Plan wird nicht gespeichert,
    sondern in app/anlagen/afa.py deterministisch aus diesen Stammdaten berechnet."""

    __tablename__ = "anlagen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("anlage.bezeichnung"))
    anschaffungsdatum: Mapped[date] = mapped_column(Date)
    anschaffungskosten_netto: Mapped[Decimal] = mapped_column(EncryptedDecimal("anlage.anschaffungskosten_netto"))
    nutzungsdauer_jahre: Mapped[int] = mapped_column(Integer)
    kategorie: Mapped[str | None] = mapped_column(EncryptedText("anlage.kategorie"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
