import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.receipts.ai_extraction import (
    ExtractedField,
    ExtractionUnavailable,
    ReceiptExtraction,
    get_extractor,
    parse_ocr_text,
)
from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)

FAKE_IMAGE = b"\x89PNG\r\n\x1a\nnot-a-real-png-but-bytes-are-all-we-hash"


class _FakeExtractor:
    def __init__(self, extraction: ReceiptExtraction | None = None, unavailable: bool = False):
        self._extraction = extraction
        self._unavailable = unavailable

    def extract(self, file_bytes: bytes, mime_type: str) -> ReceiptExtraction:
        if self._unavailable:
            raise ExtractionUnavailable("simuliert fuer Test")
        assert self._extraction is not None
        return self._extraction


def _extraction(*, begruendung: str = "Bahnticket, klar als Reisekosten erkennbar.", **overrides) -> ReceiptExtraction:
    defaults = dict(
        betrag=("49.90", 0.95), datum=("2026-09-01", 0.9), anbieter=("Bahn GmbH", 0.9),
        ust_satz=("19.00", 0.9), kategorie_vorschlag=("Reisekosten", 0.8),
    )
    defaults.update(overrides)
    return ReceiptExtraction(
        begruendung=begruendung,
        **{field: ExtractedField(wert=wert, confidence=conf) for field, (wert, conf) in defaults.items()},
    )


@pytest.fixture(autouse=True)
def _clear_extractor_override():
    yield
    app.dependency_overrides.pop(get_extractor, None)


def _use_extractor(fake: _FakeExtractor) -> None:
    app.dependency_overrides[get_extractor] = lambda: fake


def _upload(client: TestClient, headers: dict, *, filename="beleg.png", content_type="image/png", data=None, force=False):
    return client.post(
        "/belege", headers=headers, files={"file": (filename, FAKE_IMAGE, content_type)},
        data={"force": "true" if force else "false"},
    )


def test_local_parser_extracts_clear_labelled_fields():
    extraction = parse_ocr_text(
        """DB Vertrieb GmbH
        Fahrkarte Berlin - Hamburg
        Rechnungsdatum: 01.09.2026
        MwSt 19 %
        Gesamtbetrag 49,90 EUR
        """
    )

    assert extraction.betrag == ExtractedField(wert="49.90", confidence=0.92)
    assert extraction.datum == ExtractedField(wert="2026-09-01", confidence=0.92)
    assert extraction.anbieter == ExtractedField(wert="DB Vertrieb GmbH", confidence=0.9)
    assert extraction.ust_satz == ExtractedField(wert="19.00", confidence=0.92)
    assert extraction.kategorie_vorschlag.wert == "Reisekosten"
    assert extraction.kategorie_vorschlag.confidence >= 0.6


def test_local_parser_supports_iso_date_and_german_thousands_separator():
    extraction = parse_ocr_text(
        """Cloud Hosting GmbH
        Rechnungsdatum 2026-08-31
        USt. 19%
        Total: 1.234,56 €
        Webhosting und Domain
        """
    )

    assert extraction.betrag.wert == "1234.56"
    assert extraction.datum.wert == "2026-08-31"
    assert extraction.ust_satz.wert == "19.00"
    assert extraction.kategorie_vorschlag.wert == "Software/IT"
    assert extraction.kategorie_vorschlag.confidence >= 0.6


def test_local_parser_recognises_telekommunikation_category():
    """Regressionstest: Telefon-/Mobilfunkrechnungen (Vodafone, Telekom, o2, ...)
    fielen bisher komplett durchs Raster der Kategorie-Schluesselwoerter und
    landeten unter "Sonstiges", obwohl das ein sehr haeufiger Ausgabentyp ist."""
    extraction = parse_ocr_text(
        """Vodafone GmbH
        Ihre Vodafone-Mobilfunkrechnung
        Gesamt 10,00 EUR
        """
    )

    assert extraction.kategorie_vorschlag.wert == "Telekommunikation"
    assert extraction.kategorie_vorschlag.confidence >= 0.6


def test_local_parser_keeps_unlabelled_largest_amount_below_threshold():
    extraction = parse_ocr_text(
        """Musterladen
        Artikel 4,90
        Artikel 12,50
        Bar 20,00
        """
    )

    assert extraction.betrag.wert == "20.00"
    assert extraction.betrag.confidence == 0.5


def test_local_parser_recognises_plain_betrag_label():
    extraction = parse_ocr_text("Beispielmarkt\nBetrag: EUR 8,99")

    assert extraction.betrag == ExtractedField(wert="8.99", confidence=0.92)


