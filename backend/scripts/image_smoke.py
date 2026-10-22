"""Verify the real image's native image, PDF and German OCR dependencies."""
from io import BytesIO

from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract
from reportlab.pdfgen import canvas


def main() -> None:
    image = Image.new("RGB", (800, 200), "white")
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    with Image.open(BytesIO(encoded.getvalue())) as decoded:
        decoded.load()
        assert decoded.size == image.size
    # Blank input exercises the engine without relying on probabilistic text recognition.
    pytesseract.image_to_string(image, lang="deu", timeout=20)
    pdf = BytesIO()
    document = canvas.Canvas(pdf, pagesize=(300, 200))
    document.drawString(20, 100, "Bilantiq runtime check")
    document.save()
    pages = convert_from_bytes(pdf.getvalue(), dpi=72, first_page=1, last_page=1, timeout=20)
    assert len(pages) == 1 and pages[0].size == (300, 200)
    print("Bild-, PDF- und OCR-Laufzeit erfolgreich geprueft.")


if __name__ == "__main__":
    main()
