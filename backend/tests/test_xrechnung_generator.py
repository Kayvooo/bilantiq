"""Der XRechnung-Generator (app/invoices/e_invoice.py) gegen die XRechnung-Regeln.

Die Faelle laufen ohne Datenbank mit Objekten im Speicher. Die Pruef-Tests brauchen die Regeln aus
``scripts/kosit_regeln_holen.py`` (sonst Skip mit Meldung; in CI laufen sie, siehe backend-ci.yml). Die Tests ohne
``braucht_regeln`` laufen immer."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from lxml import etree

from app.auth.models import Mandant
from app.invoices.e_invoice import (
    EAS_LEITWEG_ID,
    KLEINUNTERNEHMER_HINWEIS,
    XRECHNUNG_CUSTOMIZATION_ID,
    build_xrechnung_xml,
    missing_pflichtfelder,
    runde,
    zerlege_anschrift,
)
from app.invoices.e_invoice_validation import STATUS_BESTANDEN, validate_xrechnung
from app.invoices.models import Invoice, InvoicePosition, Kontakt
from app.invoices.routes import compute_invoice_totals
from tests.test_e_invoice_validation import braucht_regeln

NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def mandant(**felder) -> Mandant:
    werte = dict(
        firmenname="Muster Beratung GmbH", ust_id="DE123456789", steuernummer=None,
        adresse="Musterstr. 1, 10115 Berlin", iban="DE02 1203 0000 0000 2020 51", bic=None,
        telefon="+49 30 1234567", kontakt_email="rechnung@muster-beratung.example",
    )
    werte.update(felder)
    return Mandant(**werte)


def kontakt(**felder) -> Kontakt:
    werte = dict(
        name="Beispiel Kunde GmbH", strasse="Kundenweg 2", plz="80331", ort="München", land="DE",
        email="einkauf@kunde.example",
    )
    werte.update(felder)
    return Kontakt(**werte)


def position(beschreibung: str, menge: str, preis: str, satz: str = "19.00", **felder) -> InvoicePosition:
    return InvoicePosition(
        reihenfolge=0, beschreibung=beschreibung, menge=Decimal(menge), einzelpreis=Decimal(preis),
        ust_satz=Decimal(satz), **felder,
    )


def rechnung(positionen: list[InvoicePosition], *, kontakt_=None, **felder) -> Invoice:
    for nr, p in enumerate(positionen):
        p.reihenfolge = nr
    netto, ust, brutto = compute_invoice_totals(positionen)
    werte = dict(
        nummer="RE-2026-0001", leistungsdatum=date(2026, 10, 1), faelligkeitsdatum=date(2026, 10, 15), waehrung="EUR",
        netto_gesamt=netto, ust_gesamt=ust, brutto_gesamt=brutto, status="final",
        finalisiert_am=datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc), kontakt=kontakt_ or kontakt(),
    )
    werte.update(felder)
    invoice = Invoice(**werte)
    invoice.positionen = positionen
    return invoice


def storno_von(original: Invoice) -> Invoice:
    """So legt routes.storno_invoice die Stornorechnung an: gleiche Positionen mit negiertem Einzelpreis."""
    positionen = [
        position(f"Storno: {p.beschreibung}", str(p.menge), str(-p.einzelpreis), str(p.ust_satz)) for p in original.positionen
    ]
    return rechnung(positionen, kontakt_=original.kontakt, nummer="RE-2026-0002", korrigiert_invoice_id="original-id")


def xml_baum(xml: bytes) -> etree._Element:
    return etree.fromstring(xml)


def text(baum, pfad: str) -> str | None:
    gefunden = baum.xpath(pfad, namespaces=NS)
    return gefunden[0].text if gefunden else None


def pruefen(xml: bytes):
    ergebnis = validate_xrechnung(xml)
    assert ergebnis.status == STATUS_BESTANDEN, ergebnis.kurztext(max_fehler=10)
    return ergebnis


# --- Faelle gegen die Regeln -------------------------------------------------------------------------------------

@braucht_regeln
def test_ein_steuersatz_19_prozent():
    xml = build_xrechnung_xml(mandant(), rechnung([position("Beratung", "2", "500.00")]))
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cbc:CustomizationID") == XRECHNUNG_CUSTOMIZATION_ID
    assert text(baum, "cbc:InvoiceTypeCode") == "380"
    assert text(baum, "cac:LegalMonetaryTotal/cbc:PayableAmount") == "1190.00"
    assert text(baum, "cac:TaxTotal/cbc:TaxAmount") == "190.00"


@braucht_regeln
def test_ein_steuersatz_7_prozent():
    xml = build_xrechnung_xml(mandant(), rechnung([position("Fachbuch", "3", "24.90", "7.00")]))
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent") == "7.00"
    assert text(baum, "cac:TaxTotal/cbc:TaxAmount") == "5.23"  # 74.70 * 7 % = 5.229


@braucht_regeln
def test_null_prozent_ist_nullsatz_z():
    xml = build_xrechnung_xml(mandant(), rechnung([position("Auslagenersatz", "1", "80.00", "0.00")]))
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID") == "Z"
    assert text(baum, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReason") is None


@braucht_regeln
def test_kleinunternehmer_paragraf_19_ist_steuerbefreit_mit_grund():
    xml = build_xrechnung_xml(
        mandant(), rechnung([position("Webdesign", "10", "65.00", "0.00")]), kleinunternehmer=True,
    )
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:ID") == "E"
    assert text(baum, "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReason") == KLEINUNTERNEHMER_HINWEIS
    assert text(baum, "cac:LegalMonetaryTotal/cbc:PayableAmount") == "650.00"


@braucht_regeln
def test_gemischte_steuersaetze_19_7_und_0():
    positionen = [
        position("Beratung", "2", "500.00", "19.00"),
        position("Fachbuch", "3", "24.90", "7.00"),
        position("Reisekosten", "1", "50.00", "0.00"),
    ]
    xml = build_xrechnung_xml(mandant(), rechnung(positionen))
    pruefen(xml)
    baum = xml_baum(xml)
    assert [s.text for s in baum.xpath("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent", namespaces=NS)] == [
        "0.00", "7.00", "19.00",
    ]
    assert text(baum, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount") == "1319.93"


@braucht_regeln
def test_stornorechnung_wird_credit_note_381_mit_positiven_betraegen():
    original = rechnung([position("Beratung", "2", "500.00"), position("Reisekosten", "1", "50.00", "0.00")])
    storno = storno_von(original)
    assert storno.brutto_gesamt < 0  # intern negativ gespeichert
    xml = build_xrechnung_xml(mandant(), storno, korrigierte_rechnungsnummer="RE-2026-0001")
    pruefen(xml)
    baum = xml_baum(xml)
    assert etree.QName(baum).localname == "CreditNote"
    assert text(baum, "cbc:CreditNoteTypeCode") == "381"
    assert text(baum, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID") == "RE-2026-0001"
    assert text(baum, "cac:LegalMonetaryTotal/cbc:PayableAmount") == "1240.00"
    assert text(baum, "cac:CreditNoteLine/cac:Price/cbc:PriceAmount") == "500.00"
    assert text(baum, "cac:CreditNoteLine/cbc:LineExtensionAmount") == "1000.00"
    assert text(baum, "cac:CreditNoteLine/cbc:CreditedQuantity") == "2"


def test_stornorechnung_braucht_die_nummer_der_ursprungsrechnung():
    storno = storno_von(rechnung([position("Beratung", "1", "100.00")]))
    with pytest.raises(ValueError, match="stornierten Rechnung"):
        build_xrechnung_xml(mandant(), storno)


@braucht_regeln
def test_leitweg_id_wird_zur_kaeuferreferenz_bt_10():
    k = kontakt(leitweg_id="991-01234-06")
    xml = build_xrechnung_xml(mandant(), rechnung([position("Beratung", "1", "100.00")], kontakt_=k))
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cbc:BuyerReference") == "991-01234-06"
    assert text(baum, "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID") == "einkauf@kunde.example"


@braucht_regeln
def test_behoerde_ohne_e_mail_nutzt_die_leitweg_id_als_elektronische_adresse():
    k = kontakt(leitweg_id="991-01234-06", email=None)
    xml = build_xrechnung_xml(mandant(), rechnung([position("Beratung", "1", "100.00")], kontakt_=k))
    pruefen(xml)
    endpoint = xml_baum(xml).xpath("cac:AccountingCustomerParty/cac:Party/cbc:EndpointID", namespaces=NS)[0]
    assert endpoint.get("schemeID") == EAS_LEITWEG_ID
    assert endpoint.text == "991-01234-06"


@braucht_regeln
def test_ohne_leitweg_id_ist_die_kundennummer_die_kaeuferreferenz():
    k = kontakt(kundennummer="K-4711")
    xml = build_xrechnung_xml(mandant(), rechnung([position("Beratung", "1", "100.00")], kontakt_=k))
    pruefen(xml)
    assert text(xml_baum(xml), "cbc:BuyerReference") == "K-4711"


@braucht_regeln
def test_skonto_wird_im_xrechnung_format_ausgegeben():
    invoice = rechnung([position("Beratung", "1", "1000.00")], skonto_tage=14, skonto_prozent=Decimal("2"))
    xml = build_xrechnung_xml(mandant(), invoice)
    pruefen(xml)
    assert text(xml_baum(xml), "cac:PaymentTerms/cbc:Note") == "#SKONTO#TAGE=14#PROZENT=2.00#\n"


@braucht_regeln
def test_viele_positionen_mit_artikelnummer():
    positionen = [
        position(f"Position {n}", str(n), "12.34", "19.00" if n % 2 else "7.00", artikelnummer=f"ART-{n:03d}")
        for n in range(1, 31)
    ]
    xml = build_xrechnung_xml(mandant(), rechnung(positionen))
    pruefen(xml)
    baum = xml_baum(xml)
    assert len(baum.xpath("cac:InvoiceLine", namespaces=NS)) == 30
    assert text(baum, "cac:InvoiceLine/cac:Item/cac:SellersItemIdentification/cbc:ID") == "ART-001"


@braucht_regeln
def test_rundung_umsatzsteuer_wird_je_satz_aus_der_zeilensumme_berechnet():
    # Einzeln gerundet waeren es 3 x 0,19 = 0,57, richtig (je Steuersatz aus der Summe 2,97) sind 0,56.
    positionen = [position("Kleinteil", "1", "0.99") for _ in range(3)]
    invoice = rechnung(positionen)
    assert invoice.ust_gesamt == Decimal("0.56")
    xml = build_xrechnung_xml(mandant(), invoice)
    pruefen(xml)
    baum = xml_baum(xml)
    assert text(baum, "cac:TaxTotal/cbc:TaxAmount") == "0.56"
    assert text(baum, "cac:LegalMonetaryTotal/cbc:PayableAmount") == "3.53"


@braucht_regeln
@pytest.mark.parametrize(
    ("menge", "preis", "erwartet_zeile"),
    [
        ("1", "1.005", "1.01"),  # halbe Cent kaufmaennisch aufrunden (nicht auf gerade Ziffer)
        ("1", "2.675", "2.68"),
        ("3", "0.3333", "1.00"),  # Preis mit vier Nachkommastellen
        ("2.5", "87.50", "218.75"),  # gebrochene Menge
        ("0.333", "10.00", "3.33"),
        ("1000000", "0.01", "10000.00"),
    ],
)
def test_rundung_zeilenbetraege(menge: str, preis: str, erwartet_zeile: str):
    invoice = rechnung([position("Leistung", menge, preis)])
    xml = build_xrechnung_xml(mandant(), invoice)
    pruefen(xml)
    assert text(xml_baum(xml), "cac:InvoiceLine/cbc:LineExtensionAmount") == erwartet_zeile


@braucht_regeln
def test_nur_steuernummer_wird_als_fc_gemeldet():
    xml = build_xrechnung_xml(mandant(ust_id=None, steuernummer="12/345/67890"), rechnung([position("Beratung", "1", "100.00")]))
    pruefen(xml)
    schema = xml_baum(xml).xpath(
        "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme[cac:TaxScheme/cbc:ID='FC']/cbc:CompanyID", namespaces=NS
    )
    assert [s.text for s in schema] == ["12/345/67890"]
    assert text(xml_baum(xml), "cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID") == "12/345/67890"


@braucht_regeln
def test_ust_idnr_und_steuernummer_zusammen_und_ust_id_mit_leerzeichen():
    xml = build_xrechnung_xml(
        mandant(ust_id="DE 123 456 789", steuernummer="12/345/67890"), rechnung([position("Beratung", "1", "100.00")])
    )
    pruefen(xml)
    ids = xml_baum(xml).xpath("cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", namespaces=NS)
    assert [i.text for i in ids] == ["DE123456789", "12/345/67890"]


@braucht_regeln
def test_kaeufer_im_ausland_mit_ust_id():
    k = kontakt(name="Alpen Handel GmbH", strasse="Ringstraße 5", plz="1010", ort="Wien", land="AT", ust_id="ATU 1234 5678")
    xml = build_xrechnung_xml(mandant(), rechnung([position("Beratung", "1", "100.00")], kontakt_=k))
    pruefen(xml)
    assert text(xml_baum(xml), "cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID") == "ATU12345678"


@braucht_regeln
def test_sonderzeichen_und_zeilenumbrueche_in_texten():
    k = kontakt(name='Müller & Söhne <Bau> "GmbH"')
    xml = build_xrechnung_xml(
        mandant(firmenname="Ärzte-Büro Schäfer & Co. KG"),
        rechnung([position("Zeile eins\nZeile zwei & <mehr>", "1", "10.00")], kontakt_=k),
    )
    pruefen(xml)
    assert text(xml_baum(xml), "cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name") == 'Müller & Söhne <Bau> "GmbH"'


@braucht_regeln
def test_bic_wird_mitgegeben():
    xml = build_xrechnung_xml(mandant(bic="bykodeff"), rechnung([position("Beratung", "1", "100.00")]))
    pruefen(xml)
    assert text(xml_baum(xml), "cac:PaymentMeans/cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID") == "BYKODEFF"


# --- Ohne Regeln lauffaehig ---------------------------------------------------------------------------------------

def test_fehlende_pflichtfelder_werden_einzeln_benannt():
    leer = mandant(ust_id=None, steuernummer=None, adresse=None, iban=None, telefon=None, kontakt_email=None)
    fehlt = missing_pflichtfelder(leer, rechnung([position("Beratung", "1", "100.00")], kontakt_=kontakt(email=None)))
    assert "USt-IdNr. oder Steuernummer (Verkaeufer)" in fehlt
    assert "Anschrift (Verkaeufer)" in fehlt
    assert "IBAN (Verkaeufer)" in fehlt
    assert "Telefonnummer (Verkaeufer)" in fehlt
    assert "E-Mail-Adresse fuer Rueckfragen (Verkaeufer)" in fehlt
    assert "E-Mail-Adresse (Kaeufer)" in fehlt


@pytest.mark.parametrize(
    ("adresse", "erwartet"),
    [
        ("Musterstr. 1, 10115 Berlin", ("Musterstr. 1", "10115", "Berlin")),
        ("Musterstr. 1\n10115 Berlin", ("Musterstr. 1", "10115", "Berlin")),
        ("Firma X, Hinterhof, Musterstr. 1, 80331 München, Deutschland", ("Firma X, Hinterhof, Musterstr. 1", "80331", "München")),
        ("Musterstr. 1, D-10115 Berlin", ("Musterstr. 1", "10115", "Berlin")),
    ],
)
def test_anschrift_wird_zerlegt(adresse: str, erwartet: tuple[str, str, str]):
    anschrift = zerlege_anschrift(adresse)
    assert (anschrift.strasse, anschrift.plz, anschrift.ort) == erwartet


@pytest.mark.parametrize("adresse", [None, "", "Musterstr. 1", "10115 Berlin", "Musterstr. 1, Berlin"])
def test_nicht_lesbare_anschrift_ist_ein_fehlendes_pflichtfeld(adresse):
    assert zerlege_anschrift(adresse) is None
    fehlt = missing_pflichtfelder(mandant(adresse=adresse), rechnung([position("Beratung", "1", "100.00")]))
    assert any(eintrag.startswith("Anschrift (Verkaeufer)") for eintrag in fehlt)
    with pytest.raises(ValueError, match="Anschrift"):
        build_xrechnung_xml(mandant(adresse=adresse), rechnung([position("Beratung", "1", "100.00")]))


def test_rundung_ist_kaufmaennisch():
    assert runde(Decimal("0.005")) == Decimal("0.01")
    assert runde(Decimal("-0.005")) == Decimal("-0.01")
    assert runde(Decimal("2.675")) == Decimal("2.68")
    assert runde(Decimal("1E+2")) == Decimal("100.00")


def test_storno_summen_sind_exakt_das_negativ_des_originals():
    original = rechnung([position("A", "3", "0.99"), position("B", "1", "1.005", "7.00")])
    storno = storno_von(original)
    assert storno.netto_gesamt == -original.netto_gesamt
    assert storno.ust_gesamt == -original.ust_gesamt
    assert storno.brutto_gesamt == -original.brutto_gesamt


def test_zahlen_stehen_nie_in_exponentenschreibweise():
    invoice = rechnung([position("Gross", "1E+3", "1E+1")])
    xml = build_xrechnung_xml(mandant(), invoice).decode()
    assert "E+" not in xml