def test_local_parser_removes_decorative_ocr_prefix_from_vendor():
    extraction = parse_ocr_text("® Beispielmarkt GmbH\nGesamt 8,99 EUR")

    assert extraction.anbieter.wert == "Beispielmarkt GmbH"
    assert extraction.anbieter.confidence == 0.9


def test_local_parser_confirms_brutto_from_netto_ust_summenzeile():
    """Regressionstest fuer eine echte Vodafone-Mobilfunkrechnung: die Summenzeile
    einer Netto/USt-Betrag/Brutto-Uebersicht ("Gesamt 80,79 3,19 83,98") wurde
    zuvor wegen mehrerer Zahlen auf einer Total-Zeile auf Konfidenz 0.5 abgewertet,
    obwohl der Bruttobetrag rechnerisch (Netto + USt = Brutto) eindeutig ist."""
    extraction = parse_ocr_text(
        """Vodafone GmbH
        Details Netto in EUR USt.-Satz Brutto in EUR
        1 GigaMobil M mit Top Smartphone 75,6218 19% 89,99
        Gesamt 80,79 3,19 83,98
        """
    )

    assert extraction.betrag == ExtractedField(wert="83.98", confidence=0.92)


def test_local_parser_ignores_compound_noise_words_and_greeting_for_vendor():
    """Regressionstest: "Rechnungsnummer"/"Kundennummer" wurden vom Rausch-Filter
    nicht erkannt, weil \\b vor einem angehaengten Kompositum nie greift ("...gs"
    vor "nummer" ist keine Wortgrenze) -- die Kopfzeile wurde dadurch faelschlich
    als Anbieter uebernommen. Eine Anrede an den Kunden ("Hallo ...") darf ebenfalls
    nicht als Anbieter durchrutschen."""
    extraction = parse_ocr_text(
        """Rechnungsnummer Kundennummer Seite
        Hallo Max Mustermann,
        Beispiel Telekom GmbH
        Gesamt 10,00 EUR
        """
    )

    assert extraction.anbieter.wert == "Beispiel Telekom GmbH"
    assert extraction.anbieter.confidence == 0.9


def test_local_parser_finds_vendor_in_impressum_footer_when_header_is_unusable():
    """Regressionstest: bei einem mehrspaltigen Layout (Kundenanschrift und
    Rechnungskopf durcheinander in der OCR-Lesereihenfolge, wie bei echten
    Vodafone-Rechnungen) liefern die ersten Zeilen keinen brauchbaren Anbieter.
    Die Impressum-Fusszeile (Pflichtangabe nach §5 DDG: Firma + eigene Domain)
    ist dann zuverlaessiger."""
    extraction = parse_ocr_text(
        """Hallo Max Mustermann,
        Musterstrasse 1
        12345 Musterstadt
        Ihr Rechnungsbetrag ist:
        10,00 EUR
        Zusammenfassung
        Rechnungsdetails
        weitere Details zum Vertrag
        Gesamt 10,00 EUR
        Beispiel Telekom GmbH, Musterallee 1, 10115 Berlin | beispiel-telekom.de
        Telefon: 0800 1234567
        """
    )

    assert extraction.anbieter.wert == "Beispiel Telekom GmbH"
    assert extraction.anbieter.confidence == 0.85


def test_local_parser_recognises_rechnung_vom_split_across_ocr_lines():
    """Regressionstest: OCR trennt "Ihre Rechnung vom" haeufig vom eigentlichen
    Datum in die naechste Zeile (Spaltenumbruch/Layout). Das Label muss trotzdem
    fuer die Folgezeile gelten, sonst bleibt ein eindeutiges Rechnungsdatum
    [UNKLAR], obwohl das Dokument mehrere andere Datumsangaben (Zeitraum,
    Faelligkeit) enthaelt."""
    extraction = parse_ocr_text(
        """Beispiel Telekom GmbH
        den Zeitraum vom 01.08.2026 bis 31.08.2026
        Ihre Rechnung vom
        16.09.2026
        faellig am 24.09.2026
        Gesamt 10,00 EUR
        """
    )

    assert extraction.datum == ExtractedField(wert="2026-09-16", confidence=0.92)


