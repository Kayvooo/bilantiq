from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _overdue_invoice_payload(kontakt_id: str) -> dict:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    return {
        "kontakt_id": kontakt_id,
        "leistungsdatum": (date.today() - timedelta(days=20)).isoformat(),
        "faelligkeitsdatum": yesterday,
        "waehrung": "EUR",
        "positionen": [{"beschreibung": "Beratung", "menge": "1", "einzelpreis": "500.00", "ust_satz": "19.00"}],
    }


def _finalized_overdue_invoice(client: TestClient, headers: dict) -> dict:
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_overdue_invoice_payload(kontakt_id)).json()
    return client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()


def test_invoice_past_due_shows_ueberfaellig(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)
    assert invoice["anzeige_status"] == "ueberfaellig"


def test_cannot_mahnung_before_ueberfaellig(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _overdue_invoice_payload(kontakt_id)
    payload["faelligkeitsdatum"] = (date.today() + timedelta(days=14)).isoformat()  # not due yet
    draft = client.post("/invoices", headers=headers, json=payload).json()
    invoice = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()

    resp = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers)
    assert resp.status_code == 400


def test_full_mahnstufen_progression(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)

    erinnerung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()
    assert erinnerung["stufe"] == 1
    assert erinnerung["stufe_bezeichnung"] == "Zahlungserinnerung"
    assert float(erinnerung["mahngebuehr"]) == 0.0

    erste_mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()
    assert erste_mahnung["stufe"] == 2
    assert float(erste_mahnung["mahngebuehr"]) > 0

    zweite_mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()
    assert zweite_mahnung["stufe"] == 3

    # Max reached — a fourth stage is refused rather than silently invented.
    resp = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers)
    assert resp.status_code == 400

    liste = client.get(f"/invoices/{invoice['id']}/mahnungen", headers=headers).json()
    assert [m["stufe"] for m in liste] == [1, 2, 3]


def test_cannot_mahnung_a_paid_invoice(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)
    client.post(f"/invoices/{invoice['id']}/bezahlt", headers=headers, json={})

    resp = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers)
    assert resp.status_code == 400


def test_mark_paid_updates_status_and_blocks_double_payment(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)

    resp = client.post(f"/invoices/{invoice['id']}/bezahlt", headers=headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["anzeige_status"] == "bezahlt"
    assert body["bezahlt_am"] == date.today().isoformat()

    second = client.post(f"/invoices/{invoice['id']}/bezahlt", headers=headers, json={})
    assert second.status_code == 400


def test_mahnung_pdf_endpoint(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)
    mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()

    resp = client.get(f"/mahnungen/{mahnung['id']}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_uebersicht_listet_mahnungen_ueber_alle_rechnungen(client: TestClient):
    headers = _onboarded_mandant(client)
    erste_rechnung = _finalized_overdue_invoice(client, headers)
    zweite_rechnung = _finalized_overdue_invoice(client, headers)
    client.post(f"/invoices/{erste_rechnung['id']}/mahnung", headers=headers)
    client.post(f"/invoices/{erste_rechnung['id']}/mahnung", headers=headers)
    client.post(f"/invoices/{zweite_rechnung['id']}/mahnung", headers=headers)

    resp = client.get("/mahnungen", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert {m["invoice_id"] for m in body} == {erste_rechnung["id"], zweite_rechnung["id"]}
    assert all(m["kontakt_name"] == "Beispiel Kunde GmbH" for m in body)


def test_uebersicht_ist_leer_ohne_mahnungen(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/mahnungen", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_uebersicht_zeigt_nur_eigene_mandant_mahnungen(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_invoice = _finalized_overdue_invoice(client, kevin_headers)
    client.post(f"/invoices/{kevin_invoice['id']}/mahnung", headers=kevin_headers)

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get("/mahnungen", headers=lea_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_cross_mandant_mahnung_access_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_invoice = _finalized_overdue_invoice(client, kevin_headers)
    kevin_mahnung = client.post(f"/invoices/{kevin_invoice['id']}/mahnung", headers=kevin_headers).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/mahnungen/{kevin_mahnung['id']}/pdf", headers=lea_headers)
    assert resp.status_code == 404
