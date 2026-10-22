import json

from fastapi.testclient import TestClient

from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant


def _export(client: TestClient, headers: dict) -> tuple[int, dict]:
    resp = client.get("/auth/datenexport", headers=headers)
    if resp.status_code != 200:
        return resp.status_code, {}
    return resp.status_code, json.loads(resp.content)


def test_datenexport_enthaelt_stammdaten_und_entschluesselte_email(client: TestClient):
    headers = _onboarded_mandant(client, email="export-owner@example.com")
    status, export = _export(client, headers)

    assert status == 200
    assert export["mandant"]["firmenname"] == "Kevin GmbH"
    # E-Mail liegt verschluesselt in der DB, muss im Export entschluesselt auftauchen.
    emails = [n["email"] for n in export["nutzer"]]
    assert "export-owner@example.com" in emails


def test_datenexport_enthaelt_kontakte_und_rechnungen_mit_positionen(client: TestClient):
    headers = _onboarded_mandant(client, email="export-daten@example.com")
    kontakt_id = _kontakt(client, headers)
    client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id))

    _, export = _export(client, headers)

    assert any(k["id"] == kontakt_id for k in export["kontakte"])
    assert len(export["rechnungen"]) == 1
    rechnung = export["rechnungen"][0]
    assert rechnung["kontakt_id"] == kontakt_id
    assert len(rechnung["positionen"]) >= 1


def test_datenexport_enthaelt_kein_sicherheitsmaterial(client: TestClient):
    headers = _onboarded_mandant(client, email="export-secret@example.com")
    resp = client.get("/auth/datenexport", headers=headers)
    roh = resp.content.decode("utf-8")

    assert "passwort_hash" not in roh
    assert "email_lookup_hash" not in roh
    assert "mfa_secret" not in roh


def test_datenexport_ist_mandantengetrennt(client: TestClient):
    kevin = _onboarded_mandant(client, email="export-kevin@example.com")
    lea = _onboarded_mandant(client, email="export-lea@example.com")
    lea_kontakt = _kontakt(client, lea)

    _, kevin_export = _export(client, kevin)

    assert kevin_export["kontakte"] == []
    assert all(k["id"] != lea_kontakt for k in kevin_export["kontakte"])


def test_datenexport_nur_fuer_owner(client: TestClient):
    headers = _onboarded_mandant(client, email="export-rolle@example.com")

    # Eigene Mitgliedschaft auf "mitglied" herabstufen -> require_owner muss ablehnen.
    from app.auth.models import Mitgliedschaft
    from app.db import SessionLocal

    mandant_id = client.get("/auth/me", headers=headers).json()["mandant_id"]
    with SessionLocal() as db:
        mitgliedschaft = db.query(Mitgliedschaft).filter(Mitgliedschaft.mandant_id == mandant_id).first()
        mitgliedschaft.rolle = "mitglied"
        db.commit()

    resp = client.get("/auth/datenexport", headers=headers)
    assert resp.status_code == 403


def test_datenexport_setzt_audit_eintrag(client: TestClient):
    headers = _onboarded_mandant(client, email="export-audit@example.com")
    client.get("/auth/datenexport", headers=headers)

    _, export = _export(client, headers)
    aktionen = [e["aktion"] for e in export["audit_log"]]
    assert "datenexport" in aktionen
