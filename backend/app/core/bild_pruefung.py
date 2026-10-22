"""Pruefung hochgeladener Bilder (Logo, Briefpapier) anhand des Inhalts.

Der vom Client gemeldete Content-Type ist nur eine Behauptung. Geprueft wird deshalb:

1. Magic Bytes (PNG/JPEG/WebP) -- der erkannte Typ ersetzt den behaupteten,
2. Pillow kann die Datei wirklich lesen (``verify`` + erneutes Oeffnen), das Format passt zu den Magic Bytes,
3. die Pixelzahl bleibt begrenzt (Dekompressionsbombe: wenige KB PNG koennen Milliarden Pixel entpacken und beim
   Zuschneiden bzw. beim Einbetten ins PDF den Arbeitsspeicher fuellen).

SVG und andere Formate sind bewusst nicht erlaubt (SVG kann Skripte und externe Verweise enthalten).
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_PIXEL = 25_000_000  # ~5000 x 5000; ein A4-Briefpapier mit 300 dpi hat rund 8,7 Mio. Pixel

_FORMAT_ZU_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class UngueltigesBild(ValueError):
    """Die Datei ist kein erlaubtes, sicher lesbares Bild."""


def erkenne_bildtyp(daten: bytes) -> str | None:
    if daten.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if daten.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if daten[:4] == b"RIFF" and daten[8:12] == b"WEBP":
        return "image/webp"
    return None


def pruefe_bild(daten: bytes, erlaubte_typen: set[str] | frozenset[str]) -> str:
    """Gibt den aus dem Inhalt erkannten MIME-Typ zurueck oder wirft ``UngueltigesBild``."""
    typ = erkenne_bildtyp(daten)
    if typ is None or typ not in erlaubte_typen:
        raise UngueltigesBild("Dateityp wird nicht unterstuetzt (erlaubt: JPEG, PNG, WebP).")
    try:
        with Image.open(BytesIO(daten)) as bild:
            if _FORMAT_ZU_MIME.get(bild.format or "") != typ:
                raise UngueltigesBild("Der Dateiinhalt passt nicht zum Dateityp.")
            if bild.width * bild.height > MAX_PIXEL:
                raise UngueltigesBild(f"Das Bild ist zu gross (maximal {MAX_PIXEL // 1_000_000} Megapixel).")
            bild.verify()
        with Image.open(BytesIO(daten)) as bild:
            bild.load()  # entpackt wirklich -- beschaedigte oder abgeschnittene Dateien scheitern hier
    except UngueltigesBild:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UngueltigesBild("Die Bilddatei ist beschaedigt oder nicht lesbar.") from exc
    return typ