def test_local_parser_does_not_guess_between_multiple_dates_or_vat_rates():
    extraction = parse_ocr_text(
        """Muster GmbH
        01.08.2026
        03.08.2026
        MwSt 7 %
        MwSt 19 %
        Gesamt 10,00 EUR
        """
    )

    assert extraction.datum.wert is None
    assert extraction.datum.confidence < 0.6
    assert extraction.ust_satz.wert is None
    assert extraction.ust_satz.confidence < 0.6


def test_local_parser_empty_ocr_text_returns_only_uncertain_fields():
    extraction = parse_ocr_text("  \n\t")

    assert extraction.betrag.wert is None
    assert extraction.datum.wert is None
    assert extraction.anbieter.wert is None
    assert extraction.ust_satz.wert is None
    assert extraction.kategorie_vorschlag.wert == "Sonstiges"
    assert all(
        field.confidence < 0.6
        for field in (
            extraction.betrag,
            extraction.datum,
            extraction.anbieter,
            extraction.ust_satz,
            extraction.kategorie_vorschlag,
        )
    )


def test_upload_with_confident_extraction_is_geprueft(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))

    resp = _upload(client, headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "geprueft"
    assert body["betrag"] == {"wert": "49.90", "confidence": 0.95, "unklar": False}
    assert body["kategorie_vorschlag"]["unklar"] is False


def test_low_confidence_field_is_marked_unklar_but_others_still_usable(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(anbieter=("Irgendwas", 0.2))))

    resp = _upload(client, headers)
    body = resp.json()
    assert body["status"] == "geprueft"  # betrag is confident, so the receipt overall is usable
    assert body["anbieter"]["unklar"] is True
    assert body["anbieter"]["wert"] is None  # never surface a guess below threshold


def test_no_betrag_leaves_receipt_unklar(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(betrag=(None, 0.1))))

    resp = _upload(client, headers)
    assert resp.json()["status"] == "unklar"


def test_extraction_service_unavailable_keeps_receipt_without_data_loss(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(unavailable=True))

    resp = _upload(client, headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "unklar"
    assert body["betrag"]["unklar"] is True


def test_duplicate_upload_warns_instead_of_silently_booking(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))

    first = _upload(client, headers).json()
    second = _upload(client, headers)  # identical bytes -> identical hash
    assert second.status_code == 201
    body = second.json()
    assert body["ist_duplikat"] is True
    assert body["duplikat_von"] == first["id"]

    all_belege = client.get("/belege", headers=headers).json()
    assert len(all_belege) == 1  # no second row was created


def test_duplicate_upload_with_force_creates_a_new_receipt(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))

    _upload(client, headers)
    forced = _upload(client, headers, force=True)
    assert forced.status_code == 201
    assert forced.json()["ist_duplikat"] is False

    all_belege = client.get("/belege", headers=headers).json()
    assert len(all_belege) == 2


def test_confirm_creates_ausgabe_and_marks_receipt_gebucht(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()

    resp = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={})
    assert resp.status_code == 201
    ausgabe = resp.json()
    assert ausgabe["anbieter"] == "Bahn GmbH"
    assert float(ausgabe["betrag"]) == 49.90

    updated = client.get(f"/belege/{receipt['id']}", headers=headers).json()
    assert updated["status"] == "gebucht"
    assert updated["gebucht_als"] == ausgabe["id"]


def test_receipt_shows_buchungskonto_vorschlag_and_begruendung(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(kategorie_vorschlag=("Reisekosten", 0.9), begruendung="Zugticket erkennbar.")))

    receipt = _upload(client, headers).json()
    assert receipt["buchungskonto_vorschlag"] == "6663"  # SKR03 Reisekosten
    assert receipt["begruendung"] == "Zugticket erkennbar."


def test_buchungskonto_falls_back_to_default_when_kategorie_unklar(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(kategorie_vorschlag=(None, 0.1))))

    receipt = _upload(client, headers).json()
    assert receipt["buchungskonto_vorschlag"] == "6800"  # Sonstiges/Standardkonto


def test_confirm_books_with_suggested_konto_when_not_overridden(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(kategorie_vorschlag=("Software/IT", 0.9))))
    receipt = _upload(client, headers).json()

    ausgabe = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={}).json()
    assert ausgabe["konto"] == "6835"  # SKR03 Software/IT


def test_confirm_allows_overriding_the_suggested_konto(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(kategorie_vorschlag=("Software/IT", 0.9))))
    receipt = _upload(client, headers).json()

    ausgabe = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={"konto": "6300"}).json()
    assert ausgabe["konto"] == "6300"


def test_confirm_rejects_when_unklar_field_not_overridden(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(anbieter=(None, 0.1))))
    receipt = _upload(client, headers).json()

    resp = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={})
    assert resp.status_code == 400
    assert "anbieter" in resp.json()["detail"]


