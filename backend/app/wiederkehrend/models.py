import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.core.intervall import INTERVALLE
from app.db import Base

__all__ = ["INTERVALLE", "WiederkehrendeAusgabe", "WiederkehrendeRechnung", "WiederkehrendeRechnungPosition"]


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WiederkehrendeRechnung(Base):
    """Vorlage fuer wiederkehrende Rechnungen. Erzeugt beim Faelligwerden einen
    echten Invoice-Entwurf (nie automatisch final) — siehe app/wiederkehrend/routes.py,
    erzeuge_faellige_rechnungen(). Positionen sind eine eigene Relation statt JSON,
    konsistent mit Invoice/InvoicePosition."""

    __tablename__ = "wiederkehrende_rechnungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"))
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("wiederkehrend.bezeichnung"))
    intervall: Mapped[str] = mapped_column(String(20))  # monatlich | quartalsweise | jaehrlich
    naechstes_datum: Mapped[date] = mapped_column(Date)
    enddatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kontakt: Mapped["Kontakt"] = relationship()  # noqa: F821 (Kontakt lives in app.invoices.models)
    positionen: Mapped[list["WiederkehrendeRechnungPosition"]] = relationship(
        back_populates="vorlage", cascade="all, delete-orphan", order_by="WiederkehrendeRechnungPosition.reihenfolge"
    )


class WiederkehrendeRechnungPosition(Base):
    __tablename__ = "wiederkehrende_rechnung_positionen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vorlage_id: Mapped[str] = mapped_column(String(36), ForeignKey("wiederkehrende_rechnungen.id"), index=True)
    beschreibung: Mapped[str] = mapped_column(EncryptedText("wiederkehrend_position.beschreibung"))
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("wiederkehrend_position.menge"))
    einzelpreis: Mapped[Decimal] = mapped_column(EncryptedDecimal("wiederkehrend_position.einzelpreis"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    reihenfolge: Mapped[int] = mapped_column(Integer, default=0)

    vorlage: Mapped["WiederkehrendeRechnung"] = relationship(back_populates="positionen")


class WiederkehrendeAusgabe(Base):
    """Vorlage fuer wiederkehrende Ausgaben (z.B. Software-Abo). Erzeugt beim
    Faelligwerden direkt eine gebuchte Ausgabe OHNE Beleg (Ausgabe.receipt_id bleibt
    None) — anders als bei Rechnungen gibt es hier keinen Entwurfs-Zwischenschritt,
    da eine Ausgabe im bestehenden Modell immer sofort eine gebuchte, unveraenderliche
    Buchung ist (siehe app/receipts/models.py::Ausgabe). Der fehlende Beleg wird in
    der UI ehrlich ausgewiesen, siehe app/wiederkehrend/ausgaben_routes.py."""

    __tablename__ = "wiederkehrende_ausgaben"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("wiederkehrende_ausgabe.bezeichnung"))
    anbieter: Mapped[str] = mapped_column(EncryptedText("wiederkehrende_ausgabe.anbieter"))
    betrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("wiederkehrende_ausgabe.betrag"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    kategorie: Mapped[str] = mapped_column(EncryptedText("wiederkehrende_ausgabe.kategorie"))
    intervall: Mapped[str] = mapped_column(String(20))
    naechstes_datum: Mapped[date] = mapped_column(Date)
    enddatum: Mapped[date | None] = mapped_column(Date, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
