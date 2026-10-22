import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.core.encrypted_types import EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Produkt(Base):
    __tablename__ = "produkte"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    bezeichnung: Mapped[str] = mapped_column(EncryptedText("produkt.bezeichnung"))
    beschreibung: Mapped[str | None] = mapped_column(EncryptedText("produkt.beschreibung"), nullable=True)
    einzelpreis: Mapped[Decimal] = mapped_column(EncryptedDecimal("produkt.einzelpreis"))
    ust_satz: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    einheit: Mapped[str] = mapped_column(EncryptedText("produkt.einheit"))
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    # Opt-in pro Produkt: viele Produkte sind Dienstleistungen (Einheit "Stunde" o.ae.)
    # ohne sinnvollen Bestandsbegriff, daher kein automatisches Tracking fuer jede Zeile.
    lagerbestand_aktiv: Mapped[bool] = mapped_column(Boolean, default=False)
    artikelnummer: Mapped[str | None] = mapped_column(EncryptedText("produkt.artikelnummer"), nullable=True)
    import_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("datenimporte.id"), index=True, nullable=True)


class Lagerbewegung(Base):
    """Manuelle Lagerbuchung (Wareneingang/Warenausgang) zu einem Produkt. Immutable wie
    KassenbuchEintrag: kein Update-/Delete-Endpunkt, eine Fehlbuchung wird durch eine
    Gegenbuchung korrigiert, nicht durch nachtraegliches Aendern/Loeschen der urspruenglichen
    Bewegung. Der aktuelle Lagerbestand wird nirgends gespeichert, sondern aus dieser Tabelle
    aufsummiert (zugang positiv, abgang negativ) -- siehe _lagerbestand() in routes.py."""

    __tablename__ = "lagerbewegungen"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    produkt_id: Mapped[str] = mapped_column(String(36), ForeignKey("produkte.id"), index=True)
    datum: Mapped[date] = mapped_column(Date)
    typ: Mapped[str] = mapped_column(String(10))  # zugang | abgang
    menge: Mapped[Decimal] = mapped_column(EncryptedDecimal("lagerbewegung.menge"))  # immer positiv, typ gibt die Richtung vor
    grund: Mapped[str] = mapped_column(EncryptedText("lagerbewegung.grund"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
