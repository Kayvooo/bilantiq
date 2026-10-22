"""Shared PDF document data and branding helpers.

Eleven print-first layouts are implemented in document_layouts.py. All callers
retain the same document API, tenant settings and subscription restrictions.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.auth.models import Mandant
from app.core import branding_storage, letterhead_storage

FUSSZEILE_Y = 15 * mm
SEKUNDAERFARBE = colors.HexColor("#526258")  # Bilantiq-Sekundaertext (--bq-muted), siehe brand.css
KURATIERTES_BLAU = "#2557D6"

# Bilantiq-Waldgrün (--bq-forest) aus frontend/src/styles/brand.css — Standardakzent, wenn der Mandant
# keine eigene Farbe gewaehlt hat.
STANDARD_AKZENTFARBE = "#143D2B"
GUELTIGE_VORLAGEN = ("klassisch", "modern", "minimal", "kompakt", "elegant", "balken", "seitenleiste", "rahmen", "kachel", "mono", "stempel")
GUELTIGE_VARIANTEN = ("standard", "schwarz", "blau", "einfach")
GUELTIGE_LOGO_GROESSEN = ("S", "M", "L")
_LOGO_FAKTOR = {"S": 0.7, "M": 1.0, "L": 1.3}

# Alle festen Dokumenttexte, De/En -- siehe _t(). Muss synchron bleiben mit den
# i18n-Schluesseln, die app/invoices/pdf.py, app/quotes/pdf.py und
# app/auftraege/pdf.py als titel_prefix/datum_label/folgedatum_label/entwurf_hinweis
# uebergeben (keine literalen deutschen Strings mehr an dieser Schnittstelle).
_TEXTE: dict[str, dict[str, str]] = {
    "beschreibung": {"de": "Beschreibung", "en": "Description"},
    "menge": {"de": "Menge", "en": "Qty"},
    "einzelpreis": {"de": "Einzelpreis", "en": "Unit Price"},
    "ust_prozent": {"de": "USt %", "en": "VAT %"},
    "gesamt": {"de": "Gesamt", "en": "Total"},
    "artikelnummer": {"de": "Art.-Nr.", "en": "Item No."},
    "empfaenger": {"de": "Empfaenger", "en": "Recipient"},
    "netto": {"de": "Netto", "en": "Net"},
    "ust": {"de": "USt", "en": "VAT"},
    "kundennummer": {"de": "Kundennummer", "en": "Customer No."},
    "kontaktperson": {"de": "Ansprechpartner", "en": "Contact"},
    "seite": {"de": "Seite", "en": "Page"},
    "von": {"de": "von", "en": "of"},
    "fortsetzung": {"de": "Fortsetzung", "en": "continued"},
    "rechnung": {"de": "Rechnung", "en": "Invoice"},
    "angebot": {"de": "Angebot", "en": "Quote"},
    "auftragsbestaetigung": {"de": "Auftragsbestaetigung", "en": "Order Confirmation"},
    "lieferschein": {"de": "Lieferschein", "en": "Delivery Note"},
    "leistungsdatum": {"de": "Leistungsdatum", "en": "Service Date"},
    "zahlungsziel": {"de": "Zahlungsziel", "en": "Due Date"},
    "erstellt_am": {"de": "Erstellt am", "en": "Created On"},
    "gueltig_bis": {"de": "Gueltig bis", "en": "Valid Until"},
    "angebot_vom": {"de": "Angebot vom", "en": "Quote Dated"},
    "lieferdatum": {"de": "Lieferdatum", "en": "Delivery Date"},
    "entwurf_hinweis": {"de": "ENTWURF — noch nicht final", "en": "DRAFT — not final"},
    "entwurf_hinweis_angebot": {"de": "ENTWURF — noch nicht versendet", "en": "DRAFT — not sent"},
}


@dataclass
class DocumentPosition:
    beschreibung: str
    menge: Decimal
    einzelpreis: Decimal
    ust_satz: Decimal
    artikelnummer: str | None = None


@dataclass
class LieferPosition:
    beschreibung: str
    menge: Decimal
    artikelnummer: str | None = None


@dataclass
class _Zeile:
    beschreibung: str
    menge: Decimal
    einzelpreis: Decimal | None = None
    ust_satz: Decimal | None = None
    artikelnummer: str | None = None


@dataclass
class _DocContext:
    mandant: Mandant
    akzent: colors.Color
    logo_faktor: float
    reduziert: bool
    titel_prefix: str
    nummer: str | None
    ist_entwurf: bool
    entwurf_hinweis: str
    kontakt_name: str
    kontakt_strasse: str | None
    kontakt_ort_zeile: str
    kontakt_land: str
    datum_label: str
    datum: date
    folgedatum_label: str | None
    folgedatum: date | None
    waehrung: str
    netto_gesamt: Decimal | None
    ust_gesamt: Decimal | None
    brutto_gesamt: Decimal | None
    zeilen: list[_Zeile] = field(default_factory=list)
    # Rechnungs-Editor-Zusatzfelder (siehe app/invoices/pdf.py): betreff ersetzt den
    # berechneten Titel 1:1, fusszeile_override ersetzt die Mandanten-Fusszeile fuer
    # genau dieses Dokument (mit bereits aufgeloesten Platzhaltern). kundennummer/
    # kontaktperson sind dokumentspezifisch (vom Kontakt bzw. von der Rechnung), nicht
    # mandantenweit -- alle anderen Design-Einstellungen kommen direkt aus ctx.mandant.
    titel_override: str | None = None
    fusszeile_override: str | None = None
    kundennummer: str | None = None
    kontaktperson: str | None = None

    @property
    def mit_preisen(self) -> bool:
        return self.brutto_gesamt is not None

    @property
    def titel(self) -> str:
        if self.titel_override:
            return self.titel_override
        praefix = _t(self, self.titel_prefix)
        return f"{praefix} {self.nummer}" if self.nummer else f"{praefix} (ENTWURF)"

    @property
    def fusszeile_text(self) -> str | None:
        return self.fusszeile_override or self.mandant.fusszeile_text


def _t(ctx: _DocContext, key: str) -> str:
    sprache = ctx.mandant.sprache or "de"
    eintrag = _TEXTE.get(key)
    if eintrag is None:
        return key
    return eintrag.get(sprache, eintrag["de"])


# --------------------------------------------------------------------------------
# Gemeinsame Bausteine
# --------------------------------------------------------------------------------

def _logo_bild(mandant: Mandant) -> ImageReader | None:
    if not mandant.logo_referenz:
        return None
    try:
        daten = branding_storage.read(mandant.logo_referenz)
    except OSError:
        return None  # Logo-Datei fehlt (z.B. Storage-Verzeichnis manuell geleert)
    return ImageReader(BytesIO(daten))


def _zeichne_logo(c: canvas.Canvas, bild: ImageReader | None, x: float, y: float, w: float, h: float, *, karte: bool = False) -> None:
    """`karte=True` legt eine weisse Flaeche hinter das Logo — noetig auf farbigen
    Untergruenden (Balken/Seitenleiste), damit ein Logo mit eigenem weissem
    Hintergrund nicht mit der Akzentfarbe kollidiert. Zuschneiden ueberfluessigen
    Rands passiert schon beim Upload (branding_storage.py). `w`/`h` sind vom
    Aufrufer bereits mit ctx.logo_faktor skaliert."""
    if bild is None:
        return
    if karte:
        c.setFillColor(colors.white)
        c.roundRect(x - 2 * mm, y - 2 * mm, w + 4 * mm, h + 4 * mm, 2 * mm, stroke=0, fill=1)
    c.drawImage(bild, x, y, width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto")


def _briefpapier_hintergrund(c: canvas.Canvas, mandant: Mandant) -> None:
    """Zeichnet das gewaehlte Briefpapier als volle Seite ZUERST (unterste Ebene) --
    muss vor allem anderen Vorlagen-Code aufgerufen werden."""
    if not mandant.briefpapier or not mandant.briefpapier.datei_referenz:
        return
    try:
        daten = letterhead_storage.read(mandant.briefpapier.datei_referenz)
    except OSError:
        return
    width, height = A4
    c.drawImage(ImageReader(BytesIO(daten)), 0, 0, width=width, height=height, preserveAspectRatio=False, mask="auto")


def _kuerzen(c: canvas.Canvas, text: str, schrift: str, groesse: float, max_breite: float) -> str:
    if c.stringWidth(text, schrift, groesse) <= max_breite:
        return text
    gekuerzt = text
    while gekuerzt and c.stringWidth(gekuerzt + "…", schrift, groesse) > max_breite:
        gekuerzt = gekuerzt[:-1]
    return f"{gekuerzt}…" if gekuerzt else "…"


def _falz_lochmarken(c: canvas.Canvas, height: float) -> None:
    """DIN-5008-Falz-/Lochmarken am linken Seitenrand: zwei Falzmarken (87mm/192mm von
    oben, zum Falten auf ein Fensterkuvert) und eine Lochmarke (148,5mm, vertikale
    Mitte, fuer den Locher)."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.3)
    for abstand_von_oben in (87 * mm, 192 * mm):
        y = height - abstand_von_oben
        c.line(0, y, 2.5 * mm, y)
    loch_y = height - 148.5 * mm
    c.line(0, loch_y, 4 * mm, loch_y)
    c.setLineWidth(1)


