import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SonstigeEinnahme(Base):
    __tablename__ = "sonstige_einnahmen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("einnahme.bezeichnung"))
    betrag_brutto: Mapped[Decimal] = mapped_column(EncryptedDecimal("einnahme.betrag_brutto"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    datum: Mapped[date] = mapped_column(Date)
    verwendungszweck: Mapped[str | None] = mapped_column(EncryptedText("einnahme.verwendungszweck"), nullable=True)
