"""Eingehende E-Rechnungen lesen: XRechnung (UBL oder CII) und ZUGFeRD/Factur-X (PDF mit
XML-Anhang).

Es wird nur gelesen, nicht geprueft: Eingehende Dateien durchlaufen hier keine XSD-/Schematron-
Validierung (die gibt es nur fuer selbst erzeugte XRechnungen, siehe app/invoices/e_invoice_validation.py).
Das XML ist bei einer E-Rechnung der Originalbeleg und wird unveraendert archiviert; die hier gelesenen
Werte sind Vorschlaege fuer das Bestaetigungsformular, wie bei der Texterkennung auch.

Getestet ist das Lesen ausser mit eigenen Dateien auch mit den Beispielinstanzen aus den Regel-Repositories
(KoSIT-Testsuite UBL und CII, CEN-Beispiele; tests/test_e_rechnung_beispielinstanzen.py, nur mit geholten
Regeln). Gutschriften (381 / CreditNote) werden bewusst nicht automatisch gelesen."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pikepdf
from lxml import etree

from app.core.key_management import blind_index
from app.core.xml_safe import UngueltigesXml, parse_xml_sicher
from app.receipts.ai_extraction import ExtractedField, ReceiptExtraction, _extract_category
from app.receipts.accounting import SUPPORTED_VAT_RATES

UBL_NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
CII_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
PDF_ANHANG_NAMEN = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")
GUTSCHRIFT_CODES = {"381"}
SICHERHEIT = Decimal("0.99")


class EInvoiceFehler(ValueError):
    """Die Datei ist keine lesbare, unterstuetzte E-Rechnung."""


@dataclass
class EInvoiceDaten:
    syntax: str
    rechnungsnummer: str | None = None
    datum: date | None = None
    faelligkeit: date | None = None
    waehrung: str | None = None
    verkaeufer_name: str | None = None
    verkaeufer_ust_id: str | None = None
    brutto: Decimal | None = None
    zahlbetrag: Decimal | None = None
    iban: str | None = None
    steueranteile: list[tuple[Decimal, Decimal]] = field(default_factory=list)  # (Satz, Brutto)
    positionsnamen: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def betrag(self) -> Decimal | None:
        return self.brutto if self.brutto is not None else self.zahlbetrag


def _text(knoten: etree._Element, ausdruck: str, ns: dict[str, str]) -> str | None:
    treffer = knoten.xpath(ausdruck, namespaces=ns)
    if not treffer:
        return None
    wert = treffer[0].text if hasattr(treffer[0], "text") else str(treffer[0])
    wert = wert.strip() if wert else ""
    return wert or None


def _dezimal(wert: str | None) -> Decimal | None:
    if wert is None:
        return None
    try:
        return Decimal(wert)
    except InvalidOperation:
        return None


def _datum(wert: str | None) -> date | None:
    if wert is None:
        return None
    wert = wert.strip()
    try:
        if re.fullmatch(r"\d{8}", wert):
            return date(int(wert[:4]), int(wert[4:6]), int(wert[6:]))
        return date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _brutto_je_satz(eintraege: list[tuple[Decimal, Decimal, Decimal]]) -> list[tuple[Decimal, Decimal]]:
    """(Satz, Basis, Steuer) wird zu (Satz, Brutto), gleiche Saetze werden zusammengefasst."""
    je_satz: dict[Decimal, Decimal] = {}
    for satz, basis, steuer in eintraege:
        je_satz[satz] = je_satz.get(satz, Decimal("0")) + basis + steuer
    return sorted(je_satz.items())


def _lese_ubl(wurzel: etree._Element) -> EInvoiceDaten:
    ns = UBL_NS
    if etree.QName(wurzel).localname == "CreditNote":
        raise EInvoiceFehler(
            "Gutschriften werden noch nicht automatisch gelesen. Bitte als Beleg manuell erfassen."
        )
    if _text(wurzel, "cbc:InvoiceTypeCode", ns) in GUTSCHRIFT_CODES:
        raise EInvoiceFehler("Gutschriften werden noch nicht automatisch gelesen. Bitte als Beleg manuell erfassen.")

    verkaeufer = "cac:AccountingSupplierParty/cac:Party"
    daten = EInvoiceDaten(
        syntax="ubl",
        rechnungsnummer=_text(wurzel, "cbc:ID", ns),
        datum=_datum(_text(wurzel, "cbc:IssueDate", ns)),
        faelligkeit=_datum(_text(wurzel, "cbc:DueDate", ns)),
        waehrung=_text(wurzel, "cbc:DocumentCurrencyCode", ns),
        verkaeufer_name=(
            _text(wurzel, f"{verkaeufer}/cac:PartyLegalEntity/cbc:RegistrationName", ns)
            or _text(wurzel, f"{verkaeufer}/cac:PartyName/cbc:Name", ns)
        ),
        verkaeufer_ust_id=_text(wurzel, f"{verkaeufer}/cac:PartyTaxScheme[cac:TaxScheme/cbc:ID='VAT']/cbc:CompanyID", ns),
        brutto=_dezimal(_text(wurzel, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount", ns)),
        zahlbetrag=_dezimal(_text(wurzel, "cac:LegalMonetaryTotal/cbc:PayableAmount", ns)),
        iban=_text(wurzel, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", ns),
        positionsnamen=[
            name.text.strip() for name in wurzel.xpath("cac:InvoiceLine/cac:Item/cbc:Name", namespaces=ns) if name.text
        ],
    )
    eintraege = []
    for teil in wurzel.xpath("cac:TaxTotal[1]/cac:TaxSubtotal", namespaces=ns):
        satz = _dezimal(_text(teil, "cac:TaxCategory/cbc:Percent", ns))
        basis = _dezimal(_text(teil, "cbc:TaxableAmount", ns))
        steuer = _dezimal(_text(teil, "cbc:TaxAmount", ns))
        if satz is not None and basis is not None and steuer is not None:
            eintraege.append((satz, basis, steuer))
    daten.steueranteile = _brutto_je_satz(eintraege)
    return daten


def _lese_cii(wurzel: etree._Element) -> EInvoiceDaten:
    ns = CII_NS
    if _text(wurzel, "rsm:ExchangedDocument/ram:TypeCode", ns) in GUTSCHRIFT_CODES:
        raise EInvoiceFehler("Gutschriften werden noch nicht automatisch gelesen. Bitte als Beleg manuell erfassen.")

    handel = "rsm:SupplyChainTradeTransaction"
    abrechnung = f"{handel}/ram:ApplicableHeaderTradeSettlement"
    summen = f"{abrechnung}/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    daten = EInvoiceDaten(
        syntax="cii",
        rechnungsnummer=_text(wurzel, "rsm:ExchangedDocument/ram:ID", ns),
        datum=_datum(_text(wurzel, "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString", ns)),
        faelligkeit=_datum(
            _text(wurzel, f"{abrechnung}/ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString", ns)
        ),
        waehrung=_text(wurzel, f"{abrechnung}/ram:InvoiceCurrencyCode", ns),
        verkaeufer_name=_text(wurzel, f"{handel}/ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:Name", ns),
        verkaeufer_ust_id=_text(
            wurzel,
            f"{handel}/ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/"
            "ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']",
            ns,
        ),
        brutto=_dezimal(_text(wurzel, f"{summen}/ram:GrandTotalAmount", ns)),
        zahlbetrag=_dezimal(_text(wurzel, f"{summen}/ram:DuePayableAmount", ns)),
        iban=_text(
            wurzel,
            f"{abrechnung}/ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID",
            ns,
        ),
        positionsnamen=[
            name.text.strip()
            for name in wurzel.xpath(
                f"{handel}/ram:IncludedSupplyChainTradeLineItem/ram:SpecifiedTradeProduct/ram:Name", namespaces=ns
            )
            if name.text
        ],
    )
    eintraege = []
    for teil in wurzel.xpath(f"{abrechnung}/ram:ApplicableTradeTax", namespaces=ns):
        satz = _dezimal(_text(teil, "ram:RateApplicablePercent", ns))
        basis = _dezimal(_text(teil, "ram:BasisAmount", ns))
        steuer = _dezimal(_text(teil, "ram:CalculatedAmount", ns))
        if satz is not None and basis is not None and steuer is not None:
            eintraege.append((satz, basis, steuer))
    daten.steueranteile = _brutto_je_satz(eintraege)
    return daten


def lese_e_rechnung(xml_bytes: bytes) -> EInvoiceDaten:
    try:
        wurzel = parse_xml_sicher(xml_bytes)
    except UngueltigesXml as exc:
        raise EInvoiceFehler(str(exc)) from exc

    name = etree.QName(wurzel)
    if name.namespace == UBL_NS["inv"] and name.localname == "Invoice" or (
        name.namespace == UBL_NS["cn"] and name.localname == "CreditNote"
    ):
        daten = _lese_ubl(wurzel)
    elif name.namespace == CII_NS["rsm"] and name.localname == "CrossIndustryInvoice":
        daten = _lese_cii(wurzel)
    else:
        raise EInvoiceFehler(
            "Die XML-Datei ist keine unterstützte E-Rechnung (erwartet: XRechnung als UBL Invoice oder CII)."
        )

    _pruefe_und_ergaenze_hinweise(daten)
    return daten


def _pruefe_und_ergaenze_hinweise(daten: EInvoiceDaten) -> None:
    if daten.betrag is None:
        raise EInvoiceFehler("In der E-Rechnung wurde kein Gesamtbetrag gefunden.")
    if daten.waehrung not in (None, "EUR"):
        daten.hinweise.append(f"Die Rechnung lautet auf {daten.waehrung}. Bitte den Betrag in Euro selbst eintragen.")
    nicht_unterstuetzt = [satz for satz, _ in daten.steueranteile if satz not in SUPPORTED_VAT_RATES]
    if nicht_unterstuetzt:
        daten.hinweise.append(
            "Die Rechnung enthält USt-Sätze, die Bilantiq noch nicht unterstützt: "
            + ", ".join(f"{satz} %" for satz in nicht_unterstuetzt)
            + "."
        )
    if len(daten.steueranteile) > 1 and daten.betrag is not None:
        summe = sum((brutto for _, brutto in daten.steueranteile), Decimal("0"))
        if summe != daten.betrag:
            daten.hinweise.append(
                f"Die USt-Aufteilung ({summe:.2f}) weicht vom Gesamtbetrag ({daten.betrag:.2f}) ab. Bitte prüfen."
            )


def baue_extraktion(daten: EInvoiceDaten) -> ReceiptExtraction:
    """Die gelesenen Werte im selben Format wie die Texterkennung. Maschinenlesbare Felder
    sind sehr sicher, Kategorie kommt weiter aus Stichworten."""
    sicher = float(SICHERHEIT)
    in_euro = daten.waehrung in (None, "EUR")
    betrag = ExtractedField(wert=f"{daten.betrag:.2f}", confidence=sicher) if in_euro and daten.betrag is not None else (
        ExtractedField(wert=None, confidence=0.0)
    )
    ust_satz = ExtractedField(wert=None, confidence=0.0)
    if len(daten.steueranteile) == 1 and daten.steueranteile[0][0] in SUPPORTED_VAT_RATES:
        ust_satz = ExtractedField(wert=f"{daten.steueranteile[0][0]:.2f}", confidence=sicher)

    kategorie, begruendung = _extract_category(" ".join([daten.verkaeufer_name or "", *daten.positionsnamen]))
    return ReceiptExtraction(
        betrag=betrag,
        datum=ExtractedField(wert=daten.datum.isoformat(), confidence=sicher) if daten.datum else ExtractedField(wert=None, confidence=0.0),
        anbieter=ExtractedField(wert=daten.verkaeufer_name, confidence=sicher) if daten.verkaeufer_name else ExtractedField(wert=None, confidence=0.0),
        ust_satz=ust_satz,
        kategorie_vorschlag=kategorie,
        begruendung=begruendung,
    )


def zusatzdaten_json(daten: EInvoiceDaten) -> str:
    """Die nicht als eigene Spalte gespeicherten Angaben, als JSON (wird verschluesselt abgelegt)."""
    return json.dumps(
        {
            "syntax": daten.syntax,
            "verkaeufer_ust_id": daten.verkaeufer_ust_id,
            "waehrung": daten.waehrung,
            "steueranteile": [
                {"ust_satz": f"{satz:.2f}", "bruttobetrag": f"{brutto:.2f}"} for satz, brutto in daten.steueranteile
            ],
            "hinweise": daten.hinweise,
        },
        ensure_ascii=False,
    )


def dedupe_key(mandant_id: str, daten: EInvoiceDaten) -> str | None:
    """Gleiche Rechnung (Verkaeufer plus Rechnungsnummer), auch wenn sie als XML und als
    PDF-Kopie eintrifft. Blind-Index, damit der Klartext nie durchsuchbar gespeichert wird."""
    verkaeufer = daten.verkaeufer_ust_id or daten.verkaeufer_name
    if not daten.rechnungsnummer or not verkaeufer:
        return None
    return blind_index(f"{verkaeufer}|{daten.rechnungsnummer}", purpose=f"e-rechnung:{mandant_id}")


def _ist_unterstuetztes_xml(xml_bytes: bytes) -> bool:
    try:
        wurzel = parse_xml_sicher(xml_bytes)
    except UngueltigesXml:
        return False
    name = etree.QName(wurzel)
    return (name.namespace, name.localname) in {
        (UBL_NS["inv"], "Invoice"), (UBL_NS["cn"], "CreditNote"), (CII_NS["rsm"], "CrossIndustryInvoice"),
    }


def extrahiere_xml_aus_pdf(pdf_bytes: bytes) -> bytes | None:
    """Sucht im PDF den eingebetteten Rechnungsdatensatz (ZUGFeRD/Factur-X). Kein Treffer
    oder kaputtes PDF: None, dann greift die Texterkennung."""
    try:
        with pikepdf.Pdf.open(BytesIO(pdf_bytes)) as pdf:
            anhaenge = {name.lower(): name for name in pdf.attachments.keys()}
            kandidaten = [anhaenge[name] for name in PDF_ANHANG_NAMEN if name in anhaenge]
            kandidaten += [original for klein, original in anhaenge.items() if klein.endswith(".xml") and original not in kandidaten]
            for name in kandidaten:
                inhalt = pdf.attachments[name].get_file().read_bytes()
                if _ist_unterstuetztes_xml(inhalt):
                    return inhalt
    except (pikepdf.PdfError, ValueError, RuntimeError, OSError):
        return None
    return None