def _girocode_payload(mandant: Mandant, *, betrag: Decimal, verwendungszweck: str) -> str:
    """EPC069-12-Format (SEPA Credit Transfer QR, "GiroCode")."""
    zeilen = [
        "BCD", "002", "1", "SCT", mandant.bic or "", mandant.firmenname[:70],
        (mandant.iban or "").replace(" ", ""), f"EUR{betrag:.2f}", "", "", verwendungszweck[:140],
    ]
    return "\n".join(zeilen)


def _zeichne_girocode(c: canvas.Canvas, ctx: _DocContext, *, x: float, y: float, groesse: float = 22 * mm) -> None:
    """Nur gezeichnet wenn IBAN hinterlegt, Toggle aktiv, das Dokument Preise hat und
    eine echte Nummer (kein Entwurf) -- sonst still uebersprungen, nie ein Fehler."""
    if not (ctx.mandant.zeige_girocode and ctx.mandant.iban and ctx.mit_preisen and ctx.nummer):
        return
    payload = _girocode_payload(ctx.mandant, betrag=ctx.brutto_gesamt, verwendungszweck=ctx.nummer)
    widget = QrCodeWidget(payload)
    x0, y0, x1, y1 = widget.getBounds()
    breite_orig, hoehe_orig = x1 - x0, y1 - y0
    zeichnung = Drawing(groesse, groesse, transform=[groesse / breite_orig, 0, 0, groesse / hoehe_orig, 0, 0])
    zeichnung.add(widget)
    renderPDF.draw(zeichnung, c, x, y)


