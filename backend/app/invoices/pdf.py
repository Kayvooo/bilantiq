"""Invoice PDF rendering (via the shared layout in app/core/document_pdf.py), plus a
best-effort ZUGFeRD-style hybrid.

Honest limitation: real ZUGFeRD/Factur-X expects the embedded XML in UN/CEFACT CII
format and a PDF/A-3 container (specific color profile + XMP metadata). We only
generate UBL (for XRechnung) and attach that same XML here rather than building a
second CII generator with nothing to validate it against. A strict ZUGFeRD reader will
not accept this file as-is — treat the output as a working PDF with the e-invoice data
attached for convenience, not a certified Factur-X/ZUGFeRD document. Building a real
CII generator and validating both against veraPDF/KoSIT is follow-up work, not silently
claimed here.

Stand der Pruefung: Das angehaengte UBL-XML wird vor der Auslieferung gegen XSD und Schematron der
KoSIT-XRechnung-Konfiguration geprueft (app/invoices/e_invoice_validation.py, Saxon, nicht der
Original-Validator). Das gilt nur fuer das XML. Der PDF/A-3-Container ist nicht geprueft (kein veraPDF),
und CII wird nicht erzeugt, also ist das Ergebnis weiterhin kein zertifiziertes ZUGFeRD/Factur-X.
"""
from io import BytesIO

import pikepdf

from app.auth.models import Mandant
from app.core.crypto import decrypt_field
from app.core.document_pdf import DocumentPosition, render_document_pdf
from app.invoices.models import Invoice


def _fusstext_aufloesen(invoice: Invoice) -> str | None:
    """[%ZAHLUNGSZIEL%]/[%KONTAKTPERSON%] sind Platzhalter, die im frei getippten
    Fusstext (siehe InvoiceEditor) auf die tatsaechlichen Werte dieser Rechnung
    aufgeloest werden -- kopftext wird bewusst noch nicht ins PDF gezeichnet (siehe
    Invoice-Model-Docstring), nur betreff/fusstext wirken sich hier aus."""
    if not invoice.fusstext:
        return None
    kontaktperson = decrypt_field(invoice.interne_kontaktperson.email_encrypted) if invoice.interne_kontaktperson else ""
    return (
        invoice.fusstext
        .replace("[%ZAHLUNGSZIEL%]", invoice.faelligkeitsdatum.strftime("%d.%m.%Y"))
        .replace("[%KONTAKTPERSON%]", kontaktperson)
    )


def render_invoice_pdf(mandant: Mandant, invoice: Invoice) -> bytes:
    kontakt = invoice.kontakt
    kontaktperson = decrypt_field(invoice.interne_kontaktperson.email_encrypted) if invoice.interne_kontaktperson else None
    return render_document_pdf(
        mandant,
        titel_prefix="rechnung",
        nummer=invoice.nummer,
        ist_entwurf=invoice.status == "entwurf",
        entwurf_hinweis="entwurf_hinweis",
        kontakt_name=kontakt.name,
        kontakt_strasse=kontakt.strasse,
        kontakt_ort_zeile=f"{kontakt.plz or ''} {kontakt.ort or ''}".strip(),
        kontakt_land=kontakt.land,
        datum_label="leistungsdatum",
        datum=invoice.leistungsdatum,
        folgedatum_label="zahlungsziel",
        folgedatum=invoice.faelligkeitsdatum,
        positionen=[
            DocumentPosition(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz, artikelnummer=p.artikelnummer)
            for p in invoice.positionen
        ],
        waehrung=invoice.waehrung,
        netto_gesamt=invoice.netto_gesamt,
        ust_gesamt=invoice.ust_gesamt,
        brutto_gesamt=invoice.brutto_gesamt,
        titel_override=invoice.betreff,
        fusszeile_override=_fusstext_aufloesen(invoice),
        kundennummer=kontakt.kundennummer,
        kontaktperson=kontaktperson,
    )


def attach_e_invoice_xml(pdf_bytes: bytes, *, xml_bytes: bytes, filename: str = "xrechnung.xml") -> bytes:
    with pikepdf.Pdf.open(BytesIO(pdf_bytes)) as pdf:
        pdf.attachments[filename] = xml_bytes
        out = BytesIO()
        pdf.save(out)
        return out.getvalue()
