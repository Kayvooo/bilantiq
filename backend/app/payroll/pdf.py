from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.auth.models import Mandant
from app.core.crypto import decrypt_field
from app.payroll.models import LohnMonatsentwurf, Mitarbeiter

_MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def render_lohnzettel_pdf(mandant: Mandant, mitarbeiter: Mitarbeiter, entwurf: LohnMonatsentwurf, hinweis: str) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 20 * mm
    right = width - 20 * mm
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, mandant.firmenname)
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    if mandant.adresse:
        c.drawString(left, y, mandant.adresse)
        y -= 8 * mm

    name = f"{decrypt_field(mitarbeiter.vorname_encrypted)} {decrypt_field(mitarbeiter.nachname_encrypted)}"
    c.drawString(left, y, name)
    y -= 4.5 * mm
    c.drawString(left, y, f"Personalnummer {mitarbeiter.personalnummer}")

    y -= 15 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, f"Lohnvorbereitung {_MONATSNAMEN[entwurf.monat - 1]} {entwurf.jahr}")

    y -= 12 * mm
    zeilen = [
        ("Grundbrutto", entwurf.grundbrutto),
        ("Steuerpflichtige Zuschläge", entwurf.steuerpflichtige_zuschlaege),
        ("Steuerfreie Erstattungen", entwurf.steuerfreie_erstattungen),
        ("Sonstige Abzüge", -entwurf.sonstige_abzuege),
    ]
    c.setFont("Helvetica", 10)
    for label, betrag in zeilen:
        c.drawString(left, y, label)
        c.drawRightString(right, y, f"{betrag:.2f} EUR")
        y -= 6 * mm

    y -= 2 * mm
    c.line(left, y, right, y)
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Gesamtbrutto")
    c.drawRightString(right, y, f"{entwurf.gesamtbrutto:.2f} EUR")
    y -= 6 * mm
    c.drawString(left, y, "Zwischensumme vor gesetzlichen Abgaben")
    c.drawRightString(right, y, f"{entwurf.zwischenbetrag_vor_abgaben:.2f} EUR")

    y -= 16 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Hinweis")
    y -= 5.5 * mm
    text = c.beginText(left, y)
    text.setFont("Helvetica", 9)
    text.setLeading(12)
    for line in _wrap(hinweis, 95):
        text.textLine(line)
    c.drawText(text)

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