def _seitenende(c: canvas.Canvas, ctx: _DocContext, *, seite_nr: int, gesamt_seiten: int) -> None:
    """Seitenzahl + Falz-/Lochmarken fuer die GERADE VERLASSENE (oder letzte) Seite --
    an jedem Seitenumbruch und am Dokumentende aufgerufen."""
    width, height = A4
    if ctx.mandant.zeige_seitenzahlen:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(SEKUNDAERFARBE)
        c.drawRightString(width - 20 * mm, 10 * mm, f"{_t(ctx, 'seite')} {seite_nr} {_t(ctx, 'von')} {gesamt_seiten}")
        c.setFillColor(colors.black)
    if ctx.mandant.zeige_falz_lochmarken:
        _falz_lochmarken(c, height)


def _akzent(mandant: Mandant) -> colors.Color:
    """Design-Variante ist der Hebel, der Schwarz/Blau ohne Aenderung an den elf
    Vorlagen selbst durchreicht -- alle lesen zentral ctx.akzent."""
    variante = mandant.design_variante or "standard"
    if variante == "schwarz":
        return colors.black
    if variante == "blau":
        return colors.HexColor(KURATIERTES_BLAU)
    return colors.HexColor(mandant.akzentfarbe or STANDARD_AKZENTFARBE)


def _render(mandant: Mandant, ctx: _DocContext) -> bytes:
    from app.core.document_layouts import render_layout

    template = mandant.rechnungsvorlage or "klassisch"
    if template not in GUELTIGE_VORLAGEN:
        template = "klassisch"
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    render_layout(c, ctx, template)
    c.showPage()
    c.save()
    return buffer.getvalue()


