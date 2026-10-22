from datetime import date

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.payroll.models import Mitarbeiter
from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _employee_payload(**overrides) -> dict:
    payload = {
        "personalnummer": "P-001",
        "vorname": "Mara",
        "nachname": "Muster",
        "eintrittsdatum": "2026-01-15",
        "austrittsdatum": None,
        "monatsbrutto": "3200.00",
    }
    payload.update(overrides)
    return payload


def _create_employee(client: TestClient, headers: dict, **overrides) -> dict:
    response = client.post("/lohn/mitarbeitende", headers=headers, json=_employee_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_employee_names_are_encrypted_at_rest_and_returned_to_owner(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)

    assert employee["vorname"] == "Mara"
    assert employee["nachname"] == "Muster"
    with SessionLocal() as db:
        stored = db.get(Mitarbeiter, employee["id"])
        assert stored is not None
        assert stored.vorname_encrypted != "Mara"
        assert stored.nachname_encrypted != "Muster"


def test_personal_number_is_unique_per_tenant(client: TestClient):
    headers = _onboarded_mandant(client)
    _create_employee(client, headers)
    duplicate = client.post("/lohn/mitarbeitende", headers=headers, json=_employee_payload())
    assert duplicate.status_code == 409

    other_headers = _onboarded_mandant(client, email="other-payroll@example.com")
    assert client.post("/lohn/mitarbeitende", headers=other_headers, json=_employee_payload()).status_code == 201


def test_monthly_draft_uses_salary_and_calculates_only_preparation_totals(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    response = client.post(
        "/lohn/monatsentwuerfe",
        headers=headers,
        json={
            "mitarbeiter_id": employee["id"],
            "jahr": 2026,
            "monat": 2,
            "steuerpflichtige_zuschlaege": "125.55",
            "steuerfreie_erstattungen": "44.40",
            "sonstige_abzuege": "20.00",
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["grundbrutto"] == "3200.00"
    assert draft["steuerpflichtige_zuschlaege"] == "125.55"
    assert draft["gesamtbrutto"] == "3325.55"
    assert draft["zwischenbetrag_vor_abgaben"] == "3349.95"
    assert draft["status"] == "vorbereitung"
    assert draft["verbindlicher_abschluss_verfuegbar"] is False
    assert "keine rechtsverbindliche" in draft["hinweis"].lower()


def test_draft_rejects_duplicate_and_month_outside_employment(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers, austrittsdatum="2026-03-31")
    payload = {"mitarbeiter_id": employee["id"], "jahr": 2026, "monat": 2}
    assert client.post("/lohn/monatsentwuerfe", headers=headers, json=payload).status_code == 201
    assert client.post("/lohn/monatsentwuerfe", headers=headers, json=payload).status_code == 409

    outside = client.post(
        "/lohn/monatsentwuerfe",
        headers=headers,
        json={"mitarbeiter_id": employee["id"], "jahr": 2026, "monat": 4},
    )
    assert outside.status_code == 400


def test_deactivated_employee_is_retained_but_cannot_receive_new_drafts(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    deactivated = client.post(f"/lohn/mitarbeitende/{employee['id']}/deaktivieren", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["aktiv"] is False
    listed = client.get("/lohn/mitarbeitende", headers=headers).json()
    assert listed[0]["id"] == employee["id"]
    assert listed[0]["aktiv"] is False
    blocked = client.post(
        "/lohn/monatsentwuerfe",
        headers=headers,
        json={"mitarbeiter_id": employee["id"], "jahr": date.today().year, "monat": date.today().month},
    )
    assert blocked.status_code == 400


def test_cross_tenant_access_is_hidden(client: TestClient):
    owner_headers = _onboarded_mandant(client)
    employee = _create_employee(client, owner_headers)
    other_headers = _onboarded_mandant(client, email="other-tenant@example.com")
    response = client.post(f"/lohn/mitarbeitende/{employee['id']}/deaktivieren", headers=other_headers)
    assert response.status_code == 404
    assert client.get("/lohn/mitarbeitende", headers=other_headers).json() == []


def test_month_export_is_machine_readable_and_clearly_not_an_official_payroll(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    client.post(
        "/lohn/monatsentwuerfe",
        headers=headers,
        json={"mitarbeiter_id": employee["id"], "jahr": 2026, "monat": 2},
    )
    response = client.get("/lohn/monate/2026/2/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Lohnvorbereitung-2026-02.csv" in response.headers["content-disposition"]
    decoded = response.content.decode("utf-8-sig")
    assert "VORBEREITUNG;P-001;Mara Muster" in decoded
    assert "Keine rechtsverbindliche Lohnabrechnung" in decoded


def _create_draft(client: TestClient, headers: dict, employee_id: str, **overrides) -> dict:
    payload = {"mitarbeiter_id": employee_id, "jahr": 2026, "monat": 2}
    payload.update(overrides)
    response = client.post("/lohn/monatsentwuerfe", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_mitarbeiter_kann_bearbeitet_werden(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    response = client.patch(
        f"/lohn/mitarbeitende/{employee['id']}",
        headers=headers,
        json={"nachname": "Musterfrau", "monatsbrutto": "3500.00"},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["vorname"] == "Mara"
    assert updated["nachname"] == "Musterfrau"
    assert updated["monatsbrutto"] == "3500.00"
    assert updated["eintrittsdatum"] == "2026-01-15"


def test_mitarbeiter_bearbeiten_validiert_datumsreihenfolge(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    response = client.patch(
        f"/lohn/mitarbeitende/{employee['id']}",
        headers=headers,
        json={"austrittsdatum": "2020-01-01"},
    )
    assert response.status_code == 422


def test_mitarbeiter_kann_reaktiviert_werden(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    client.post(f"/lohn/mitarbeitende/{employee['id']}/deaktivieren", headers=headers)

    doppelt = client.post(f"/lohn/mitarbeitende/{employee['id']}/reaktivieren", headers=headers)
    assert doppelt.status_code == 200
    assert doppelt.json()["aktiv"] is True

    erneut = client.post(f"/lohn/mitarbeitende/{employee['id']}/reaktivieren", headers=headers)
    assert erneut.status_code == 400


def test_monatsentwurf_kann_korrigiert_werden_solange_in_vorbereitung(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    draft = _create_draft(client, headers, employee["id"], steuerpflichtige_zuschlaege="100.00")

    response = client.patch(
        f"/lohn/monatsentwuerfe/{draft['id']}",
        headers=headers,
        json={"steuerpflichtige_zuschlaege": "200.00", "sonstige_abzuege": "50.00"},
    )
    assert response.status_code == 200, response.text
    corrected = response.json()
    assert corrected["steuerpflichtige_zuschlaege"] == "200.00"
    assert corrected["gesamtbrutto"] == "3400.00"
    assert corrected["zwischenbetrag_vor_abgaben"] == "3350.00"


def test_monatsentwurf_korrektur_darf_abzuege_nicht_ueber_auszahlung_setzen(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    draft = _create_draft(client, headers, employee["id"])
    response = client.patch(
        f"/lohn/monatsentwuerfe/{draft['id']}",
        headers=headers,
        json={"sonstige_abzuege": "999999.00"},
    )
    assert response.status_code == 422


def test_monatsentwurf_abschliessen_und_reaktivieren(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    draft = _create_draft(client, headers, employee["id"])

    abgeschlossen = client.post(f"/lohn/monatsentwuerfe/{draft['id']}/abschliessen", headers=headers)
    assert abgeschlossen.status_code == 200, abgeschlossen.text
    body = abgeschlossen.json()
    assert body["status"] == "abgeschlossen"
    assert body["abgeschlossen_am"] is not None
    assert body["verbindlicher_abschluss_verfuegbar"] is False

    doppelt = client.post(f"/lohn/monatsentwuerfe/{draft['id']}/abschliessen", headers=headers)
    assert doppelt.status_code == 400

    gesperrt = client.patch(f"/lohn/monatsentwuerfe/{draft['id']}", headers=headers, json={"sonstige_abzuege": "10.00"})
    assert gesperrt.status_code == 400

    reaktiviert = client.post(f"/lohn/monatsentwuerfe/{draft['id']}/reaktivieren", headers=headers)
    assert reaktiviert.status_code == 200, reaktiviert.text
    assert reaktiviert.json()["status"] == "vorbereitung"
    assert reaktiviert.json()["abgeschlossen_am"] is None

    erneut_reaktivieren = client.post(f"/lohn/monatsentwuerfe/{draft['id']}/reaktivieren", headers=headers)
    assert erneut_reaktivieren.status_code == 400

    wieder_editierbar = client.patch(f"/lohn/monatsentwuerfe/{draft['id']}", headers=headers, json={"sonstige_abzuege": "10.00"})
    assert wieder_editierbar.status_code == 200


def test_lohnzettel_pdf_wird_erzeugt(client: TestClient):
    headers = _onboarded_mandant(client)
    employee = _create_employee(client, headers)
    draft = _create_draft(client, headers, employee["id"])

    response = client.get(f"/lohn/monatsentwuerfe/{draft['id']}/lohnzettel", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert f"Lohnzettel-P-001-2026-02.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_lohn_korrektur_endpunkte_sind_mandantengetrennt(client: TestClient):
    owner_headers = _onboarded_mandant(client)
    employee = _create_employee(client, owner_headers)
    draft = _create_draft(client, owner_headers, employee["id"])
    other_headers = _onboarded_mandant(client, email="other-payroll-2@example.com")

    assert client.patch(f"/lohn/mitarbeitende/{employee['id']}", headers=other_headers, json={"nachname": "X"}).status_code == 404
    assert client.post(f"/lohn/mitarbeitende/{employee['id']}/reaktivieren", headers=other_headers).status_code == 404
    assert client.patch(f"/lohn/monatsentwuerfe/{draft['id']}", headers=other_headers, json={"sonstige_abzuege": "1.00"}).status_code == 404
    assert client.post(f"/lohn/monatsentwuerfe/{draft['id']}/abschliessen", headers=other_headers).status_code == 404
    assert client.get(f"/lohn/monatsentwuerfe/{draft['id']}/lohnzettel", headers=other_headers).status_code == 404
