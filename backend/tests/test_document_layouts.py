"""Regression coverage for every layout, wrapping, pagination and document kind."""
from io import BytesIO
from decimal import Decimal

import pikepdf
import pytest
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from app.core import document_pdf as pdf
from app.core.document_layouts import _wrap, _on_color, _number
from scripts.preview_invoice_designs import sample_arguments, sample_mandant


@pytest.mark.parametrize("template", pdf.GUELTIGE_VORLAGEN)
@pytest.mark.parametrize("variant", pdf.GUELTIGE_VARIANTEN)
def test_all_layouts_render(template, variant):
    mandant = sample_mandant(template)
    mandant.design_variante = variant
    result = pdf.render_document_pdf(mandant, **sample_arguments())
    with pikepdf.open(BytesIO(result)) as doc:
        assert len(doc.pages) == 1


@pytest.mark.parametrize("template", pdf.GUELTIGE_VORLAGEN)
def test_long_descriptions_are_preserved_and_paginated(monkeypatch, template):
    drawn = []
    original = canvas.Canvas.drawString
    original_right = canvas.Canvas.drawRightString

    def record(self, x, y, text, *args, **kwargs):
        drawn.append((self.getPageNumber(), x, y, text))
        return original(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(canvas.Canvas, "drawString", record)
    def record_right(self, x, y, text, *args, **kwargs):
        drawn.append((self.getPageNumber(), x, y, text))
        return original_right(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(canvas.Canvas, "drawRightString", record_right)
    args = sample_arguments()
    words = [f"Leistung{i:04}" for i in range(400)]
    args["positionen"] = [pdf.DocumentPosition(" ".join(words), Decimal(1), Decimal(2200), Decimal(19), "ART-123")]
    mandant = sample_mandant(template)
    mandant.zeige_artikelnummer = True
    result = pdf.render_document_pdf(mandant, **args)
    text = " ".join(t for _, _, _, t in drawn)
    for word in words:
        assert text.count(word) == 1
    with pikepdf.open(BytesIO(result)) as doc:
        assert len(doc.pages) > 1
        for page in range(1, len(doc.pages) + 1):
            assert f"Seite {page} von {len(doc.pages)}" in text
    assert all(50 * mm < y < 260 * mm for _, _, y, t in drawn if "Leistung" in t)


def test_wrap_preserves_unbroken_identifiers():
    c = canvas.Canvas(BytesIO())
    text = "ABCDEFGHIJ" * 20
    lines = _wrap(c, text, "Helvetica", 9, 30 * mm)
    assert "".join(lines) == text
    assert all(c.stringWidth(line, "Helvetica", 9) <= 30 * mm for line in lines)


def test_contrast_and_locale():
    from reportlab.lib import colors
    assert _on_color(colors.yellow) == colors.black
    assert _on_color(colors.darkblue) == colors.white
    assert _number(Decimal("12345.67"), True) == "12.345,67"
    assert _number(Decimal("12345.67"), False) == "12,345.67"


@pytest.mark.parametrize("template", pdf.GUELTIGE_VORLAGEN)
def test_delivery_note_never_prints_prices(monkeypatch, template):
    from app.core import document_layouts
    drawn = []
    original = document_layouts._text

    def record(c, text, *args, **kwargs):
        drawn.append(str(text))
        return original(c, text, *args, **kwargs)

    monkeypatch.setattr(document_layouts, "_text", record)
    a = sample_arguments()
    result = pdf.render_lieferschein_pdf(sample_mandant(template), nummer="LS-142",
        kontakt_name=a["kontakt_name"], kontakt_strasse=a["kontakt_strasse"],
        kontakt_ort_zeile=a["kontakt_ort_zeile"], kontakt_land=a["kontakt_land"],
        lieferdatum=a["datum"], positionen=[pdf.LieferPosition("Designpaket", Decimal(1))])
    assert result.startswith(b"%PDF")
    assert not {"Netto", "USt", "Gesamt", "Einzelpreis"}.intersection(drawn)