def test_confirm_with_manual_override_fills_unklar_field(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(anbieter=(None, 0.1))))
    receipt = _upload(client, headers).json()

    resp = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={"anbieter": "Handeingabe GmbH"})
    assert resp.status_code == 201
    assert resp.json()["anbieter"] == "Handeingabe GmbH"



def test_original_receipt_file_is_available_only_to_own_mandant(client: TestClient):
    headers = _onboarded_mandant(client, email="owner@example.com")
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()

    own = client.get(f"/belege/{receipt['id']}/datei", headers=headers)
    assert own.status_code == 200
    assert own.content == FAKE_IMAGE
    assert own.headers["content-type"].startswith("image/png")

    foreign_headers = _onboarded_mandant(client, email="foreign@example.com")
    foreign = client.get(f"/belege/{receipt['id']}/datei", headers=foreign_headers)
    assert foreign.status_code == 404


def test_mixed_vat_requires_exact_gross_total(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()

    response = client.post(
        f"/belege/{receipt['id']}/bestaetigen",
        headers=headers,
        json={
            "betrag": "100.00",
            "datum": "2026-09-01",
            "zahlungsdatum": "2026-09-02",
            "anbieter": "Restaurant",
            "steueranteile": [
                {"ust_satz": "7", "bruttobetrag": "40.00"},
                {"ust_satz": "19", "bruttobetrag": "50.00"},
            ],
            "kategorie": "Bewirtung",
            "konto": "6644",
        },
    )
    assert response.status_code == 400
    assert "Gesamtbetrag" in response.json()["detail"]

def test_cannot_confirm_an_already_booked_receipt_twice(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()
    client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={})

    second = client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={})
    assert second.status_code == 400


