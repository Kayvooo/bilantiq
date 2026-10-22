from datetime import date

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant


def _paid_invoice(client: TestClient, headers: dict, *, netto: str, ust_satz: str, bezahlt_am: str) -> dict:
    kontakt_id = _kontakt(client, headers)
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": bezahlt_am, "faelligkeitsdatum": bezahlt_am, "waehrung": "EUR",
            "positionen": [{"beschreibung": "Leistung", "menge": "1", "einzelpreis": netto, "ust_satz": ust_satz}],
        },
    ).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
    client.post(f"/invoices/{final['id']}/bezahlt", headers=headers, json={"bezahlt_am": bezahlt_am})
    return final


def _booked_ausgabe(client: TestClient, headers: dict, *, brutto: str, ust_satz: str, datum: str) -> dict:
    upload = client.post(
        "/belege", headers=headers, files={"file": ("beleg.png", b"\x89PNG\r\n\x1a\n" + brutto.encode() + datum.encode(), "image/png")},
        data={"force": "false"},
    ).json()
    return client.post(
        f"/belege/{upload['id']}/bestaetigen", headers=headers,
        json={
            "betrag": brutto, "datum": datum, "anbieter": "Lieferant", "ust_satz": ust_satz,
            "kategorie": "Sonstiges", "konto": "6800",
        },
    ).json()


def test_ustva_defaults_to_current_month(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/ustva", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["jahr"] == date.today().year
    assert body["zeitraum_typ"] == "monat"
    assert body["periode"] == date.today().month


def test_ustva_sums_19_and_7_percent_separately(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", ust_satz="19.00", bezahlt_am=f"{this_year}-06-10")
    _paid_invoice(client, headers, netto="200.00", ust_satz="7.00", bezahlt_am=f"{this_year}-06-15")

    body = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=headers).json()
    assert float(body["umsatz_19_netto"]) == 1000.00
    assert float(body["umsatzsteuer_19"]) == 190.00
    assert float(body["umsatz_7_netto"]) == 200.00
    assert float(body["umsatzsteuer_7"]) == 14.00
    assert float(body["umsatzsteuer_gesamt"]) == 204.00
    assert body["anzahl_rechnungen"] == 2


def test_ustva_computes_vorsteuer_and_zahllast(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", ust_satz="19.00", bezahlt_am=f"{this_year}-06-10")
    _booked_ausgabe(client, headers, brutto="238.00", ust_satz="19.00", datum=f"{this_year}-06-12")  # 38.00 Vorsteuer

    body = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=headers).json()
    assert abs(float(body["vorsteuer_gesamt"]) - 38.00) < 0.01
    assert abs(float(body["zahllast"]) - (190.00 - 38.00)) < 0.01
    assert body["anzahl_ausgaben"] == 1



def test_ustva_sums_mixed_vat_receipt(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    upload = client.post(
        "/belege",
        headers=headers,
        files={"file": ("mixed.png", b"\x89PNG\r\n\x1a\n" + b"mixed-vat", "image/png")},
        data={"force": "false"},
    ).json()
    response = client.post(
        f"/belege/{upload['id']}/bestaetigen",
        headers=headers,
        json={
            "betrag": "226.00",
            "datum": f"{this_year}-06-12",
            "zahlungsdatum": f"{this_year}-07-01",
            "anbieter": "Restaurant",
            "steueranteile": [
                {"ust_satz": "7.00", "bruttobetrag": "107.00"},
                {"ust_satz": "19.00", "bruttobetrag": "119.00"},
            ],
            "kategorie": "Bewirtung",
            "konto": "6644",
        },
    )
    assert response.status_code == 201
    assert response.json()["ust_satz"] is None
    assert len(response.json()["steueranteile"]) == 2

    june = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=headers).json()
    july = client.get(f"/berichte/ustva?jahr={this_year}&periode=7", headers=headers).json()
    assert abs(float(june["vorsteuer_gesamt"]) - 26.00) < 0.01
    assert float(july["vorsteuer_gesamt"]) == 0.0

def test_ustva_zahllast_negative_when_vorsteuer_exceeds_umsatzsteuer(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _booked_ausgabe(client, headers, brutto="1190.00", ust_satz="19.00", datum=f"{this_year}-06-01")  # 190 Vorsteuer, keine Einnahmen

    body = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=headers).json()
    assert float(body["zahllast"]) < 0


def test_ustva_quartal_mode_covers_three_months(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="100.00", ust_satz="19.00", bezahlt_am=f"{this_year}-01-05")
    _paid_invoice(client, headers, netto="100.00", ust_satz="19.00", bezahlt_am=f"{this_year}-03-25")

    body = client.get(f"/berichte/ustva?jahr={this_year}&zeitraum_typ=quartal&periode=1", headers=headers).json()
    assert body["zeitraum_von"] == f"{this_year}-01-01"
    assert body["zeitraum_bis"] == f"{this_year}-03-31"
    assert body["anzahl_rechnungen"] == 2
    assert float(body["umsatz_19_netto"]) == 200.00


def test_ustva_rejects_invalid_periode(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/ustva?zeitraum_typ=monat&periode=13", headers=headers)
    assert resp.status_code == 400


def test_ustva_excludes_unpaid_invoices(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    this_year = date.today().year
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": f"{this_year}-06-01", "faelligkeitsdatum": f"{this_year}-06-15",
            "waehrung": "EUR", "positionen": [{"beschreibung": "Unbezahlt", "menge": "1", "einzelpreis": "500.00", "ust_satz": "19.00"}],
        },
    ).json()
    client.post(f"/invoices/{draft['id']}/finalize", headers=headers)

    body = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=headers).json()
    assert body["anzahl_rechnungen"] == 0
    assert float(body["umsatzsteuer_gesamt"]) == 0.0


def test_ustva_isolated_per_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="5000.00", ust_satz="19.00", bezahlt_am=f"{this_year}-06-10")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    body = client.get(f"/berichte/ustva?jahr={this_year}&periode=6", headers=lea_headers).json()
    assert body["anzahl_rechnungen"] == 0
