"""Local filesystem storage for uploaded Briefpapier (letterhead background images) —
same pattern as app/core/branding_storage.py, but no auto-crop: a letterhead is meant
to fill the page as-is, not be trimmed to its visible content like a logo."""
from pathlib import Path

from app.config import settings
from app.core.secure_storage import read_encrypted, write_encrypted
from app.receipts.storage import hash_bytes

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB — ein DIN-A4-Hintergrundbild ist groesser als ein Logo


def _mandant_dir(mandant_id: str) -> Path:
    path = Path(settings.letterhead_storage_dir) / mandant_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(mandant_id: str, mime_type: str, data: bytes) -> str:
    """Schreibt die Datei hash-adressiert und gibt den Pfad relativ zum Storage-Root
    zurueck — der wird als Briefpapier.datei_referenz gespeichert."""
    extension = ALLOWED_MIME_TYPES[mime_type]
    file_hash = hash_bytes(data)
    relative_path = f"{mandant_id}/{file_hash}.{extension}"
    full_path = _mandant_dir(mandant_id) / f"{file_hash}.{extension}"
    if not full_path.exists():
        write_encrypted(settings.letterhead_storage_dir, relative_path, data, purpose_prefix="letterhead-file")
    return relative_path


def read(relative_path: str) -> bytes:
    return read_encrypted(settings.letterhead_storage_dir, relative_path, purpose_prefix="letterhead-file")
