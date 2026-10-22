from fastapi.testclient import TestClient


def test_health_liefert_nur_status_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_ready_prueft_datenbank_und_liefert_nur_status(client: TestClient):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    # Kein Cache und die ueblichen Security-Header gelten auch hier.
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_health_ready_503_ohne_details_wenn_datenbank_fehlt(client: TestClient, monkeypatch, caplog):
    class KaputteEngine:
        def connect(self):
            raise RuntimeError("could not connect to server postgres://geheim:passwort@db-intern:5432/x")

    monkeypatch.setattr("app.main.engine", KaputteEngine())
    with caplog.at_level("WARNING"):
        resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
    body = resp.text
    assert "passwort" not in body and "db-intern" not in body
    # Auch das Log enthaelt nur den Fehlertyp, nicht die Meldung mit Zugangsdaten.
    assert "RuntimeError" in caplog.text
    assert "passwort" not in caplog.text


def test_health_endpunkte_ohne_anmeldung_erreichbar(client: TestClient):
    # Monitoring hat kein Token; beide Endpunkte duerfen keinen Login verlangen.
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200
