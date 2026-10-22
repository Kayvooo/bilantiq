import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Angebotsnummernkreis(Base):
    """Own counter table, deliberately not shared with Rechnungsnummernkreis — see
    app/quotes/numbering.py. Same shape, kept separate so invoice and quote sequences
    can never collide or interfere with each other."""

    __tablename__ = "angebotsnummernkreise"
    __table_args__ = (UniqueConstraint("mandant_id", "jahr", name="uq_angebotsnummernkreis_mandant_jahr"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    naechste_nummer: Mapped[int] = mapped_column(Integer, default=1)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    nummer: Mapped[str | None] = mapped_column(String(40), nullable=True)  # set on Versand
    status: Mapped[str] = mapped_column(String(20), default="entwurf")  # entwurf|versendet|angenommen|abgelehnt
    gueltig_bis: Mapped[date] = mapped_column(Date)
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    netto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("quote.netto_gesamt"), default=Decimal("0"))
    ust_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("quote.ust_gesamt"), default=Decimal("0"))
    brutto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("quote.brutto_gesamt"), default=Decimal("0"))
    umgewandelt_in_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("invoices.id"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Tatsaechlicher E-Mail-Versand (app/core/mailer.py) -- bewusst NICHT versendet_am
    # oben wiederverwendet: das Feld existiert schon seit 0005 und bedeutet dort "Entwurf
    # abgeschlossen, Angebotsnummer vergeben" (siehe routes.py::send_quote), unabhaengig
    # davon ob je gemailt wurde. Ein Angebot kann also "versendet" (Status) sein ohne je
    # gemailt worden zu sein, und umgekehrt beliebig oft gemailt werden, ohne dass sich
    # Status oder versendet_am dadurch aendern.
    email_versendet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    kontakt: Mapped["Kontakt"] = relationship()  # noqa: F821 (Kontakt lives in app.invoices.models)
    positionen: Mapped[list["QuotePosition"]] = relationship(
        back_populates="quote", cascade="all, delete-orphan", order_by="QuotePosition.reihenfolge"
    )


class QuotePosition(Base):
    __tablename__ = "quote_positionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    quote_id: Mapped[str] = mapped_column(String(36), ForeignKey("quotes.id"), index=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, default=0)
    beschreibung: Mapped[str] = mapped_column(EncryptedText("quote_position.beschreibung"))
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("quote_position.menge"))
    einzelpreis: Mapped[Decimal] = mapped_column(EncryptedDecimal("quote_position.einzelpreis"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    quote: Mapped["Quote"] = relationship(back_populates="positionen")
