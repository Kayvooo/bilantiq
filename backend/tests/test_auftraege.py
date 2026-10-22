from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _angenommenes_angebot(client: TestClient, headers: dict, kontakt_id: str) -> str:
    draft = client.post(
        "/angebote",
        headers=headers,
        json={
            "kontakt_id": kontakt_id,
            "gueltig_bis": (date.today() + timedelta(days=14)).isoformat(),
            "waehrung": "EUR",
            "positionen": [
                {"beschreibung": "Konzeption", "menge": "2", "einzelpreis": "500.00", "ust_satz": "19.00"},
            ],
        },
    ).json()
    client.post(f"/angebote/{draft['id']}/versenden", headers=headers)
    client.post(f"/angebote/{draft['id']}/annehmen", headers=headers)
    return draft["id"]


def test_create_auftragsbestaetigung_copies_positions_and_totals(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)

    resp = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["quote_id"] == quote_id
    assert float(body["brutto_gesamt"]) == 1190.00
    assert len(body["positionen"]) == 1
    year = date.today().year
    assert body["nummer"] == f"AB-{year}-0001"


def test_cannot_confirm_quote_twice(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)

    client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id})
    second = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id})
    assert second.status_code == 400


def test_cannot_confirm_quote_not_yet_accepted(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post(
        "/angebote",
        headers=headers,
        json={
            "kontakt_id": kontakt_id,
            "gueltig_bis": (date.today() + timedelta(days=14)).isoformat(),
            "waehrung": "EUR",
            "positionen": [{"beschreibung": "Konzeption", "menge": "1", "einzelpreis": "100.00", "ust_satz": "19.00"}],
        },
    ).json()

    resp = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": draft["id"]})
    assert resp.status_code == 400


def test_auftragsbestaetigung_pdf_downloads(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)
    ab = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id}).json()

    resp = client.get(f"/auftragsbestaetigungen/{ab['id']}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_create_lieferschein_without_prices(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)
    ab = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id}).json()

    resp = client.post(
        "/lieferscheine",
        headers=headers,
        json={
            "auftragsbestaetigung_id": ab["id"],
            "lieferdatum": date.today().isoformat(),
            "positionen": [{"beschreibung": "Konzeption", "menge": "2"}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "einzelpreis" not in body["positionen"][0]
    year = date.today().year
    assert body["nummer"] == f"LS-{year}-0001"


def test_multiple_lieferscheine_per_auftragsbestaetigung_allowed(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)
    ab = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id}).json()

    payload = {
        "auftragsbestaetigung_id": ab["id"],
        "lieferdatum": date.today().isoformat(),
        "positionen": [{"beschreibung": "Teillieferung", "menge": "1"}],
    }
    first = client.post("/lieferscheine", headers=headers, json=payload)
    second = client.post("/lieferscheine", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["nummer"] != second.json()["nummer"]

    listing = client.get("/lieferscheine", headers=headers)
    assert len(listing.json()) == 2


def test_lieferschein_pdf_downloads(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote_id = _angenommenes_angebot(client, headers, kontakt_id)
    ab = client.post("/auftragsbestaetigungen", headers=headers, json={"quote_id": quote_id}).json()
    ls = client.post(
        "/lieferscheine",
        headers=headers,
        json={
            "auftragsbestaetigung_id": ab["id"],
            "lieferdatum": date.today().isoformat(),
            "positionen": [{"beschreibung": "Konzeption", "menge": "2"}],
        },
    ).json()

    resp = client.get(f"/lieferscheine/{ls['id']}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