def test_unsupported_file_type_rejected(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post(
        "/belege", headers=headers, files={"file": ("beleg.txt", b"hallo", "text/plain")}, data={"force": "false"},
    )
    assert resp.status_code == 400


def test_cross_mandant_receipt_access_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    _use_extractor(_FakeExtractor(_extraction()))
    kevin_receipt = _upload(client, kevin_headers).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/belege/{kevin_receipt['id']}", headers=lea_headers)
    assert resp.status_code == 404


def test_can_delete_an_unbooked_receipt(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()

    resp = client.delete(f"/belege/{receipt['id']}", headers=headers)
    assert resp.status_code == 204
    assert client.get(f"/belege/{receipt['id']}", headers=headers).status_code == 404


def test_cannot_delete_an_already_booked_receipt(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction()))
    receipt = _upload(client, headers).json()
    client.post(f"/belege/{receipt['id']}/bestaetigen", headers=headers, json={})

    resp = client.delete(f"/belege/{receipt['id']}", headers=headers)
    assert resp.status_code == 400
    assert client.get(f"/belege/{receipt['id']}", headers=headers).status_code == 200


def test_cannot_delete_another_mandants_receipt(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    _use_extractor(_FakeExtractor(_extraction()))
    kevin_receipt = _upload(client, kevin_headers).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.delete(f"/belege/{kevin_receipt['id']}", headers=lea_headers)
    assert resp.status_code == 404
    assert client.get(f"/belege/{kevin_receipt['id']}", headers=kevin_headers).status_code == 200


_UEBERWEISUNG_TEXT = """Generiert am 31.10.2025
MAX BEISPIELMANN
Musterweg 1, 12345, Musterstadt
Germany
Wertstellungsdatum 2025-10-31
Status Abgeschlossen
Art Überweisung via SEPA Instant
IBAN DE00123456780000000000 Verfügbarkeitsdatum 2025-10-31
Überweisungsdaten
Betrag €3,450
Gebühr €0
Verwendungszweck Kaution Musterwohnung
Empfängerdaten
Name Erika Beispielfrau
Kontonummer DE00987654320000000000
BIC TESTDEFFXXX
© 2025 Beispielbank UAB
Seite 1 von 1
"""


def test_local_parser_reads_integer_amount_with_currency_and_thousands_separator():
    extraction = parse_ocr_text("Überweisungsdaten\nBetrag €3,450\nGebühr €0\n")

    assert extraction.betrag.wert == "3450.00"
    assert extraction.betrag.confidence >= 0.9


@pytest.mark.parametrize(
    "line,expected",
    [("Betrag 3.450 €", "3450.00"), ("Zahlbetrag EUR 75", "75.00"), ("Gesamt 12 EUR", "12.00")],
)
def test_local_parser_reads_labelled_amounts_without_decimals(line, expected):
    assert parse_ocr_text(f"Beispiel GmbH\n{line}\n").betrag.wert == expected


def test_local_parser_does_not_mistake_a_date_for_an_amount():
    extraction = parse_ocr_text("Generiert am 31.10.2025\nStand 01.11.25\nSeite 1 von 1\n")

    assert extraction.betrag.wert is None


def test_local_parser_does_not_read_eur_prefix_of_europaeisch_as_currency():
    extraction = parse_ocr_text("Beispiel GmbH\nBeschluss 2025 Europäischen Zentralbank\n")

    assert extraction.betrag.wert is None


def test_local_parser_uses_recipient_as_vendor_for_bank_transfer_confirmations():
    extraction = parse_ocr_text(_UEBERWEISUNG_TEXT)

    assert extraction.anbieter.wert == "Erika Beispielfrau"
    assert extraction.anbieter.confidence >= 0.6
    assert extraction.betrag.wert == "3450.00"
    assert extraction.betrag.confidence >= 0.9
    assert extraction.datum.wert == "2025-10-31"


def test_local_parser_keeps_invoice_recipient_out_of_vendor_for_normal_invoices():
    extraction = parse_ocr_text(
        "Muster Software GmbH, Hauptstr. 5, 10115 Berlin\n"
        "Rechnungsempfänger\nName Max Kunde\n"
        "Gesamtbetrag 119,00 EUR\n"
    )

    assert extraction.anbieter.wert == "Muster Software GmbH"


def test_local_parser_ignores_generated_timestamp_line_as_vendor():
    extraction = parse_ocr_text("Generiert am 31.10.2025\nNordwind Handels GmbH\nGesamt 10,00 EUR\n")

    assert extraction.anbieter.wert == "Nordwind Handels GmbH"


def test_local_parser_uses_leistungsdatum_and_ignores_zahlungsziel_on_same_line():
    extraction = parse_ocr_text(
        "Musterstudio GmbH\nRechnung RE-2026-0001\n"
        "Leistungsdatum: 2026-10-08 Zahlungsziel: 2026-10-22\nGesamt 285,60 EUR\n"
    )

    assert extraction.datum.wert == "2026-10-08"
    assert extraction.datum.confidence >= 0.8


def test_local_parser_prefers_rechnungsdatum_over_leistungsdatum():
    extraction = parse_ocr_text(
        "Muster GmbH\nRechnungsdatum: 05.03.2026\nLeistungsdatum: 01.03.2026\nFälligkeitsdatum: 19.03.2026\n"
    )

    assert extraction.datum.wert == "2026-03-05"
    assert extraction.datum.confidence >= 0.9


def test_local_parser_never_takes_a_due_date_as_receipt_date():
    only_due = parse_ocr_text("Muster GmbH\nFällig am 19.03.2026\nZahlungsziel: 19.03.2026\n")
    assert only_due.datum.wert is None

    with_receipt_date = parse_ocr_text("Muster GmbH\n12.03.2026\nFällig am 26.03.2026\n")
    assert with_receipt_date.datum.wert == "2026-03-12"


@pytest.mark.parametrize(
    "text,kategorie",
    [
        ("Büromiete April 2026", "Miete"),
        ("Buchhaltungssoftware Jahreslizenz", "Software/IT"),
        ("Übernachtung Hotel Beispiel 2 Nächte", "Reisekosten"),
        ("Kraftstoff Diesel 45,20 l", "Reisekosten"),
        ("IONOS Webhosting Paket", "Software/IT"),
        ("Visitenkarten Druck 500 Stück", "Marketing"),
        ("Internetanschluss Telefonie Grundgebühr", "Telekommunikation"),
        ("Büromaterial Druckerpapier Ordner", "Buerobedarf"),
    ],
)
def test_local_parser_recognises_common_category_words_including_compounds(text, kategorie):
    extraction = parse_ocr_text(f"Beispiel GmbH\n{text}\nGesamt 10,00 EUR\n")

    assert extraction.kategorie_vorschlag.wert == kategorie
    assert extraction.kategorie_vorschlag.confidence >= 0.6


def test_local_parser_keeps_unrelated_words_out_of_categories():
    extraction = parse_ocr_text("Beispiel GmbH\nWartung Oktober\nGesamt 285,60 EUR\n")

    assert extraction.kategorie_vorschlag.confidence < 0.6
