from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _invoice_due_in(client: TestClient, headers: dict, *, tage: int, brutto_netto: str = "100.00") -> dict:
    kontakt_id = _kontakt(client, headers)
    heute = date.today()
    faellig = heute + timedelta(days=tage)
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": heute.isoformat(), "faelligkeitsdatum": faellig.isoformat(),
            "waehrung": "EUR", "positionen": [{"beschreibung": "Leistung", "menge": "1", "einzelpreis": brutto_netto, "ust_satz": "0.00"}],
        },
    ).json()
    return client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()


def _booked_ausgabe(client: TestClient, headers: dict, *, brutto: str, tage_zurueck: int) -> dict:
    datum = (date.today() - timedelta(days=tage_zurueck)).isoformat()
    upload = client.post(
        "/belege", headers=headers, files={"file": ("beleg.png", b"\x89PNG\r\n\x1a\n" + brutto.encode() + str(tage_zurueck).encode(), "image/png")},
        data={"force": "false"},
    ).json()
    return client.post(
        f"/belege/{upload['id']}/bestaetigen", headers=headers,
        json={"betrag": brutto, "datum": datum, "anbieter": "Lieferant", "ust_satz": "0.00", "kategorie": "Sonstiges"},
    ).json()


def test_default_horizon_is_eight_weeks(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/cashflow", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["wochen"]) == 8


def test_horizon_is_clamped_to_sane_bounds(client: TestClient):
    headers = _onboarded_mandant(client)
    assert len(client.get("/berichte/cashflow?wochen=0", headers=headers).json()["wochen"]) == 1
    assert len(client.get("/berichte/cashflow?wochen=999", headers=headers).json()["wochen"]) == 26


def test_open_invoice_bucketed_into_correct_week(client: TestClient):
    headers = _onboarded_mandant(client)
    _invoice_due_in(client, headers, tage=10, brutto_netto="500.00")

    body = client.get("/berichte/cashflow", headers=headers).json()
    treffer = [w for w in body["wochen"] if w["anzahl_faellige_rechnungen"] > 0]
    assert len(treffer) == 1
    assert float(treffer[0]["erwarteter_zufluss"]) == 500.00
    assert treffer[0]["anzahl_faellige_rechnungen"] == 1


def test_paid_invoice_excluded_from_forecast(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _invoice_due_in(client, headers, tage=5, brutto_netto="200.00")
    client.post(f"/invoices/{invoice['id']}/bezahlt", headers=headers, json={})

    body = client.get("/berichte/cashflow", headers=headers).json()
    assert all(w["anzahl_faellige_rechnungen"] == 0 for w in body["wochen"])


def test_overdue_invoice_excluded_from_weeks_but_counted_separately(client: TestClient):
    headers = _onboarded_mandant(client)
    _invoice_due_in(client, headers, tage=-5, brutto_netto="150.00")

    body = client.get("/berichte/cashflow", headers=headers).json()
    assert all(w["anzahl_faellige_rechnungen"] == 0 for w in body["wochen"])
    assert body["ueberfaellige_rechnungen_anzahl"] == 1
    assert float(body["ueberfaellige_rechnungen_betrag"]) == 150.00


def test_average_weekly_expense_from_history(client: TestClient):
    headers = _onboarded_mandant(client)
    _booked_ausgabe(client, headers, brutto="90.00", tage_zurueck=10)

    body = client.get("/berichte/cashflow", headers=headers).json()
    # 90 EUR over 90 days history / (90/7) weeks = 7.00 EUR/week
    assert abs(float(body["durchschnittliche_wochenausgabe"]) - 7.00) < 0.01
    assert all(float(w["geschaetzter_abfluss"]) == float(body["durchschnittliche_wochenausgabe"]) for w in body["wochen"])


def test_warnung_set_when_cumulative_balance_goes_negative(client: TestClient):
    headers = _onboarded_mandant(client)
    _booked_ausgabe(client, headers, brutto="700.00", tage_zurueck=7)  # ~54 EUR/week estimated outflow, no inflow

    body = client.get("/berichte/cashflow", headers=headers).json()
    assert body["warnung"] is not None
    assert float(body["wochen"][-1]["kumulierter_saldo"]) < 0


def test_no_warnung_when_inflows_cover_outflows(client: TestClient):
    headers = _onboarded_mandant(client)
    _invoice_due_in(client, headers, tage=3, brutto_netto="10000.00")

    body = client.get("/berichte/cashflow", headers=headers).json()
    assert body["warnung"] is None


def test_cashflow_is_isolated_per_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    _invoice_due_in(client, kevin_headers, tage=3, brutto_netto="9999.00")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    body = client.get("/berichte/cashflow", headers=lea_headers).json()
    assert all(w["erwarteter_zufluss"] == "0" or float(w["erwarteter_zufluss"]) == 0.0 for w in body["wochen"])
