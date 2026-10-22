"""Verschluesselte Ablage fuer Rechnungs-PDFs aus dem Altsystem und die Quelldatei der Rechnungsliste.

PDFs sind hash-adressiert (`{mandant}/{hash}.pdf`). Die Quelldatei einer Rechnungsliste liegt als
`{mandant}/import-{hash}.{endung}` getrennt davon, damit sie sich mit dem Import wieder entfernen
laesst, ohne ein PDF zu treffen."""
from __future__ import annotations

import os
from pathlib import Path

from app.config import settings
from app.core.secure_storage import read_encrypted, write_encrypted

PURPOSE = "altrechnung-file"


def speichere_pdf(mandant_id: str, datei_hash: str, daten: bytes) -> str:
    relativ = f"{mandant_id}/{datei_hash}.pdf"
    write_encrypted(settings.altrechnung_storage_dir, relativ, daten, purpose_prefix=PURPOSE)
    return relativ


def speichere_importdatei(mandant_id: str, datei_hash: str, endung: str, daten: bytes) -> str:
    relativ = f"{mandant_id}/import-{datei_hash}.{endung}"
    write_encrypted(settings.altrechnung_storage_dir, relativ, daten, purpose_prefix=PURPOSE)
    return relativ


def lies(relativ: str) -> bytes:
    return read_encrypted(settings.altrechnung_storage_dir, relativ, purpose_prefix=PURPOSE)


def loesche_importdatei(relativ: str) -> None:
    """Nur fuer Quelldateien von Rechnungslisten (Name beginnt mit `import-`), nie fuer PDFs."""
    if not Path(relativ).name.startswith("import-"):
        raise ValueError("Nur Quelldateien eines Imports duerfen geloescht werden.")
    voll = Path(settings.altrechnung_storage_dir).resolve() / relativ
    if Path(settings.altrechnung_storage_dir).resolve() in voll.resolve().parents and voll.exists():
        os.remove(voll)
