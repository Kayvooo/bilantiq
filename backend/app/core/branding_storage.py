"""Local filesystem storage for uploaded Mandant-Logos — same pattern as
app/receipts/storage.py (hash-addressed, mandant-scoped directories), kept as its own
module/config dir rather than reused directly since a logo is not a receipt."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops

from app.config import settings
from app.core.secure_storage import read_encrypted, write_encrypted
from app.receipts.storage import hash_bytes

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_PIL_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
MAX_BYTES = 2 * 1024 * 1024  # 2 MB reicht fuer ein Logo bei weitem, haelt PDFs klein


def _mandant_dir(mandant_id: str) -> Path:
    path = Path(settings.branding_storage_dir) / mandant_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auto_zuschneiden(data: bytes, mime_type: str) -> bytes:
    """Schneidet ueberschuessigen transparenten/weissen Rand um das eigentliche
    Motiv weg, bevor gespeichert wird — sonst wirkt ein Logo in der PDF-Box winzig,
    wenn die hochgeladene Datei selbst schon viel Weissraum enthaelt. Bewusst
    konservativ: jeder Fehler laesst die Originaldatei unveraendert durch, ein
    Upload darf daran nie scheitern."""
    try:
        bild = Image.open(BytesIO(data))
        bild.load()
        if bild.mode in ("RGBA", "LA") or (bild.mode == "P" and "transparency" in bild.info):
            alpha = bild.convert("RGBA").split()[-1]
            box = alpha.getbbox()
        else:
            rgb = bild.convert("RGB")
            hintergrund = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
            box = ImageChops.difference(rgb, hintergrund).getbbox()
        if box is None:
            return data
        rand = 2  # Px Sicherheitsabstand, damit Kanten nicht hart angeschnitten wirken
        x0, y0, x1, y1 = box
        box = (max(0, x0 - rand), max(0, y0 - rand), min(bild.width, x1 + rand), min(bild.height, y1 + rand))
        if box == (0, 0, bild.width, bild.height):
            return data
        zugeschnitten = bild.crop(box)
        ausgabe = BytesIO()
        zugeschnitten.save(ausgabe, format=_PIL_FORMAT[mime_type])
        return ausgabe.getvalue()
    except Exception:
        return data


def save(mandant_id: str, mime_type: str, data: bytes) -> str:
    """Schreibt die Datei hash-adressiert (Re-Uploads derselben Bytes duplizieren
    nichts) und gibt den Pfad relativ zum Storage-Root zurueck — der wird als
    Mandant.logo_referenz gespeichert."""
    data = _auto_zuschneiden(data, mime_type)
    extension = ALLOWED_MIME_TYPES[mime_type]
    file_hash = hash_bytes(data)
    relative_path = f"{mandant_id}/{file_hash}.{extension}"
    full_path = _mandant_dir(mandant_id) / f"{file_hash}.{extension}"
    if not full_path.exists():
        write_encrypted(settings.branding_storage_dir, relative_path, data, purpose_prefix="branding-file")
    return relative_path


def read(relative_path: str) -> bytes:
    return read_encrypted(settings.branding_storage_dir, relative_path, purpose_prefix="branding-file")
