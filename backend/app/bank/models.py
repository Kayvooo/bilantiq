"""Kontoauszug-Import: Bankkonten, Importdateien und einzelne Umsaetze.

Ein Bankumsatz ist Quelldatum: Er wird nie veraendert, nur sein Status (offen,
zugeordnet, ignoriert) und die Zuordnung. Jede Aenderung steht im Audit-Log. Alle
personenbezogenen Felder (Gegenpartei, IBAN, Verwendungszweck, Betrag) sind verschluesselt;
Suchbares laeuft ueber Blind-Indizes."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Bankkonto(Base):
    __tablename__ = "bankkonten"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("bankkonto.bezeichnung"))
    iban: Mapped[str | None] = mapped_column(EncryptedText("bankkonto.iban"), nullable=True)
    # Blind-Index der IBAN: ordnet CAMT-Dateien dem richtigen Konto zu, ohne die IBAN durchsuchbar zu speichern.
    iban_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    # Zuletzt verwendetes Spaltenprofil fuer CSV-Importe (JSON).
    csv_profil: Mapped[str | None] = mapped_column(EncryptedText("bankkonto.csv_profil"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Bankimport(Base):
    __tablename__ = "bankimporte"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bankkonto_id: Mapped[str] = mapped_column(String(36), ForeignKey("bankkonten.id"), index=True)
    format: Mapped[str] = mapped_column(String(10))  # camt | csv
    dateiname: Mapped[str] = mapped_column(EncryptedText("bankimport.dateiname"))
    datei_hash: Mapped[str] = mapped_column(String(64))
    datei_referenz: Mapped[str] = mapped_column(String(500))  # verschluesselte Originaldatei, siehe app/bank/service.py
    anzahl_neu: Mapped[int] = mapped_column(Integer)
    anzahl_doppelt: Mapped[int] = mapped_column(Integer)
    zeitraum_von: Mapped[date | None] = mapped_column(Date, nullable=True)
    zeitraum_bis: Mapped[date | None] = mapped_column(Date, nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Bankumsatz(Base):
    __tablename__ = "bankumsaetze"
    __table_args__ = (UniqueConstraint("bankkonto_id", "dedupe_hash", name="uq_bankumsatz_dedupe"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bankkonto_id: Mapped[str] = mapped_column(String(36), ForeignKey("bankkonten.id"), index=True)
    import_id: Mapped[str] = mapped_column(String(36), ForeignKey("bankimporte.id"), index=True)

    buchungsdatum: Mapped[date] = mapped_column(Date, index=True)
    wertstellung: Mapped[date | None] = mapped_column(Date, nullable=True)
    betrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("bankumsatz.betrag"))  # mit Vorzeichen: Eingang +, Ausgang -
    waehrung: Mapped[str] = mapped_column(String(3), default="EUR")
    gegenpartei_name: Mapped[str | None] = mapped_column(EncryptedText("bankumsatz.gegenpartei_name"), nullable=True)
    gegenpartei_iban: Mapped[str | None] = mapped_column(EncryptedText("bankumsatz.gegenpartei_iban"), nullable=True)
    verwendungszweck: Mapped[str] = mapped_column(EncryptedText("bankumsatz.verwendungszweck"), default="")
    end_to_end_id: Mapped[str | None] = mapped_column(EncryptedText("bankumsatz.end_to_end_id"), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(12), default="offen", index=True)  # offen | zugeordnet | ignoriert
    zuordnung_typ: Mapped[str | None] = mapped_column(String(12), nullable=True)  # rechnung | beleg | ausgabe
    zuordnung_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    zugeordnet_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ignoriert_grund: Mapped[str | None] = mapped_column(EncryptedText("bankumsatz.ignoriert_grund"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
