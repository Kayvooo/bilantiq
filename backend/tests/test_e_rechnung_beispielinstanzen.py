"""Die Leseseite (app/receipts/e_rechnung.py) mit den Beispielinstanzen aus den Regel-Repositories.

Die Dateien kommen aus der KoSIT-Testsuite und dem CEN-Repository und werden von scripts/kosit_regeln_holen.py in den
Cache gelegt (nichts davon liegt im Repository). Ohne Cache werden die Tests mit Meldung uebersprungen. Erwartet wird
der Gesamtbetrag, den die Datei selbst nennt (unabhaengig per XPath gelesen)."""
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from app.invoices import e_invoice_validation as val
from app.receipts.e_rechnung import EInvoiceFehler, lese_e_rechnung

TESTINSTANZEN = val.regeln_ordner() / "testinstanzen"
STANDARD = sorted((TESTINSTANZEN / "business-cases" / "standard").glob("*.xml"))
TECHNISCH = sorted((TESTINSTANZEN / "technical-cases" / "cius").glob("*.xml"))
CEN_BEISPIELE = sorted((TESTINSTANZEN / "en16931-ubl-beispiele").glob("*.[xX][mM][lL]"))
ALLE = STANDARD + TECHNISCH + CEN_BEISPIELE

pytestmark = pytest.mark.skipif(
    not ALLE, reason="Beispielinstanzen fehlen: 'python scripts/kosit_regeln_holen.py' im Ordner backend ausfuehren"
)

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
}


def _erwartet(datei: Path) -> tuple[str, Decimal, str | None, bool]:
    """(Syntax, Gesamtbetrag laut Datei, Rechnungsnummer, ist_gutschrift)"""
    baum = etree.parse(str(datei)).getroot()
    name = etree.QName(baum)
    if name.localname == "CrossIndustryInvoice":
        betrag = baum.xpath("string(.//ram:GrandTotalAmount)", namespaces=NS)
        nummer = baum.xpath("string(rsm:ExchangedDocument/ram:ID)", namespaces=NS)
        typ = baum.xpath("string(rsm:ExchangedDocument/ram:TypeCode)", namespaces=NS)
        return "cii", Decimal(betrag), nummer or None, typ == "381"
    betrag = baum.xpath("string(cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount)", namespaces=NS)
    nummer = baum.xpath("string(cbc:ID)", namespaces=NS)
    typ = baum.xpath("string(cbc:InvoiceTypeCode|cbc:CreditNoteTypeCode)", namespaces=NS)
    return "ubl", Decimal(betrag), nummer or None, name.localname == "CreditNote" or typ == "381"


@pytest.mark.parametrize("datei", ALLE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_beispielinstanz_wird_gelesen_oder_als_gutschrift_abgelehnt(datei: Path):
    syntax, betrag, nummer, gutschrift = _erwartet(datei)
    if gutschrift:
        # Gutschriften liest Bilantiq bewusst noch nicht automatisch (siehe e_rechnung.py), sie fallen auf die Handerfassung zurueck.
        with pytest.raises(EInvoiceFehler, match="Gutschrift"):
            lese_e_rechnung(datei.read_bytes())
        return
    daten = lese_e_rechnung(datei.read_bytes())
    assert daten.syntax == syntax
    assert daten.brutto == betrag
    assert daten.rechnungsnummer == nummer
    assert daten.verkaeufer_name
