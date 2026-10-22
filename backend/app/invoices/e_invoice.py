"""XRechnung (UBL 2.1 Invoice, CIUS XRechnung 3.0) fuer eine finalisierte Rechnung oder Stornorechnung.

Stand, ohne Beschoenigung:

* Erzeugt wird nur UBL, kein CII (UN/CEFACT). Der Ausgang wird gegen XSD und Schematron der KoSIT-XRechnung-
  Konfiguration (EN16931 plus XRechnung-CIUS) geprueft, siehe ``e_invoice_validation.py``. Diese Pruefung laeuft mit
  Saxon und ist nicht das KoSIT-Validator-Programm; sie ersetzt weder dessen Gegenprobe noch eine Zertifizierung
  (Anleitung zur Gegenprobe: docs/xrechnung-validierung.md).
* Was die Regeln nicht pruefen koennen, ist hier nicht abgedeckt: Steuerbefreiungen nach UStG ausser § 19
  (Kleinunternehmer), Reverse-Charge, innergemeinschaftliche Lieferungen, Anzahlungen, Rabatte/Zuschlaege auf
  Dokumentebene, Anhaenge, mehrere Umsatzsteuerwaehrungen. 0-%-Positionen werden als "Z" (Nullsatz) gemeldet, bei
  Kleinunternehmern als "E" mit dem Hinweis auf § 19 UStG.
* Stornorechnungen (``korrigiert_invoice_id`` gesetzt) werden als UBL-CreditNote (Typcode 381) mit positiven Betraegen
  und Verweis auf die Ursprungsrechnung (BT-25) ausgegeben. Intern sind sie mit negativen Preisen gespeichert; EN16931
  erlaubt keine negativen Preise (BR-27), und der Code 381 ist in einem UBL-Invoice nicht zulaessig (BR-CL-01).
* Die Anschrift des Verkaeufers steht im Mandanten als ein Textfeld; Strasse, PLZ und Ort werden daraus gelesen
  (Land: Deutschland, fuer deutsche Anschriften mit fuenfstelliger PLZ).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

from app.auth.models import Mandant
from app.invoices.models import Invoice, InvoicePosition

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDITNOTE_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

NSMAP = {None: UBL_NS, "cac": CAC_NS, "cbc": CBC_NS}
NSMAP_GUTSCHRIFT = {None: UBL_CREDITNOTE_NS, "cac": CAC_NS, "cbc": CBC_NS}

# BT-24. Seit XRechnung 3.0.1 mit xeinkauf.de (vorher xoev-de); die KoSIT-Konfiguration kennt nur diese Kennung.
XRECHNUNG_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
# BT-23, von den Peppol-Regeln (PEPPOL-EN16931-R001) verlangt, die im XRechnung-Schematron enthalten sind.
PEPPOL_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

TYPCODE_RECHNUNG = "380"
TYPCODE_GUTSCHRIFT = "381"
KLEINUNTERNEHMER_HINWEIS = "Kein Ausweis von Umsatzsteuer, da Kleinunternehmer gemäß § 19 UStG"
EAS_E_MAIL = "EM"
EAS_LEITWEG_ID = "0204"

CENT = Decimal("0.01")


def runde(betrag: Decimal) -> Decimal:
    """Kaufmaennisch auf Cent (0,005 wird 0,01, bei negativen Werten spiegelbildlich). Decimal.quantize allein rundet
    ohne Angabe auf gerade Ziffern (0,005 wird 0,00) und waere fuer Rechnungen falsch."""
    return betrag.quantize(CENT, rounding=ROUND_HALF_UP)


def _cbc(tag: str) -> str:
    return f"{{{CBC_NS}}}{tag}"


def _cac(tag: str) -> str:
    return f"{{{CAC_NS}}}{tag}"


def _dezimal(wert: Decimal) -> str:
    """Ohne Exponentenschreibweise (str(Decimal('1E+2')) waere kein gueltiger xs:decimal)."""
    return format(wert, "f")


def _betrag(wert: Decimal) -> str:
    return _dezimal(runde(wert))


@dataclass(frozen=True)
class Anschrift:
    strasse: str
    plz: str
    ort: str


_PLZ_ORT = re.compile(r"^(?:D[- ])?(\d{5})\s+(\S.*)$")
_LAENDER = {"deutschland", "germany", "de"}


def zerlege_anschrift(adresse: str | None) -> Anschrift | None:
    """Liest "Musterstr. 1, 10115 Berlin" (auch zeilenweise) in Strasse, PLZ und Ort. None, wenn das nicht gelingt."""
    if not adresse:
        return None
    teile = [t.strip() for t in re.split(r"[\n\r;,]+", adresse) if t.strip()]
    while teile and teile[-1].lower() in _LAENDER:
        teile.pop()
    if len(teile) < 2:
        return None
    treffer = _PLZ_ORT.match(teile[-1])
    if not treffer:
        return None
    return Anschrift(strasse=", ".join(teile[:-1]), plz=treffer.group(1), ort=treffer.group(2).strip())


def _kompakt(wert: str | None) -> str:
    return re.sub(r"\s+", "", wert or "").upper()


def ist_gutschrift(invoice: Invoice) -> bool:
    return invoice.korrigiert_invoice_id is not None


def missing_pflichtfelder(mandant: Mandant, invoice: Invoice) -> list[str]:
    """Returns a list of human-readable German field names that are missing.
    Empty list means the invoice can be turned into an XRechnung (whether it passes the rules is a separate check,
    see e_invoice_validation.py)."""
    missing: list[str] = []

    if not mandant.ust_id and not mandant.steuernummer:
        missing.append("USt-IdNr. oder Steuernummer (Verkaeufer)")
    if not mandant.adresse:
        missing.append("Anschrift (Verkaeufer)")
    elif zerlege_anschrift(mandant.adresse) is None:
        missing.append("Anschrift (Verkaeufer): Strasse sowie PLZ und Ort, z. B. 'Musterstr. 1, 10115 Berlin'")
    if not mandant.iban:
        missing.append("IBAN (Verkaeufer)")
    if not mandant.telefon:
        missing.append("Telefonnummer (Verkaeufer)")
    if not mandant.kontakt_email:
        missing.append("E-Mail-Adresse fuer Rueckfragen (Verkaeufer)")
    if invoice.nummer is None:
        missing.append("Rechnungsnummer (erst nach Finalisierung vorhanden)")
    if not invoice.leistungsdatum:
        missing.append("Leistungsdatum")
    if not invoice.faelligkeitsdatum:
        missing.append("Zahlungsziel (Faelligkeitsdatum)")

    kontakt = invoice.kontakt
    if not kontakt.name:
        missing.append("Name (Kaeufer)")
    if not (kontakt.strasse and kontakt.plz and kontakt.ort):
        missing.append("Anschrift (Kaeufer)")
    if not kontakt.email and not kontakt.leitweg_id:
        missing.append("E-Mail-Adresse (Kaeufer)")

    return missing


def kaeuferreferenz(invoice: Invoice) -> str:
    """BT-10 ist in XRechnung immer Pflicht (BR-DE-15). Oeffentliche Auftraggeber verlangen
    dort ihre Leitweg-ID. Ohne Leitweg-ID nehmen wir die Kundennummer, sonst die
    Rechnungsnummer, damit das Feld nie leer bleibt."""
    kontakt = invoice.kontakt
    return kontakt.leitweg_id or kontakt.kundennummer or invoice.nummer or ""


def _endpoint(party: etree._Element, wert: str, schema: str) -> None:
    element = etree.SubElement(party, _cbc("EndpointID"))
    element.set("schemeID", schema)
    element.text = wert


def _party(
    parent: etree._Element, tag: str, *, name: str, anschrift: Anschrift, land: str,
    endpoint: tuple[str, str] | None, steuer_ids: list[tuple[str, str]], kontakt: tuple[str, str, str] | None = None,
    kennung: str | None = None,
) -> None:
    """steuer_ids: [(Kennung, Steuerschema)], Schema "VAT" fuer die USt-IdNr. (BT-31/BT-48), "FC" fuer die Steuernummer
    (BT-32). kontakt: (Name, Telefon, E-Mail) fuer BG-6. kennung: Verkaeufer-Kennung (BT-29); BR-CO-26 verlangt BT-29,
    BT-30 oder BT-31, eine Steuernummer allein (BT-32) genuegt nicht."""
    party_wrapper = etree.SubElement(parent, _cac(tag))
    party = etree.SubElement(party_wrapper, _cac("Party"))

    if endpoint:
        _endpoint(party, endpoint[0], endpoint[1])

    if kennung:
        identification = etree.SubElement(party, _cac("PartyIdentification"))
        etree.SubElement(identification, _cbc("ID")).text = kennung

    party_name = etree.SubElement(party, _cac("PartyName"))
    etree.SubElement(party_name, _cbc("Name")).text = name

    address = etree.SubElement(party, _cac("PostalAddress"))
    etree.SubElement(address, _cbc("StreetName")).text = anschrift.strasse
    etree.SubElement(address, _cbc("CityName")).text = anschrift.ort
    etree.SubElement(address, _cbc("PostalZone")).text = anschrift.plz
    country = etree.SubElement(address, _cac("Country"))
    etree.SubElement(country, _cbc("IdentificationCode")).text = land

    for kennung, schema in steuer_ids:
        tax_scheme_wrapper = etree.SubElement(party, _cac("PartyTaxScheme"))
        etree.SubElement(tax_scheme_wrapper, _cbc("CompanyID")).text = kennung
        tax_scheme = etree.SubElement(tax_scheme_wrapper, _cac("TaxScheme"))
        etree.SubElement(tax_scheme, _cbc("ID")).text = schema

    legal_entity = etree.SubElement(party, _cac("PartyLegalEntity"))
    etree.SubElement(legal_entity, _cbc("RegistrationName")).text = name

    if kontakt:
        contact = etree.SubElement(party, _cac("Contact"))
        etree.SubElement(contact, _cbc("Name")).text = kontakt[0]
        etree.SubElement(contact, _cbc("Telephone")).text = kontakt[1]
        etree.SubElement(contact, _cbc("ElectronicMail")).text = kontakt[2]


@dataclass(frozen=True)
class _Steuerkategorie:
    code: str  # S | Z | E
    satz: Decimal

    @property
    def befreiungsgrund(self) -> str | None:
        return KLEINUNTERNEHMER_HINWEIS if self.code == "E" else None


def _kategorie(position: InvoicePosition, *, kleinunternehmer: bool) -> _Steuerkategorie:
    satz = runde(position.ust_satz)
    if satz > 0:
        return _Steuerkategorie("S", satz)
    return _Steuerkategorie("E" if kleinunternehmer else "Z", Decimal("0.00"))


def _tax_category(parent: etree._Element, kategorie: _Steuerkategorie, *, mit_grund: bool) -> None:
    element = etree.SubElement(parent, _cac("TaxCategory") if mit_grund else _cac("ClassifiedTaxCategory"))
    etree.SubElement(element, _cbc("ID")).text = kategorie.code
    etree.SubElement(element, _cbc("Percent")).text = _dezimal(kategorie.satz)
    if mit_grund and kategorie.befreiungsgrund:
        etree.SubElement(element, _cbc("TaxExemptionReason")).text = kategorie.befreiungsgrund
    scheme = etree.SubElement(element, _cac("TaxScheme"))
    etree.SubElement(scheme, _cbc("ID")).text = "VAT"


def _betragselement(parent: etree._Element, tag: str, waehrung: str, wert: Decimal) -> etree._Element:
    element = etree.SubElement(parent, _cbc(tag))
    element.set("currencyID", waehrung)
    element.text = _betrag(wert)
    return element


def _skonto_zeile(invoice: Invoice) -> str | None:
    """Skonto-Angabe im Format von BR-DE-18 (XRechnung): '#SKONTO#TAGE=14#PROZENT=2.00#' plus Zeilenumbruch."""
    if invoice.skonto_tage is None or invoice.skonto_prozent is None:
        return None
    if invoice.skonto_tage < 0 or invoice.skonto_prozent <= 0:
        return None
    return f"#SKONTO#TAGE={int(invoice.skonto_tage)}#PROZENT={_dezimal(runde(invoice.skonto_prozent))}#\n"


def build_xrechnung_xml(
    mandant: Mandant, invoice: Invoice, *, kleinunternehmer: bool = False,
    korrigierte_rechnungsnummer: str | None = None,
) -> bytes:
    """kleinunternehmer: Einstellung des Mandanten (§ 19 UStG), macht aus 0-%-Positionen steuerfreie ("E") mit Hinweis.
    korrigierte_rechnungsnummer: Nummer der Ursprungsrechnung, Pflicht bei Stornorechnungen (BT-25)."""
    missing = missing_pflichtfelder(mandant, invoice)
    gutschrift = ist_gutschrift(invoice)
    if gutschrift and not korrigierte_rechnungsnummer:
        missing.append("Rechnungsnummer der stornierten Rechnung")
    if missing:
        raise ValueError(f"Fehlende Pflichtfelder fuer E-Rechnung: {', '.join(missing)}")

    # Intern ist eine Storno-Rechnung negativ gespeichert, die Gutschrift im XML positiv.
    vorzeichen = Decimal("-1") if gutschrift else Decimal("1")
    waehrung = invoice.waehrung

    if gutschrift:
        root = etree.Element(f"{{{UBL_CREDITNOTE_NS}}}CreditNote", nsmap=NSMAP_GUTSCHRIFT)
    else:
        root = etree.Element(f"{{{UBL_NS}}}Invoice", nsmap=NSMAP)
    etree.SubElement(root, _cbc("CustomizationID")).text = XRECHNUNG_CUSTOMIZATION_ID
    etree.SubElement(root, _cbc("ProfileID")).text = PEPPOL_PROFILE_ID
    etree.SubElement(root, _cbc("ID")).text = invoice.nummer
    etree.SubElement(root, _cbc("IssueDate")).text = invoice.finalisiert_am.date().isoformat()
    if gutschrift:
        # Das UBL-CreditNote kennt kein DueDate auf Dokumentebene; die Gutschrift hat keinen Faelligkeitstermin.
        etree.SubElement(root, _cbc("CreditNoteTypeCode")).text = TYPCODE_GUTSCHRIFT
    else:
        etree.SubElement(root, _cbc("DueDate")).text = invoice.faelligkeitsdatum.isoformat()
        etree.SubElement(root, _cbc("InvoiceTypeCode")).text = TYPCODE_RECHNUNG
    etree.SubElement(root, _cbc("DocumentCurrencyCode")).text = waehrung
    etree.SubElement(root, _cbc("BuyerReference")).text = kaeuferreferenz(invoice)

    if gutschrift:
        billing = etree.SubElement(root, _cac("BillingReference"))
        reference = etree.SubElement(billing, _cac("InvoiceDocumentReference"))
        etree.SubElement(reference, _cbc("ID")).text = korrigierte_rechnungsnummer

    anschrift = zerlege_anschrift(mandant.adresse)
    steuer_ids: list[tuple[str, str]] = []
    if mandant.ust_id:
        steuer_ids.append((_kompakt(mandant.ust_id), "VAT"))
    if mandant.steuernummer:
        steuer_ids.append((mandant.steuernummer.strip(), "FC"))
    # Ohne USt-IdNr. ist die Steuernummer zugleich die Verkaeufer-Kennung (BT-29), sonst fehlt BR-CO-26 die Kennung.
    verkaeufer_kennung = None if mandant.ust_id else (mandant.steuernummer or "").strip() or None
    kontakt_email = mandant.kontakt_email.strip()
    _party(
        root, "AccountingSupplierParty",
        name=mandant.firmenname, anschrift=anschrift, land="DE",
        endpoint=(kontakt_email, EAS_E_MAIL), steuer_ids=steuer_ids,
        kontakt=(mandant.firmenname, mandant.telefon.strip(), kontakt_email), kennung=verkaeufer_kennung,
    )
    kontakt = invoice.kontakt
    kaeufer_endpoint = (kontakt.email.strip(), EAS_E_MAIL) if kontakt.email else (kontakt.leitweg_id.strip(), EAS_LEITWEG_ID)
    _party(
        root, "AccountingCustomerParty",
        name=kontakt.name,
        anschrift=Anschrift(strasse=kontakt.strasse, plz=kontakt.plz, ort=kontakt.ort),
        land=(kontakt.land or "DE").strip().upper(),
        endpoint=kaeufer_endpoint,
        steuer_ids=[(_kompakt(kontakt.ust_id), "VAT")] if kontakt.ust_id else [],
    )

    delivery = etree.SubElement(root, _cac("Delivery"))
    etree.SubElement(delivery, _cbc("ActualDeliveryDate")).text = invoice.leistungsdatum.isoformat()

    payment_means = etree.SubElement(root, _cac("PaymentMeans"))
    etree.SubElement(payment_means, _cbc("PaymentMeansCode")).text = "58"  # SEPA-Ueberweisung
    etree.SubElement(payment_means, _cbc("PaymentID")).text = invoice.nummer
    konto = etree.SubElement(payment_means, _cac("PayeeFinancialAccount"))
    etree.SubElement(konto, _cbc("ID")).text = _kompakt(mandant.iban)
    if mandant.bic:
        bank = etree.SubElement(konto, _cac("FinancialInstitutionBranch"))
        etree.SubElement(bank, _cbc("ID")).text = _kompakt(mandant.bic)

    skonto = _skonto_zeile(invoice)
    if skonto:
        terms = etree.SubElement(root, _cac("PaymentTerms"))
        etree.SubElement(terms, _cbc("Note")).text = skonto

    # Positionen: Zeilenbetrag je Position auf Cent gerundet, Steuer je Kategorie und Satz aus der Summe der Zeilen.
    zeilen = [
        (position, _kategorie(position, kleinunternehmer=kleinunternehmer), runde(position.menge * position.einzelpreis))
        for position in invoice.positionen
    ]
    gruppen: dict[_Steuerkategorie, Decimal] = {}
    for _, kategorie, zeilenbetrag in zeilen:
        gruppen[kategorie] = gruppen.get(kategorie, Decimal("0")) + zeilenbetrag

    tax_total = etree.SubElement(root, _cac("TaxTotal"))
    _betragselement(tax_total, "TaxAmount", waehrung, invoice.ust_gesamt * vorzeichen)
    for kategorie in sorted(gruppen, key=lambda k: (k.satz, k.code)):
        basis = gruppen[kategorie] * vorzeichen
        subtotal = etree.SubElement(tax_total, _cac("TaxSubtotal"))
        _betragselement(subtotal, "TaxableAmount", waehrung, basis)
        _betragselement(subtotal, "TaxAmount", waehrung, basis * kategorie.satz / Decimal("100"))
        _tax_category(subtotal, kategorie, mit_grund=True)

    totals = etree.SubElement(root, _cac("LegalMonetaryTotal"))
    for tag, wert in (
        ("LineExtensionAmount", invoice.netto_gesamt),
        ("TaxExclusiveAmount", invoice.netto_gesamt),
        ("TaxInclusiveAmount", invoice.brutto_gesamt),
        ("PayableAmount", invoice.brutto_gesamt),
    ):
        _betragselement(totals, tag, waehrung, wert * vorzeichen)

    for index, (position, kategorie, zeilenbetrag) in enumerate(zeilen, start=1):
        line = etree.SubElement(root, _cac("CreditNoteLine" if gutschrift else "InvoiceLine"))
        etree.SubElement(line, _cbc("ID")).text = str(index)
        quantity_el = etree.SubElement(line, _cbc("CreditedQuantity" if gutschrift else "InvoicedQuantity"))
        quantity_el.set("unitCode", "C62")
        quantity_el.text = _dezimal(position.menge)
        _betragselement(line, "LineExtensionAmount", waehrung, zeilenbetrag * vorzeichen)

        item = etree.SubElement(line, _cac("Item"))
        etree.SubElement(item, _cbc("Name")).text = position.beschreibung
        if position.artikelnummer:
            seller_id = etree.SubElement(item, _cac("SellersItemIdentification"))
            etree.SubElement(seller_id, _cbc("ID")).text = position.artikelnummer
        _tax_category(item, kategorie, mit_grund=False)

        price = etree.SubElement(line, _cac("Price"))
        price_amount = etree.SubElement(price, _cbc("PriceAmount"))
        price_amount.set("currencyID", waehrung)
        price_amount.text = _dezimal(position.einzelpreis * vorzeichen)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
