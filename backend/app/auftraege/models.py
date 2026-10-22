import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Auftragsbestaetigungsnummernkreis(Base):
    """Own counter table — same shape as Angebotsnummernkreis/Rechnungsnummernkreis,
    kept separate so this sequence can never collide with quotes or invoices."""

    __tablename__ = "auftragsbestaetigungsnummernkreise"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    naechste_nummer: Mapped[int] = mapped_column(Integer, default=1)


class Lieferscheinnummernkreis(Base):
    __tablename__ = "lieferscheinnummernkreise"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    jahr: Mapped[int] = mapped_column(Integer)
    naechste_nummer: Mapped[int] = mapped_column(Integer, default=1)


class Auftragsbestaetigung(Base):
    """Erzeugt aus einem angenommenen Angebot — kopiert dessen Positionen und Summen zu
    diesem Zeitpunkt fest (das Angebot bleibt unveraendert, wie bei der Rechnungs-
    Umwandlung in app/quotes/routes.py::convert_to_invoice). Unveraenderlich nach dem
    Anlegen: keine Update/Delete-Routen."""

    __tablename__ = "auftragsbestaetigungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    quote_id: Mapped[str] = mapped_column(String(36), ForeignKey("quotes.id"))
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    nummer: Mapped[str] = mapped_column(String(40))
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    netto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag.netto_gesamt"), default=Decimal("0"))
    ust_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag.ust_gesamt"), default=Decimal("0"))
    brutto_gesamt: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag.brutto_gesamt"), default=Decimal("0"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kontakt: Mapped["Kontakt"] = relationship()  # noqa: F821 (Kontakt lives in app.invoices.models)
    quote: Mapped["Quote"] = relationship()  # noqa: F821 (Quote lives in app.quotes.models)
    positionen: Mapped[list["AuftragsbestaetigungPosition"]] = relationship(
        back_populates="auftragsbestaetigung", cascade="all, delete-orphan",
        order_by="AuftragsbestaetigungPosition.reihenfolge",
    )
    lieferscheine: Mapped[list["Lieferschein"]] = relationship(back_populates="auftragsbestaetigung")


class AuftragsbestaetigungPosition(Base):
    __tablename__ = "auftragsbestaetigung_positionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    auftragsbestaetigung_id: Mapped[str] = mapped_column(String(36), ForeignKey("auftragsbestaetigungen.id"), index=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, default=0)
    beschreibung: Mapped[str] = mapped_column(EncryptedText("auftrag_position.beschreibung"))
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag_position.menge"))
    einzelpreis: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag_position.einzelpreis"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    auftragsbestaetigung: Mapped["Auftragsbestaetigung"] = relationship(back_populates="positionen")


class Lieferschein(Base):
    """Erzeugt aus einer Auftragsbestaetigung — Positionen ohne Preis (Menge und
    Beschreibung), wie im Handel ueblich fuer Lieferscheine. Unveraenderlich nach dem
    Anlegen: keine Update/Delete-Routen. Mehrere Lieferscheine je Auftragsbestaetigung
    sind erlaubt (Teillieferungen)."""

    __tablename__ = "lieferscheine"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    auftragsbestaetigung_id: Mapped[str] = mapped_column(String(36), ForeignKey("auftragsbestaetigungen.id"))
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    nummer: Mapped[str] = mapped_column(String(40))
    lieferdatum: Mapped[date] = mapped_column(Date)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kontakt: Mapped["Kontakt"] = relationship()  # noqa: F821
    auftragsbestaetigung: Mapped["Auftragsbestaetigung"] = relationship(back_populates="lieferscheine")
    positionen: Mapped[list["LieferscheinPosition"]] = relationship(
        back_populates="lieferschein", cascade="all, delete-orphan", order_by="LieferscheinPosition.reihenfolge"
    )


class LieferscheinPosition(Base):
    __tablename__ = "lieferschein_positionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    lieferschein_id: Mapped[str] = mapped_column(String(36), ForeignKey("lieferscheine.id"), index=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, default=0)
    beschreibung: Mapped[str] = mapped_column(EncryptedText("auftrag_position.beschreibung"))
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("auftrag_position.menge"))

    lieferschein: Mapped["Lieferschein"] = relationship(back_populates="positionen")
