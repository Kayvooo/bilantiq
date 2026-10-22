"""Local filesystem storage for original receipt files.

Good enough for local dev and a single-instance deployment; swap for S3/object
storage before running more than one backend instance (nothing else in this
module assumes a filesystem — routes.py only calls save/read/path_for)."""
import hashlib
import os
from pathlib import Path

from app.config import settings
from app.core.secure_storage import read_encrypted, write_encrypted

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "application/xml": "xml",  # E-Rechnung (XRechnung), wird nicht per OCR gelesen
}


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mandant_dir(mandant_id: str) -> Path:
    path = Path(settings.receipt_storage_dir) / mandant_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(mandant_id: str, file_hash: str, mime_type: str, data: bytes) -> str:
    """Writes the file if not already present (hash-addressed, so re-uploads of the
    same bytes never duplicate storage) and returns the path relative to the storage
    root — that relative path is what gets stored as Receipt.datei_referenz."""
    extension = ALLOWED_MIME_TYPES[mime_type]
    relative_path = f"{mandant_id}/{file_hash}.{extension}"
    full_path = _mandant_dir(mandant_id) / f"{file_hash}.{extension}"
    if not full_path.exists():
        write_encrypted(settings.receipt_storage_dir, relative_path, data, purpose_prefix="receipt-file")
    return relative_path


def read(relative_path: str) -> bytes:
    return read_encrypted(settings.receipt_storage_dir, relative_path, purpose_prefix="receipt-file")


def absolute_path(relative_path: str) -> str:
    """Nur fuer Diagnose/Storage-Verwaltung. Der Pfad zeigt auf Ciphertext, nicht Klartext."""
    return os.path.join(settings.receipt_storage_dir, relative_path)


_MIME_BY_SUFFIX = {f".{extension}": mime for mime, extension in ALLOWED_MIME_TYPES.items()}


def mime_type_for_reference(relative_path: str) -> str:
    """Ermittelt den gespeicherten MIME-Typ aus der von save() vergebenen Endung."""
    return _MIME_BY_SUFFIX.get(Path(relative_path).suffix.lower(), "application/octet-stream")
