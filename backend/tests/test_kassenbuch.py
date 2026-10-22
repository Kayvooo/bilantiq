from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant


def test_leeres_kassenbuch_hat_saldo_null(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/kassenbuch", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["eintraege"] == []
    assert float(body["aktueller_kassenbestand"]) == 0.0


def test_einnahme_und_ausgabe_ergeben_richtigen_saldo(client: TestClient):
    headers = _onboarded_mandant(client)
    client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-01", "typ": "einnahme", "betrag": "100.00", "beschreibung": "Bartrinkgeld"})
    client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-02", "typ": "ausgabe", "betrag": "30.00", "beschreibung": "Buerobedarf bar bezahlt"})

    body = client.get("/kassenbuch", headers=headers).json()
    assert float(body["aktueller_kassenbestand"]) == 70.0
    assert len(body["eintraege"]) == 2
    # neuester zuerst
    assert body["eintraege"][0]["beschreibung"] == "Buerobedarf bar bezahlt"
    assert float(body["eintraege"][0]["saldo_nach_buchung"]) == 70.0
    assert float(body["eintraege"][1]["saldo_nach_buchung"]) == 100.0


def test_saldo_kann_negativ_werden_ohne_ablehnung(client: TestClient):
    """Bewusst keine Validierung gegen negativen Kassenbestand -- das Kassenbuch
    bildet ab was war, es korrigiert keine Fehlbuchungen der Vergangenheit."""
    headers = _onboarded_mandant(client)
    resp = client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-01", "typ": "ausgabe", "betrag": "50.00", "beschreibung": "Vorschuss"})
    assert resp.status_code == 201
    assert float(resp.json()["saldo_nach_buchung"]) == -50.0


def test_ungueltiger_typ_wird_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-01", "typ": "transfer", "betrag": "10.00", "beschreibung": "x"})
    assert resp.status_code == 422


def test_kassenbuch_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    client.post("/kassenbuch", headers=kevin_headers, json={"datum": "2026-09-01", "typ": "einnahme", "betrag": "100.00", "beschreibung": "x"})

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    body = client.get("/kassenbuch", headers=lea_headers).json()
    assert body["eintraege"] == []
    assert float(body["aktueller_kassenbestand"]) == 0.0
