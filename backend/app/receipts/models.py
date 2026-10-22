import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    datei_referenz: Mapped[str] = mapped_column(String(500))  # relative path, see app/receipts/storage.py
    datei_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex
    status: Mapped[str] = mapped_column(String(20), default="neu")  # neu | geprueft | unklar | gebucht

    betrag: Mapped[Decimal | None] = mapped_column(EncryptedDecimal("receipt.betrag"), nullable=True)
    betrag_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    datum: Mapped[date | None] = mapped_column(Date, nullable=True)
    datum_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    anbieter: Mapped[str | None] = mapped_column(EncryptedText("receipt.anbieter"), nullable=True)
    anbieter_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ust_satz: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    ust_satz_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    kategorie_vorschlag: Mapped[str | None] = mapped_column(EncryptedText("receipt.kategorie_vorschlag"), nullable=True)
    kategorie_vorschlag_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Not gated by a confidence threshold — this is commentary explaining the category
    # choice, not itself an extracted fact. See app/receipts/ai_extraction.py.
    begruendung: Mapped[str | None] = mapped_column(EncryptedText("receipt.begruendung"), nullable=True)

    # Maschinenlesbare E-Rechnung (XRechnung/ZUGFeRD): ocr | xrechnung | zugferd. Bei diesen
    # Belegen ist das XML der Originalbeleg, die Felder darunter stammen daraus.
    beleg_typ: Mapped[str] = mapped_column(String(20), default="ocr", server_default="ocr")
    rechnungsnummer: Mapped[str | None] = mapped_column(EncryptedText("receipt.rechnungsnummer"), nullable=True)
    faelligkeit: Mapped[date | None] = mapped_column(Date, nullable=True)
    iban: Mapped[str | None] = mapped_column(EncryptedText("receipt.iban"), nullable=True)
    # JSON: Syntax, Verkaeufer-USt-IdNr, Waehrung, Steuer-Aufteilung, Hinweise.
    e_rechnung_daten: Mapped[str | None] = mapped_column(EncryptedText("receipt.e_rechnung_daten"), nullable=True)
    # Blind-Index ueber Verkaeufer + Rechnungsnummer: erkennt dieselbe Rechnung als XML und als PDF.
    dedupe_key: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    gebucht_als: Mapped[str | None] = mapped_column(String(36), ForeignKey("ausgaben.id"), nullable=True)
    hochgeladen_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Ausgabe(Base):
    """The booking created once a receipt is confirmed. Immutable once created —
    no update/delete route exists, matching the GoBD stance already applied to
    Invoice/AuditLogEintrag elsewhere in this codebase."""

    __tablename__ = "ausgaben"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    # No FK to receipts.id here on purpose — Receipt.gebucht_als already links the two
    # rows in the other direction, and a FK on both sides makes them a dependency
    # cycle (breaks SQLite's drop_all table sort; matches migrations/0004, which
    # doesn't declare this FK either).
    # Nullable since 0011: wiederkehrende Ausgaben (app/wiederkehrend/) buchen direkt
    # ohne hochgeladenen Beleg — receipt_id bleibt dann None, siehe ausgaben_routes.py.
    receipt_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    betrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("ausgabe.betrag"))
    # datum ist das Beleg-/Rechnungsdatum. Fuer EÜR/Cashflow ist dagegen das
    # tatsächliche Zahlungsdatum massgeblich; beides darf nicht vermischt werden.
    datum: Mapped[date] = mapped_column(Date)
    zahlungsdatum: Mapped[date] = mapped_column(Date)
    anbieter: Mapped[str] = mapped_column(EncryptedText("ausgabe.anbieter"))
    # Bei gemischten Steuersaetzen ist dieses Legacy-/Kurzfeld None; die
    # steuerliche Aufteilung lebt dann in steueranteile.
    ust_satz: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    kategorie: Mapped[str] = mapped_column(EncryptedText("ausgabe.kategorie"))
    konto: Mapped[str] = mapped_column(String(10))  # SKR03, see app/core/kontenrahmen.py
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    steueranteile: Mapped[list["AusgabeSteueranteil"]] = relationship(
        back_populates="ausgabe", cascade="all, delete-orphan"
    )


class AusgabeSteueranteil(Base):
    """Brutto-Anteil einer Ausgabe fuer genau einen USt-Satz.

    Ein normaler Beleg hat einen Anteil. Gemischte Belege (z.B. Gastronomie 7/19 %)
    haben mehrere Anteile. Die Summe der Bruttobetraege muss Ausgabe.betrag ergeben.
    """

    __tablename__ = "ausgabe_steueranteile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    ausgabe_id: Mapped[str] = mapped_column(String(36), ForeignKey("ausgaben.id"), index=True)
    bruttobetrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("ausgabe_steueranteil.bruttobetrag"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    ausgabe: Mapped["Ausgabe"] = relationship(back_populates="steueranteile")