def render_document_pdf(
    mandant: Mandant,
    *,
    titel_prefix: str,
    nummer: str | None,
    ist_entwurf: bool,
    entwurf_hinweis: str,
    kontakt_name: str,
    kontakt_strasse: str | None,
    kontakt_ort_zeile: str,
    kontakt_land: str,
    datum_label: str,
    datum: date,
    folgedatum_label: str,
    folgedatum: date,
    positionen: list[DocumentPosition],
    waehrung: str,
    netto_gesamt: Decimal,
    ust_gesamt: Decimal,
    brutto_gesamt: Decimal,
    titel_override: str | None = None,
    fusszeile_override: str | None = None,
    kundennummer: str | None = None,
    kontaktperson: str | None = None,
) -> bytes:
    """`titel_prefix`/`datum_label`/`folgedatum_label`/`entwurf_hinweis` sind i18n-
    Schluessel (siehe _TEXTE oben), keine literalen deutschen Anzeigetexte mehr --
    jede *_pdf.py-Callsite (invoices/quotes/auftraege) uebergibt z.B. "rechnung" statt
    "Rechnung", damit die Sprache des Mandanten greift."""
    ctx = _DocContext(
        mandant=mandant, akzent=_akzent(mandant),
        logo_faktor=_LOGO_FAKTOR.get(mandant.logo_groesse or "M", 1.0),
        reduziert=(mandant.design_variante or "standard") == "einfach",
        titel_prefix=titel_prefix, nummer=nummer,
        ist_entwurf=ist_entwurf, entwurf_hinweis=entwurf_hinweis, kontakt_name=kontakt_name,
        kontakt_strasse=kontakt_strasse, kontakt_ort_zeile=kontakt_ort_zeile, kontakt_land=kontakt_land,
        datum_label=datum_label, datum=datum, folgedatum_label=folgedatum_label, folgedatum=folgedatum,
        waehrung=waehrung, netto_gesamt=netto_gesamt, ust_gesamt=ust_gesamt, brutto_gesamt=brutto_gesamt,
        zeilen=[
            _Zeile(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz, artikelnummer=p.artikelnummer)
            for p in positionen
        ],
        titel_override=titel_override, fusszeile_override=fusszeile_override,
        kundennummer=kundennummer, kontaktperson=kontaktperson,
    )
    return _render(mandant, ctx)


def render_lieferschein_pdf(
    mandant: Mandant,
    *,
    nummer: str,
    kontakt_name: str,
    kontakt_strasse: str | None,
    kontakt_ort_zeile: str,
    kontakt_land: str,
    lieferdatum: date,
    positionen: list[LieferPosition],
    kundennummer: str | None = None,
) -> bytes:
    """Eigene, bewusst preislose Fassung fuer Lieferscheine — im Handel wird die Ware,
    nicht ihr Preis, ausgewiesen. Teilt sich Vorlage/Akzentfarbe/Logo/Fusszeile mit
    render_document_pdf; jede der elf Vorlagen blendet Preis-/USt-/Summenspalten
    automatisch aus (siehe _DocContext.mit_preisen)."""
    ctx = _DocContext(
        mandant=mandant, akzent=_akzent(mandant),
        logo_faktor=_LOGO_FAKTOR.get(mandant.logo_groesse or "M", 1.0),
        reduziert=(mandant.design_variante or "standard") == "einfach",
        titel_prefix="lieferschein", nummer=nummer,
        ist_entwurf=False, entwurf_hinweis="", kontakt_name=kontakt_name, kontakt_strasse=kontakt_strasse,
        kontakt_ort_zeile=kontakt_ort_zeile, kontakt_land=kontakt_land, datum_label="lieferdatum",
        datum=lieferdatum, folgedatum_label=None, folgedatum=None,
        waehrung="", netto_gesamt=None, ust_gesamt=None, brutto_gesamt=None,
        zeilen=[_Zeile(beschreibung=p.beschreibung, menge=p.menge, artikelnummer=p.artikelnummer) for p in positionen],
        kundennummer=kundennummer,
    )
    return _render(mandant, ctx)
