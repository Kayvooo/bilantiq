from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.auth.models import Mandant
from app.invoices.models import Invoice
from app.mahnwesen.models import Mahnung
from app.mahnwesen.schemas import STUFE_BEZEICHNUNG

_BRIEFTEXT = {
    1: "wir konnten bislang keinen Zahlungseingang zu unten stehender Rechnung feststellen. "
       "Vermutlich haben Sie die Zahlung schlicht vergessen — wir bitten Sie, den offenen "
       "Betrag bis zum neuen Zahlungsziel auszugleichen.",
    2: "trotz unserer Zahlungserinnerung liegt zu unten stehender Rechnung weiterhin kein "
       "Zahlungseingang vor. Wir mahnen den offenen Betrag hiermit an und bitten um Ausgleich "
       "bis zum neuen Zahlungsziel.",
    3: "auch nach unserer 1. Mahnung ist der offene Betrag zu unten stehender Rechnung nicht "
       "beglichen. Wir fordern Sie hiermit letztmalig auf, den Betrag bis zum neuen "
       "Zahlungsziel vollstaendig auszugleichen.",
}


def render_mahnung_pdf(mandant: Mandant, invoice: Invoice, mahnung: Mahnung) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 20 * mm
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, mandant.firmenname)
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    if mandant.adresse:
        c.drawString(left, y, mandant.adresse)
        y -= 8 * mm

    kontakt = invoice.kontakt
    for line in [kontakt.name, kontakt.strasse, f"{kontakt.plz or ''} {kontakt.ort or ''}".strip()]:
        if line:
            c.drawString(left, y, line)
            y -= 4.5 * mm

    y -= 10 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, STUFE_BEZEICHNUNG[mahnung.stufe])

    y -= 10 * mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, "Sehr geehrte Damen und Herren,")
    y -= 8 * mm

    text = c.beginText(left, y)
    text.setFont("Helvetica", 10)
    text.setLeading(13)
    for line in _wrap(_BRIEFTEXT[mahnung.stufe], 90):
        text.textLine(line)
    c.drawText(text)
    y = text.getY() - 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, f"Rechnung {invoice.nummer}")
    y -= 5.5 * mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Offener Betrag: {invoice.brutto_gesamt:.2f} {invoice.waehrung}")
    y -= 5.5 * mm
    if mahnung.mahngebuehr > 0:
        c.drawString(left, y, f"Mahngebuehr: {mahnung.mahngebuehr:.2f} {invoice.waehrung}")
        y -= 5.5 * mm
        gesamt = (invoice.brutto_gesamt + mahnung.mahngebuehr).quantize(Decimal("0.01"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, f"Gesamt faellig: {gesamt:.2f} {invoice.waehrung}")
        y -= 5.5 * mm
        c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Neues Zahlungsziel: {mahnung.neue_faelligkeit.strftime('%d.%m.%Y')}")

    c.showPage()
    c.save()
    return buffer.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
