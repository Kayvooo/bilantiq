import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.encrypted_types import EncryptedText
from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Datenimport(Base):
    """Protokoll eines Stammdaten-Imports. Die Quelldatei selbst wird nicht gespeichert
    (Datensparsamkeit), nur ihr Hash und die Zaehler. Angelegte Datensaetze tragen die
    `import_id`, damit der Import rueckgaengig gemacht werden kann."""

    __tablename__ = "datenimporte"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    mandant_id: Mapped[str] = mapped_column(String(36), ForeignKey("mandanten.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    ziel: Mapped[str] = mapped_column(String(20))  # kontakte | produkte | rechnungen
    dateiname: Mapped[str] = mapped_column(EncryptedText("datenimport.dateiname"))
    datei_hash: Mapped[str] = mapped_column(String(64))
    anzahl_neu: Mapped[int] = mapped_column(Integer, default=0)
    anzahl_ergaenzt: Mapped[int] = mapped_column(Integer, default=0)
    anzahl_uebersprungen: Mapped[int] = mapped_column(Integer, default=0)
    anzahl_fehler: Mapped[int] = mapped_column(Integer, default=0)
    # Nur bei Rechnungslisten: verschluesselte Quelldatei als Nachweis der Uebernahme (app/altrechnungen/storage.py).
    datei_referenz: Mapped[str | None] = mapped_column(String(500), nullable=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rueckgaengig_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
