import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KassenbuchEintrag(Base):
    """Manuelles Kassenbuch fuer Bar-Ein-/Auszahlungen — kein finAPI/Bankanbindung
    noetig, das ist bewusst ausgeklammert (siehe CLAUDE.md). GoBD verlangt eine
    taggenaue, lueckenlose, nicht nachtraeglich veraenderbare Kassenfuehrung, daher
    immutable wie Invoice/Ausgabe: kein Update-/Delete-Endpunkt, ein Fehlbuchung wird
    durch eine Gegenbuchung korrigiert, nicht durch Aendern des Eintrags."""

    __tablename__ = "kassenbuch_eintraege"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    datum: Mapped[date] = mapped_column(Date)
    typ: Mapped[str] = mapped_column(String(10))  # einnahme | ausgabe
    betrag: Mapped[Decimal] = mapped_column(EncryptedDecimal("kassenbuch.betrag"))  # immer positiv, typ gibt die Richtung vor
    beschreibung: Mapped[str] = mapped_column(EncryptedText("kassenbuch.beschreibung"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
