import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Mitarbeiter(Base):
    __tablename__ = "mitarbeitende"
    __table_args__ = (UniqueConstraint("mandant_id", "personalnummer", name="uq_mitarbeitende_personalnummer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    personalnummer: Mapped[str] = mapped_column(String(30))
    vorname_encrypted: Mapped[str] = mapped_column(String(500))
    nachname_encrypted: Mapped[str] = mapped_column(String(500))
    eintrittsdatum: Mapped[date] = mapped_column(Date)
    austrittsdatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    monatsbrutto: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.monatsbrutto"))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    monatsentwuerfe: Mapped[list["LohnMonatsentwurf"]] = relationship(back_populates="mitarbeiter")


class LohnMonatsentwurf(Base):
    __tablename__ = "lohn_monatsentwuerfe"
    __table_args__ = (UniqueConstraint("mitarbeiter_id", "jahr", "monat", name="uq_lohn_mitarbeiter_monat"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    mitarbeiter_id: Mapped[str] = mapped_column(String(36), ForeignKey("mitarbeitende.id"), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    monat: Mapped[int] = mapped_column(Integer)
    grundbrutto: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.grundbrutto"))
    steuerpflichtige_zuschlaege: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.steuerpflichtige_zuschlaege"), default=Decimal("0"))
    steuerfreie_erstattungen: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.steuerfreie_erstattungen"), default=Decimal("0"))
    sonstige_abzuege: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.sonstige_abzuege"), default=Decimal("0"))
    gesamtbrutto: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.gesamtbrutto"))
    zwischenbetrag_vor_abgaben: Mapped[Decimal] = mapped_column(EncryptedDecimal("payroll.zwischenbetrag_vor_abgaben"))
    status: Mapped[str] = mapped_column(String(20), default="vorbereitung")
    abgeschlossen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    mitarbeiter: Mapped["Mitarbeiter"] = relationship(back_populates="monatsentwuerfe")
