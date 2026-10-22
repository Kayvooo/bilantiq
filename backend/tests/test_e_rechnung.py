from datetime import date
from io import BytesIO

import pikepdf
import pytest
from fastapi.testclient import TestClient

from app.receipts.e_rechnung import EInvoiceFehler, lese_e_rechnung
from tests.test_invoices import _invoice_payload, _kontakt
from tests.test_invoices import _onboarded_mandant as _mandant
from tests.test_receipts import (
    _clear_extractor_override,  # noqa: F401  (autouse-Fixture)
    _extraction,
    _FakeExtractor,
    _onboarded_mandant,
    _use_extractor,
)


def cii_xml(
    *,
    nummer: str = "RE-2026-0042",
    datum: str = "20261005",
    faellig: str = "20261019",
    waehrung: str = "EUR",
    typ: str = "380",
    produkt: str = "Webhosting Paket Business",
    verkaeufer: str = "Nordwind Hosting GmbH",
    ust_id: str = "DE111222333",
    steuern: tuple[tuple[str, str, str], ...] = (("19.00", "100.00", "19.00"),),
    brutto: str = "119.00",
) -> bytes:
    steuer_xml = "".join(
        f"<ram:ApplicableTradeTax><ram:CalculatedAmount>{steuer}</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>"
        f"<ram:BasisAmount>{basis}</ram:BasisAmount><ram:CategoryCode>S</ram:CategoryCode>"
        f"<ram:RateApplicablePercent>{satz}</ram:RateApplicablePercent></ram:ApplicableTradeTax>"
        for satz, basis, steuer in steuern
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
    xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocument>
    <ram:ID>{nummer}</ram:ID><ram:TypeCode>{typ}</ram:TypeCode>
    <ram:IssueDateTime><udt:DateTimeString format="102">{datum}</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:SpecifiedTradeProduct><ram:Name>{produkt}</ram:Name></ram:SpecifiedTradeProduct>
    </ram:IncludedSupplyChainTradeLineItem>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>{verkaeufer}</ram:Name>
        <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{ust_id}</ram:ID></ram:SpecifiedTaxRegistration>
      </ram:SellerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>{waehrung}</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementPaymentMeans>
        <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>DE02120300000000202051</ram:IBANID></ram:PayeePartyCreditorFinancialAccount>
      </ram:SpecifiedTradeSettlementPaymentMeans>
      {steuer_xml}
      <ram:SpecifiedTradePaymentTerms>
        <ram:DueDateDateTime><udt:DateTimeString format="102">{faellig}</udt:DateTimeString></ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:GrandTotalAmount>{brutto}</ram:GrandTotalAmount><ram:DuePayableAmount>{brutto}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>""".encode()


def _hochladen(client: TestClient, headers: dict, daten: bytes, *, name: str = "rechnung.xml", typ: str = "application/xml", force: bool = False):
    return client.post(
        "/belege", headers=headers, files={"file": (name, daten, typ)}, data={"force": "true" if force else "false"},
    )


def _pdf_mit_anhang(name: str, inhalt: bytes) -> bytes:
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page()
        pdf.attachments[name] = inhalt
        puffer = BytesIO()
        pdf.save(puffer)
    return puffer.getvalue()


def _finale_rechnung(client: TestClient, headers: dict) -> dict:
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    return client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()


def test_eigene_xrechnung_wird_exakt_gelesen_round_trip(client: TestClient):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)
    xml = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers).content

    antwort = _hochladen(client, headers, xml)

    assert antwort.status_code == 201, antwort.text
    beleg = antwort.json()
    assert beleg["beleg_typ"] == "xrechnung"
    assert beleg["status"] == "geprueft"
    assert beleg["betrag"] == {"wert": "1240.00", "confidence": 0.99, "unklar": False}
    assert beleg["anbieter"]["wert"] == "Kevin GmbH"
    assert beleg["rechnungsnummer"] == rechnung["nummer"]
    assert beleg["datum"]["wert"] == date.today().isoformat()
    assert beleg["faelligkeit"] == rechnung["faelligkeitsdatum"]
    assert beleg["ust_satz"]["unklar"] is True  # zwei Saetze, siehe Aufteilung
    assert beleg["steueranteile_vorschlag"] == [
        {"ust_satz": "0.00", "bruttobetrag": "50.00"},
        {"ust_satz": "19.00", "bruttobetrag": "1190.00"},
    ]
    assert beleg["hinweise"] == []


def test_cii_xrechnung_mit_einem_steuersatz(client: TestClient):
    headers = _onboarded_mandant(client)

    beleg = _hochladen(client, headers, cii_xml()).json()

    assert beleg["beleg_typ"] == "xrechnung"
    assert beleg["betrag"]["wert"] == "119.00"
    assert beleg["datum"]["wert"] == "2026-10-05"
    assert beleg["faelligkeit"] == "2026-10-19"
    assert beleg["anbieter"]["wert"] == "Nordwind Hosting GmbH"
    assert beleg["rechnungsnummer"] == "RE-2026-0042"
    assert beleg["iban"] == "DE02120300000000202051"
    assert beleg["ust_satz"] == {"wert": "19.00", "confidence": 0.99, "unklar": False}
    assert beleg["steueranteile_vorschlag"] is None
    assert beleg["kategorie_vorschlag"]["wert"] == "Software/IT"


def test_cii_mit_zwei_steuersaetzen_liefert_aufteilung(client: TestClient):
    headers = _onboarded_mandant(client)
    xml = cii_xml(steuern=(("7.00", "10.00", "0.70"), ("19.00", "100.00", "19.00")), brutto="129.70")

    beleg = _hochladen(client, headers, xml).json()

    assert beleg["betrag"]["wert"] == "129.70"
    assert beleg["ust_satz"]["unklar"] is True
    assert beleg["steueranteile_vorschlag"] == [
        {"ust_satz": "7.00", "bruttobetrag": "10.70"},
        {"ust_satz": "19.00", "bruttobetrag": "119.00"},
    ]


def test_gelesene_e_rechnung_laesst_sich_ohne_nachtippen_buchen(client: TestClient):
    headers = _onboarded_mandant(client)
    beleg = _hochladen(client, headers, cii_xml()).json()

    antwort = client.post(f"/belege/{beleg['id']}/bestaetigen", headers=headers, json={})

    assert antwort.status_code == 201, antwort.text
    ausgabe = antwort.json()
    assert (ausgabe["anbieter"], ausgabe["kategorie"], ausgabe["datum"]) == ("Nordwind Hosting GmbH", "Software/IT", "2026-10-05")
    assert ausgabe["betrag"] == "119.00"


def test_vorgeschlagene_aufteilung_wird_beim_buchen_akzeptiert(client: TestClient):
    headers = _onboarded_mandant(client)
    xml = cii_xml(steuern=(("7.00", "10.00", "0.70"), ("19.00", "100.00", "19.00")), brutto="129.70")
    beleg = _hochladen(client, headers, xml).json()

    antwort = client.post(
        f"/belege/{beleg['id']}/bestaetigen", headers=headers, json={"steueranteile": beleg["steueranteile_vorschlag"]},
    )

    assert antwort.status_code == 201, antwort.text


def test_zugferd_pdf_wird_aus_dem_eingebetteten_xml_gelesen(client: TestClient):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)
    pdf = client.post(f"/invoices/{rechnung['id']}/zugferd-pdf", headers=headers)
    assert pdf.status_code == 200

    beleg = _hochladen(client, headers, pdf.content, name="rechnung.pdf", typ="application/pdf", force=True).json()

    assert beleg["beleg_typ"] == "zugferd"
    assert beleg["betrag"]["wert"] == "1240.00"
    assert beleg["rechnungsnummer"] == rechnung["nummer"]
    assert beleg["betrag"]["confidence"] == 0.99


def test_pdf_mit_cii_anhang_namens_factur_x_wird_gelesen(client: TestClient):
    headers = _onboarded_mandant(client)

    beleg = _hochladen(client, headers, _pdf_mit_anhang("factur-x.xml", cii_xml()), name="r.pdf", typ="application/pdf").json()

    assert beleg["beleg_typ"] == "zugferd"
    assert beleg["anbieter"]["wert"] == "Nordwind Hosting GmbH"


@pytest.mark.parametrize("anhang", [None, ("factur-x.xml", b"das ist kein xml"), ("notiz.txt", b"hallo")])
def test_pdf_ohne_lesbare_e_rechnung_faellt_auf_texterkennung_zurueck(client: TestClient, anhang):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(anbieter=("OCR Anbieter GmbH", 0.9))))
    with pikepdf.Pdf.new() as pdf:
        pdf.add_blank_page()
        if anhang:
            pdf.attachments[anhang[0]] = anhang[1]
        puffer = BytesIO()
        pdf.save(puffer)

    beleg = _hochladen(client, headers, puffer.getvalue(), name="r.pdf", typ="application/pdf").json()

    assert beleg["beleg_typ"] == "ocr"
    assert beleg["anbieter"]["wert"] == "OCR Anbieter GmbH"


def test_dieselbe_rechnung_als_xml_und_als_pdf_ist_ein_duplikat(client: TestClient):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)
    xml = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers).content
    pdf = client.post(f"/invoices/{rechnung['id']}/zugferd-pdf", headers=headers).content
    erster = _hochladen(client, headers, xml).json()

    zweiter = _hochladen(client, headers, pdf, name="r.pdf", typ="application/pdf").json()

    assert zweiter["ist_duplikat"] is True
    assert zweiter["duplikat_von"] == erster["id"]
    assert len(client.get("/belege", headers=headers).json()) == 1


def test_dieselbe_xml_zweimal_ist_ein_duplikat_und_force_legt_neu_an(client: TestClient):
    headers = _onboarded_mandant(client)
    xml = cii_xml()
    erster = _hochladen(client, headers, xml).json()

    assert _hochladen(client, headers, xml).json()["ist_duplikat"] is True
    dritter = _hochladen(client, headers, xml, force=True).json()
    assert dritter["ist_duplikat"] is False and dritter["id"] != erster["id"]


def test_gleiche_rechnungsnummer_eines_anderen_mandanten_ist_kein_duplikat(client: TestClient):
    kopf_a = _onboarded_mandant(client, email="a@example.com")
    kopf_b = _onboarded_mandant(client, email="b@example.com")
    _hochladen(client, kopf_a, cii_xml())

    fremd = _hochladen(client, kopf_b, cii_xml()).json()

    assert fremd["ist_duplikat"] is False


def test_fremdwaehrung_uebernimmt_keinen_betrag_und_weist_darauf_hin(client: TestClient):
    headers = _onboarded_mandant(client)

    beleg = _hochladen(client, headers, cii_xml(waehrung="USD")).json()

    assert beleg["betrag"]["unklar"] is True
    assert beleg["status"] == "unklar"
    assert any("USD" in hinweis for hinweis in beleg["hinweise"])


def test_nicht_unterstuetzter_steuersatz_wird_als_hinweis_gemeldet(client: TestClient):
    headers = _onboarded_mandant(client)

    beleg = _hochladen(client, headers, cii_xml(steuern=(("5.00", "100.00", "5.00"),), brutto="105.00")).json()

    assert beleg["ust_satz"]["unklar"] is True
    assert any("5.00 %" in hinweis for hinweis in beleg["hinweise"])


def test_abweichende_aufteilung_wird_als_hinweis_gemeldet(client: TestClient):
    headers = _onboarded_mandant(client)
    xml = cii_xml(steuern=(("7.00", "10.00", "0.70"), ("19.00", "100.00", "19.00")), brutto="130.00")

    beleg = _hochladen(client, headers, xml).json()

    assert any("weicht" in hinweis for hinweis in beleg["hinweise"])


@pytest.mark.parametrize(
    "xml,teil_der_meldung",
    [
        (cii_xml(typ="381"), "Gutschriften"),
        (b'<?xml version="1.0"?><CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"/>', "Gutschriften"),
        (b'<?xml version="1.0"?><Rechnung><Betrag>5</Betrag></Rechnung>', "keine unterstützte E-Rechnung"),
        (b'<?xml version="1.0"?><a><b></a>', "kein gültiges XML"),
        (b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/hostname">]><a>&x;</a>', "DOCTYPE"),
    ],
)
def test_ungeeignete_xml_dateien_werden_verstaendlich_abgelehnt(client: TestClient, xml, teil_der_meldung):
    headers = _onboarded_mandant(client)

    antwort = _hochladen(client, headers, xml)

    assert antwort.status_code == 400
    assert teil_der_meldung in antwort.json()["detail"]
    assert client.get("/belege", headers=headers).json() == []


def test_xml_ohne_gesamtbetrag_wird_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)
    ohne_summen = cii_xml().replace(b"GrandTotalAmount", b"Sonstiges").replace(b"DuePayableAmount", b"Sonstiges2")

    antwort = _hochladen(client, headers, ohne_summen)

    assert antwort.status_code == 400
    assert "Gesamtbetrag" in antwort.json()["detail"]


def test_original_xml_wird_unveraendert_und_als_download_ausgeliefert(client: TestClient):
    headers = _onboarded_mandant(client)
    xml = cii_xml()
    beleg = _hochladen(client, headers, xml).json()

    antwort = client.get(f"/belege/{beleg['id']}/datei", headers=headers)

    assert antwort.content == xml
    assert antwort.headers["content-type"].startswith("application/xml")
    assert antwort.headers["content-disposition"].startswith("attachment")


def test_e_rechnungen_haben_kein_monatslimit(client: TestClient):
    headers = _mandant(client)
    for nummer in range(12):
        assert _hochladen(client, headers, cii_xml(nummer=f"RE-{nummer}")).status_code == 201


def test_parser_liest_datum_in_beiden_cii_schreibweisen():
    assert lese_e_rechnung(cii_xml(datum="20260131")).datum == date(2026, 1, 31)


def test_parser_lehnt_dateien_ohne_gueltiges_xml_mit_fachfehler_ab():
    with pytest.raises(EInvoiceFehler):
        lese_e_rechnung(b"kein xml")


def test_datenexport_enthaelt_die_gelesenen_e_rechnungs_daten_aber_keinen_blind_index(client: TestClient):
    headers = _onboarded_mandant(client)
    _hochladen(client, headers, cii_xml())

    export = client.get("/auth/datenexport", headers=headers).json()

    [beleg] = export["belege"]
    assert beleg["beleg_typ"] == "xrechnung"
    assert beleg["rechnungsnummer"] == "RE-2026-0042"
    assert beleg["iban"] == "DE02120300000000202051"
    assert "dedupe_key" not in beleg
