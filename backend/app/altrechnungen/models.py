"""Rechnungen aus einem frueheren Programm (Altrechnungen).

Grundsatz: Eine Altrechnung ist KEINE Bilantiq-Rechnung. Sie bekommt keine Nummer aus dem
Bilantiq-Nummernkreis, wird nie neu als PDF erzeugt und ist unveraenderbar (GoBD). Geaendert
wird nur, was nach dem Umzug passiert: Zahlungen, die in Bilantiq erfasst werden. Zahlungen aus
der Zeit im alten Programm sind reines Archiv und zaehlen in keiner Auswertung."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base
from app.invoices.models import Kontakt


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Altrechnung(Base):
    __tablename__ = "altrechnungen"
    __table_args__ = (UniqueConstraint("mandant_id", "nummer_hash", name="uq_altrechnung_nummer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    kontakt_id: Mapped[str] = mapped_column(String(36), ForeignKey("kontakte.id"), index=True)
    import_id: Mapped[str] = mapped_column(String(36), ForeignKey("datenimporte.id"), index=True)

    # Die Nummer aus dem Altsystem, wie sie dort stand. Der Hash ist ueber die Ziffern und Buchstaben
    # allein gebildet (ohne Trennzeichen), damit "RE-2024-1" und "RE 2024 1" dieselbe Rechnung sind.
    nummer: Mapped[str] = mapped_column(EncryptedText("altrechnung.nummer"))
    nummer_hash: Mapped[str] = mapped_column(String(64))
    rechnungsdatum: Mapped[date] = mapped_column(Date, index=True)
    faelligkeit: Mapped[date | None] = mapped_column(Date, nullable=True)
    brutto: Mapped[Decimal] = mapped_column(EncryptedDecimal("altrechnung.brutto"))
    # Was beim Umzug noch offen war. 0, wenn die Rechnung im Altsystem schon bezahlt war.
    offen_beim_import: Mapped[Decimal] = mapped_column(EncryptedDecimal("altrechnung.offen_beim_import"))
    # JSON: [{"satz": "19.00", "netto": "...", "ust": "..."}], Summe ergibt den Bruttobetrag.
    steueranteile: Mapped[str] = mapped_column(EncryptedText("altrechnung.steueranteile"))
    # Klartext-Kennzeichen "beim Umzug noch offen", damit Berichte und Bankabgleich nur die wenigen
    # offenen Rechnungen laden und entschluesseln muessen statt das ganze Archiv.
    war_offen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    bezahlt_im_altsystem_am: Mapped[date | None] = mapped_column(Date, nullable=True)

    datei_referenz: Mapped[str | None] = mapped_column(String(500), nullable=True)
    datei_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    datei_hinzugefuegt_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kontakt: Mapped[Kontakt] = relationship()
    zahlungen: Mapped[list["AltrechnungZahlung"]] = relationship(
        back_populates="altrechnung", order_by="AltrechnungZahlung.datum", cascade="all, delete-orphan"
    )


class AltrechnungZahlung(Base):
    """Eine in Bilantiq erfasste Zahlung auf eine Altrechnung. Wie bei Bilantiq-Rechnungen laesst
    sie sich nicht zuruecknehmen."""

    __tablename__ = "altrechnung_zahlungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    altrechnung_id: Mapped[str] = mapped_column(String(36), ForeignKey("altrechnungen.id"), index=True)
    datum: Mapped[date] = mapped_column(Date, index=True)
    betrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("altrechnung_zahlung.betrag"))
    quelle: Mapped[str] = mapped_column(String(12), default="manuell")  # manuell | bankabgleich
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    altrechnung: Mapped[Altrechnung] = relationship(back_populates="zahlungen")
