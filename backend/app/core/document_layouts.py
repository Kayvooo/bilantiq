"""Print-first layouts with measured rows and a shared, deterministic page plan.

Existing template IDs are retained. Layout decoration never changes invoice data.
Coordinates in this module run from the top edge of the A4 sheet.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas
    from app.core.document_pdf import _DocContext

INK = colors.HexColor("#20282C")
MUTED = colors.HexColor("#65717A")
LINE = colors.HexColor("#DCE2E5")
PAPER = colors.HexColor("#F4F6F7")
W, H = A4


def _wrap(c, text, font, size, width):
    """Preserve all text, including explicit breaks and long unspaced identifiers."""
    result = []
    for paragraph in str(text or "").split("\n"):
        line = ""
        for word in paragraph.split():
            if line and c.stringWidth(line + " " + word, font, size) > width:
                result.append(line)
                line = ""
            while c.stringWidth(word, font, size) > width:
                end = 1
                while end < len(word) and c.stringWidth(word[:end + 1], font, size) <= width:
                    end += 1
                result.append(word[:end])
                word = word[end:]
            line = (line + " " + word).strip()
        result.append(line)
    return result or [""]


def _text(c, text, x, top, size=9, font="Helvetica", color=INK, right=False):
    c.setFont(font, size)
    c.setFillColor(color)
    (c.drawRightString if right else c.drawString)(x, H - top, str(text))


def _block(c, lines, x, top, size=9, font="Helvetica", color=INK, leading=4.6 * mm):
    for line in lines:
        _text(c, line, x, top, size, font, color)
        top += leading
    return top


def _rect(c, x, top, width, height, color):
    c.setFillColor(color)
    c.rect(x, H - top - height, width, height, stroke=0, fill=1)


def _rule(c, x, right, top, color=LINE, weight=0.5):
    c.setStrokeColor(color)
    c.setLineWidth(weight)
    c.line(x, H - top, right, H - top)


def _tint(color, strength=0.08):
    return colors.Color(*(1 - (1 - v) * strength for v in (color.red, color.green, color.blue)))


def _on_color(color):
    # Contrast against arbitrary customer accents, including very light yellows.
    def linear(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    luminance = sum(linear(v) * k for v, k in zip((color.red, color.green, color.blue), (.2126, .7152, .0722)))
    return colors.black if luminance > .179 else colors.white


def _number(value, german):
    value = f"{Decimal(value):,.2f}"
    return value.replace(",", "_").replace(".", ",").replace("_", ".") if german else value


@dataclass
class _Fragment:
    cells: list[list[str]]
    height: float
    index: int


def render_layout(c: "Canvas", ctx: "_DocContext", template: str) -> None:
    # Runtime import keeps the public document API and shared QR/logo helpers intact.
    from app.core import document_pdf as pdf

    german = (ctx.mandant.sprache or "de") == "de"
    compact = template == "kompakt"
    serif = template == "elegant"
    font = "Times-Roman" if serif else "Courier" if template == "mono" else "Helvetica"
    bold = "Times-Bold" if serif else "Courier-Bold" if template == "mono" else "Helvetica-Bold"
    size = 8 if compact else 9
    leading = (4 if compact else 4.8) * mm
    left = (25 if template == "seitenleiste" else 18) * mm
    right = 192 * mm
    width = right - left
    accent = INK if template in ("klassisch", "minimal", "mono") else ctx.akzent
    text_accent = INK if _on_color(accent) == colors.black else accent
    colored = template in ("modern", "balken", "kachel") and not ctx.reduziert
    money = lambda value: f"{_number(value, german)} {ctx.waehrung}"
    label = lambda key: pdf._t(ctx, key)
    date_label = lambda value: value.strftime("%d.%m.%Y") if german else value.isoformat()

    footer_lines = []
    if ctx.mandant.zeige_fusszeile and ctx.fusszeile_text:
        footer_lines = _wrap(c, ctx.fusszeile_text, font, 8, width)
    footer_top = H - 18 * mm - max(0, len(footer_lines) - 1) * 3.8 * mm
    table_bottom = min(H - 57 * mm, footer_top - (44 if ctx.mit_preisen else 10) * mm)

    def decoration():
        pdf._briefpapier_hintergrund(c, ctx.mandant)
        if ctx.reduziert:
            return
        if template == "seitenleiste":
            _rect(c, 0, 0, 9 * mm, H, accent)
            p = c.beginPath()
            p.moveTo(9 * mm, H)
            p.curveTo(25 * mm, H - 35 * mm, 2 * mm, H - 72 * mm, 16 * mm, H - 115 * mm)
            p.lineTo(9 * mm, 0)
            p.close()
            c.setFillColor(_tint(accent, .28))
            c.drawPath(p, stroke=0, fill=1)
        elif template == "rahmen":
            c.setStrokeColor(accent)
            c.setLineWidth(.7)
            c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm, stroke=1, fill=0)
        elif template == "stempel":
            c.saveState()
            c.translate(W / 2, H / 2)
            c.rotate(35)
            c.setFillColor(_tint(accent, .055))
            mark = label(ctx.titel_prefix)
            mark_size = min(76, 480 / max(c.stringWidth(mark, bold, 1), 1))
            c.setFont(bold, mark_size)
            c.drawCentredString(0, 0, mark)
            c.restoreState()
        elif template == "modern":
            _rect(c, left, 0, 34 * mm, 3 * mm, accent)

    def first_header():
        title = ctx.titel_override or label(ctx.titel_prefix)
        if template == "minimal" and not ctx.titel_override:
            title = title.upper()
        title_size = 29 if template == "minimal" else 27 if serif else 23
        title_lines = _wrap(c, title, bold, title_size, width)
        logo = pdf._logo_bild(ctx.mandant)
        logo_w, logo_h = 32 * mm * ctx.logo_faktor, 17 * mm * ctx.logo_faktor
        sender_top = (20 if compact else 24) * mm
        sender_name = _wrap(c, ctx.mandant.firmenname, bold, 13, width - 62 * mm)
        sender_address = _wrap(c, ctx.mandant.adresse, font, 8.5, width - 62 * mm) if ctx.mandant.adresse else []
        sender_height = len(sender_name) * 5.8 * mm + (2 * mm + len(sender_address) * 4.2 * mm if sender_address else 0)
        band_height = max(53 * mm, sender_top + sender_height + 6 * mm) if ctx.mandant.zeige_absenderzeile else 53 * mm
        if template == "balken" and not ctx.reduziert:
            _rect(c, 0, 0, W, band_height, accent)
            header_color = _on_color(accent)
        else:
            header_color = text_accent
        sender_end = sender_top
        if ctx.mandant.zeige_absenderzeile:
            sender_end = _block(c, sender_name, left, sender_top, 13, bold, header_color, 5.8 * mm)
            if sender_address:
                sender_end = _block(c, sender_address, left, sender_end + 2 * mm, 8.5, font, header_color, 4.2 * mm)
        pdf._zeichne_logo(c, logo, right - logo_w, H - 17 * mm - logo_h, logo_w, logo_h, karte=template == "balken" and not ctx.reduziert)
        top = max((66 if template == "balken" else 59 if template == "minimal" else 44 if compact else 52) * mm, sender_end + (8 if compact else 13) * mm)
        if template == "balken" and not ctx.reduziert:
            top = max(top, band_height + 13 * mm)
        if template == "kachel" and not ctx.reduziert:
            title_height = len(title_lines) * (title_size + 4) + 10 * mm
            _rect(c, left - 3 * mm, top - 10 * mm, width + 3 * mm, title_height, _tint(accent))
        top = _block(c, title_lines, left, top, title_size, bold, text_accent, (title_size + 4))
        if ctx.ist_entwurf:
            top = _block(c, [label(ctx.entwurf_hinweis)], left, top + 1 * mm, 8, font, MUTED)
        if template in ("klassisch", "elegant", "rahmen", "mono"):
            _rule(c, left, right, top + 2 * mm, accent, .6)
        top += (10 if compact else 14) * mm
        address_width = width - 87 * mm
        _text(c, "Rechnung an" if german and ctx.titel_prefix == "rechnung" else label("empfaenger"), left, top, 8, font, MUTED)
        recipient = _block(c, _wrap(c, ctx.kontakt_name, bold, 10, address_width), left, top + 6 * mm, 10, bold)
        for text in (ctx.kontakt_strasse, ctx.kontakt_ort_zeile, ctx.kontakt_land):
            if text:
                recipient = _block(c, _wrap(c, text, font, 9, address_width), left, recipient, 9, font)
        for key, value, enabled in (("kundennummer", ctx.kundennummer, ctx.mandant.zeige_kundennummer), ("kontaktperson", ctx.kontaktperson, ctx.mandant.zeige_kontaktperson)):
            if enabled and value:
                recipient = _block(c, _wrap(c, f"{label(key)}: {value}", font, 8, address_width), left, recipient + 2 * mm, 8, font)
        meta_x = right - 73 * mm
        meta = [("Nummer" if german else "Number", ctx.nummer or ("Entwurf" if german else "Draft")), (label(ctx.datum_label), date_label(ctx.datum))]
        if ctx.folgedatum and ctx.folgedatum_label:
            meta.append((label(ctx.folgedatum_label), date_label(ctx.folgedatum)))
        meta_top = top
        for key, value in meta:
            lines = _wrap(c, value, bold, 8.5, 37 * mm)
            row_height = max(9 * mm, len(lines) * 4.6 * mm + 4 * mm)
            if template in ("modern", "kachel", "rahmen") and not ctx.reduziert:
                _rect(c, meta_x - 3 * mm, meta_top - 4 * mm, 76 * mm, row_height, _tint(accent))
            _text(c, key, meta_x, meta_top, 8, font, MUTED)
            for i, line in enumerate(lines):
                _text(c, line, right - 2 * mm, meta_top + i * 4.6 * mm, 8.5, bold, INK, True)
            meta_top += row_height
        return max(recipient, meta_top) + (12 if compact else 17) * mm

    # Measure first-page header once; actual pages are emitted after planning rows.
    # A scratch canvas prevents duplicate header operations in the output PDF.
    from io import BytesIO
    from reportlab.pdfgen.canvas import Canvas
    output_canvas = c
    c = Canvas(BytesIO(), pagesize=A4)
    first_top = first_header()
    c = output_canvas

    # Use flexible description space, even with article numbers enabled.
    numeric = [("menge", 16 * mm)]
    if ctx.mit_preisen:
        numeric += [("einzelpreis", 26 * mm)]
        if ctx.mandant.zeige_ust_pro_position:
            numeric += [("ust_prozent", 17 * mm)]
        numeric += [("gesamt", 32 * mm)]
    columns = []
    if ctx.mandant.zeige_artikelnummer:
        columns.append(("artikelnummer", 22 * mm))
    columns.append(("beschreibung", width - sum(w for _, w in numeric) - sum(w for _, w in columns)))
    columns += numeric
    row_cells = []
    for index, row in enumerate(ctx.zeilen):
        values = {
            "artikelnummer": row.artikelnummer or "",
            "beschreibung": row.beschreibung if ctx.mandant.zeige_positionsbeschreibung else "",
            "menge": _number(row.menge, german),
        }
        if ctx.mit_preisen:
            values.update(einzelpreis=_number(row.einzelpreis, german), ust_prozent=_number(row.ust_satz, german), gesamt=money((row.menge * row.einzelpreis).quantize(Decimal("0.01"))))
        cells = [_wrap(c, values[key], font, size, col_width - 5 * mm) for key, col_width in columns]
        row_cells.append((index, cells))

    continuation_top = 40 * mm
    pages: list[list[_Fragment]] = [[]]
    starts = [first_top]
    used = first_top + 12 * mm
    for index, cells in row_cells:
        offset = 0
        count = max(map(len, cells))
        while offset < count:
            capacity = int((table_bottom - used - 5 * mm) / leading)
            if capacity < 1:
                pages.append([])
                starts.append(continuation_top)
                used = continuation_top + 12 * mm
                capacity = int((table_bottom - used - 5 * mm) / leading)
                if capacity < 1:
                    raise ValueError("Fußzeile ist zu lang für eine A4-Seite. Bitte kürzen.")
            # Keep ordinary rows together; split only rows taller than a full page.
            full_capacity = int((table_bottom - continuation_top - 17 * mm) / leading)
            if offset == 0 and count > capacity and count <= full_capacity:
                pages.append([])
                starts.append(continuation_top)
                used = continuation_top + 12 * mm
                continue
            take = min(capacity, count - offset)
            height = take * leading + 5 * mm
            pages[-1].append(_Fragment([cell[offset:offset + take] for cell in cells], height, index))
            used += height
            offset += take

    def table_header(top):
        if colored:
            _rect(c, left, top - 4.8 * mm, width, 10 * mm, accent)
        elif template in ("kompakt", "rahmen", "stempel") and not ctx.reduziert:
            _rect(c, left, top - 4.8 * mm, width, 10 * mm, PAPER)
        else:
            _rule(c, left, right, top + 4 * mm, accent, .7)
        x = left
        for key, col_width in columns:
            align_right = key not in ("beschreibung", "artikelnummer")
            caption = label(key) if key != "beschreibung" or ctx.mandant.zeige_positionsbeschreibung else ""
            _text(c, caption, x + col_width - 2.5 * mm if align_right else x + 2.5 * mm, top + 1 * mm, 7.5, bold, _on_color(accent) if colored else INK, align_right)
            x += col_width

    for page_index, fragments in enumerate(pages):
        if page_index:
            c.showPage()
        decoration()
        if page_index == 0:
            first_header()
        else:
            if ctx.mandant.zeige_absenderzeile:
                _text(c, pdf._kuerzen(c, ctx.mandant.firmenname, bold, 10, width / 2), left, 23 * mm, 10, bold, text_accent)
            _text(c, f"{ctx.nummer or label(ctx.titel_prefix)} · {label('fortsetzung')}", right, 23 * mm, 8, font, MUTED, True)
            _rule(c, left, right, 29 * mm)
        top = starts[page_index]
        table_header(top)
        top += 12 * mm
        for fragment in fragments:
            if template in ("modern", "kompakt", "rahmen") and fragment.index % 2 == 0 and not ctx.reduziert:
                _rect(c, left, top - 4 * mm, width, fragment.height, _tint(accent, .035))
            x = left
            for (key, col_width), lines in zip(columns, fragment.cells):
                align_right = key not in ("beschreibung", "artikelnummer")
                for i, line in enumerate(lines):
                    _text(c, line, x + col_width - 2.5 * mm if align_right else x + 2.5 * mm, top + i * leading, size, font, INK, align_right)
                x += col_width
            top += fragment.height
            _rule(c, left, right, top - 4 * mm)

        if page_index == len(pages) - 1 and ctx.mit_preisen:
            total_x = right - 76 * mm
            top += 8 * mm
            _text(c, label("netto"), total_x, top, 9, font, MUTED)
            _text(c, money(ctx.netto_gesamt), right - 2.5 * mm, top, 9, font, INK, True)
            top += 7 * mm
            _text(c, label("ust"), total_x, top, 9, font, MUTED)
            _text(c, money(ctx.ust_gesamt), right - 2.5 * mm, top, 9, font, INK, True)
            top += 10 * mm
            if template in ("modern", "balken", "kachel", "seitenleiste") and not ctx.reduziert:
                _rect(c, total_x - 4 * mm, top - 6 * mm, right - total_x + 4 * mm, 13 * mm, accent)
                total_color = _on_color(accent)
            else:
                _rule(c, total_x, right, top - 6 * mm, accent, .8)
                total_color = text_accent
            _text(c, label("gesamt"), total_x, top + 2 * mm, 11, bold, total_color)
            _text(c, money(ctx.brutto_gesamt), right - 2.5 * mm, top + 2 * mm, 12, bold, total_color, True)
            pdf._zeichne_girocode(c, ctx, x=left, y=H - top - 5 * mm)

        if footer_lines:
            _rule(c, left, right, footer_top - 6 * mm)
            _block(c, footer_lines, left, footer_top, 8, font, MUTED, 3.8 * mm)
        pdf._seitenende(c, ctx, seite_nr=page_index + 1, gesamt_seiten=len(pages))
