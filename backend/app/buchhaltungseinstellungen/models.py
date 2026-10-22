from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Buchhaltungseinstellungen(Base):
    __tablename__ = "buchhaltungseinstellungen"

    mandant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mandanten.id"),
        primary_key=True,
    )
    standard_zahlungsziel_tage: Mapped[int] = mapped_column(Integer, default=14)
    standard_ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("19.00"))
    kleinunternehmer: Mapped[bool] = mapped_column(Boolean, default=False)
