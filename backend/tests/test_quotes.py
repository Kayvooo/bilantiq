from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant


def _quote_payload(kontakt_id: str, *, gueltig_bis: str | None = None) -> dict:
    return {
        "kontakt_id": kontakt_id,
        "gueltig_bis": gueltig_bis or (date.today() + timedelta(days=14)).isoformat(),
        "waehrung": "EUR",
        "positionen": [
            {"beschreibung": "Konzeption", "menge": "1", "einzelpreis": "800.00", "ust_satz": "19.00"},
        ],
    }


def test_create_quote_computes_totals(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    resp = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "entwurf"
    assert body["nummer"] is None
    assert float(body["brutto_gesamt"]) == 952.00


def test_send_assigns_gapless_numbers_independent_of_invoices(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    numbers = []
    for _ in range(2):
        draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
        sent = client.post(f"/angebote/{draft['id']}/versenden", headers=headers).json()
        numbers.append(sent["nummer"])

    year = date.today().year
    assert numbers == [f"AN-{year}-0001", f"AN-{year}-0002"]


def test_cannot_send_twice(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)

    second = client.post(f"/angebote/{draft['id']}/versenden", headers=headers)
    assert second.status_code == 400


def test_accept_then_convert_to_invoice_copies_positions(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)
    client.post(f"/angebote/{draft['id']}/annehmen", headers=headers)

    convert = client.post(f"/angebote/{draft['id']}/in-rechnung-umwandeln", headers=headers)
    assert convert.status_code == 201
    invoice_id = convert.json()["invoice_id"]

    invoice = client.get(f"/invoices/{invoice_id}", headers=headers).json()
    assert invoice["status"] == "entwurf"
    assert float(invoice["brutto_gesamt"]) == 952.00
    assert invoice["positionen"][0]["beschreibung"] == "Konzeption"

    quote_after = client.get(f"/angebote/{draft['id']}", headers=headers).json()
    assert quote_after["umgewandelt_in_invoice_id"] == invoice_id
    # The quote's own figures are untouched by the conversion.
    assert float(quote_after["brutto_gesamt"]) == 952.00


def test_cannot_convert_before_accepted(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)

    resp = client.post(f"/angebote/{draft['id']}/in-rechnung-umwandeln", headers=headers)
    assert resp.status_code == 400


def test_cannot_convert_twice(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)
    client.post(f"/angebote/{draft['id']}/annehmen", headers=headers)
    client.post(f"/angebote/{draft['id']}/in-rechnung-umwandeln", headers=headers)

    second = client.post(f"/angebote/{draft['id']}/in-rechnung-umwandeln", headers=headers)
    assert second.status_code == 400


def test_reject_quote(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)

    resp = client.post(f"/angebote/{draft['id']}/ablehnen", headers=headers)
    assert resp.json()["status"] == "abgelehnt"


def test_expired_quote_shows_abgelaufen_and_blocks_accept(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id, gueltig_bis=yesterday)).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)

    fetched = client.get(f"/angebote/{draft['id']}", headers=headers).json()
    assert fetched["status"] == "versendet"  # stored status never mutated automatically
    assert fetched["anzeige_status"] == "abgelaufen"  # but display reflects reality

    resp = client.post(f"/angebote/{draft['id']}/annehmen", headers=headers)
    assert resp.status_code == 400


def test_pdf_endpoint_returns_pdf(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()

    resp = client.get(f"/angebote/{draft['id']}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_cross_mandant_quote_access_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_kontakt = _kontakt(client, kevin_headers)
    kevin_quote = client.post("/angebote", headers=kevin_headers, json=_quote_payload(kevin_kontakt)).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/angebote/{kevin_quote['id']}", headers=lea_headers)
    assert resp.status_code == 404
