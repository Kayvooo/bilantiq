import pyotp
from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _register_and_verify(client: TestClient, email: str, password: str = "correct horse battery staple", **extra) -> dict:
    reg = client.post("/auth/register", json={"email": email, "password": password, **extra}).json()
    headers_pre = {"Authorization": f"Bearer {reg['pre_auth_token']}"}
    secret = client.post("/auth/mfa/setup", headers=headers_pre).json()["secret"]
    code = pyotp.TOTP(secret).now()
    access_token = client.post("/auth/mfa/verify", headers=headers_pre, json={"code": code}).json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_register_without_code_still_requires_firmenname(client: TestClient):
    resp = client.post("/auth/register", json={"email": "x@example.com", "password": "correct horse battery staple"})
    assert resp.status_code == 400


def test_owner_can_create_and_list_einladung(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post("/auth/einladungen", headers=headers, json={"rolle": "mitglied"})
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["code"]) == 12  # 48 Bit, vorher 8 Zeichen (Brute-Force-Haertung)
    assert body["widerrufen"] is False

    liste = client.get("/auth/einladungen", headers=headers).json()
    assert len(liste) == 1


def test_mitglied_cannot_create_einladung(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner@example.com")
    code = client.post("/auth/einladungen", headers=owner_headers, json={}).json()["code"]
    mitglied_headers = _register_and_verify(client, "mitglied@example.com", einladungscode=code)

    resp = client.post("/auth/einladungen", headers=mitglied_headers, json={})
    assert resp.status_code == 403


def test_einladungscode_joins_existing_mandant_with_correct_rolle(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner2@example.com")
    owner_mandant_id = client.get("/auth/me", headers=owner_headers).json()["mandant_id"]
    code = client.post("/auth/einladungen", headers=owner_headers, json={"rolle": "mitglied"}).json()["code"]

    mitglied_headers = _register_and_verify(client, "beitretend@example.com", einladungscode=code)
    me = client.get("/auth/me", headers=mitglied_headers).json()
    assert me["mandant_id"] == owner_mandant_id
    assert me["rolle"] == "mitglied"

    mitglieder = client.get("/auth/mitglieder", headers=owner_headers).json()
    assert len(mitglieder) == 2
    assert {m["rolle"] for m in mitglieder} == {"owner", "mitglied"}


def test_einladung_kann_nicht_zweimal_eingeloest_werden(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner3@example.com")
    code = client.post("/auth/einladungen", headers=owner_headers, json={}).json()["code"]
    _register_and_verify(client, "erste@example.com", einladungscode=code)

    resp = client.post("/auth/register", json={"email": "zweite@example.com", "password": "correct horse battery staple", "einladungscode": code})
    assert resp.status_code == 400


def test_widerrufene_einladung_kann_nicht_eingeloest_werden(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner4@example.com")
    einladung = client.post("/auth/einladungen", headers=owner_headers, json={}).json()
    client.post(f"/auth/einladungen/{einladung['id']}/widerrufen", headers=owner_headers)

    resp = client.post(
        "/auth/register",
        json={"email": "spaet@example.com", "password": "correct horse battery staple", "einladungscode": einladung["code"]},
    )
    assert resp.status_code == 400


def test_owner_kann_mitglied_entfernen_und_login_schlaegt_danach_fehl(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner5@example.com")
    code = client.post("/auth/einladungen", headers=owner_headers, json={}).json()["code"]
    _register_and_verify(client, "entfernbar@example.com", einladungscode=code)

    mitglieder = client.get("/auth/mitglieder", headers=owner_headers).json()
    mitglied = next(m for m in mitglieder if m["rolle"] == "mitglied")

    resp = client.post(f"/auth/mitglieder/{mitglied['user_id']}/entfernen", headers=owner_headers)
    assert resp.status_code == 204

    login = client.post("/auth/login", json={"email": "entfernbar@example.com", "password": "correct horse battery staple"})
    assert login.status_code == 401


def test_owner_kann_sich_nicht_selbst_entfernen(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner6@example.com")
    me = client.get("/auth/me", headers=owner_headers).json()

    resp = client.post(f"/auth/mitglieder/{me['user_id']}/entfernen", headers=owner_headers)
    assert resp.status_code == 400


def test_mitglied_kann_nicht_mitglieder_entfernen(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner7@example.com")
    code = client.post("/auth/einladungen", headers=owner_headers, json={}).json()["code"]
    mitglied_headers = _register_and_verify(client, "kein-owner@example.com", einladungscode=code)

    me = client.get("/auth/me", headers=owner_headers).json()
    resp = client.post(f"/auth/mitglieder/{me['user_id']}/entfernen", headers=mitglied_headers)
    assert resp.status_code == 403


def test_owner_kann_mitglied_direkt_anlegen_und_es_kann_sich_einloggen(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner8@example.com")
    resp = client.post("/auth/mitglieder", headers=owner_headers, json={"email": "direkt@example.com", "rolle": "mitglied"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "direkt@example.com"
    assert body["rolle"] == "mitglied"
    assert len(body["initial_passwort"]) >= 12

    login = client.post("/auth/login", json={"email": "direkt@example.com", "password": body["initial_passwort"]})
    assert login.status_code == 200
    assert login.json()["status"] == "mfa_optional"

    mitglieder = client.get("/auth/mitglieder", headers=owner_headers).json()
    assert {m["email"] for m in mitglieder} == {"owner8@example.com", "direkt@example.com"}


def test_mitglied_direkt_anlegen_lehnt_doppelte_email_ab(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner9@example.com")
    client.post("/auth/mitglieder", headers=owner_headers, json={"email": "doppelt@example.com", "rolle": "mitglied"})

    resp = client.post("/auth/mitglieder", headers=owner_headers, json={"email": "doppelt@example.com", "rolle": "mitglied"})
    assert resp.status_code == 400


def test_mitglied_kann_nicht_mitglied_direkt_anlegen(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner10@example.com")
    code = client.post("/auth/einladungen", headers=owner_headers, json={}).json()["code"]
    mitglied_headers = _register_and_verify(client, "kein-owner2@example.com", einladungscode=code)

    resp = client.post("/auth/mitglieder", headers=mitglied_headers, json={"email": "neu@example.com", "rolle": "mitglied"})
    assert resp.status_code == 403


def test_passwort_aendern_und_login_mit_neuem_passwort(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner11@example.com")

    resp = client.post(
        "/auth/passwort/aendern", headers=owner_headers,
        json={"aktuelles_passwort": "correct horse battery staple", "neues_passwort": "ein ganz neues passwort"},
    )
    assert resp.status_code == 204

    alt = client.post("/auth/login", json={"email": "owner11@example.com", "password": "correct horse battery staple"})
    assert alt.status_code == 401

    neu = client.post("/auth/login", json={"email": "owner11@example.com", "password": "ein ganz neues passwort"})
    assert neu.status_code == 200


def test_passwort_aendern_lehnt_falsches_aktuelles_passwort_ab(client: TestClient):
    owner_headers = _onboarded_mandant(client, email="owner12@example.com")

    resp = client.post(
        "/auth/passwort/aendern", headers=owner_headers,
        json={"aktuelles_passwort": "falsches passwort hier", "neues_passwort": "ein ganz neues passwort"},
    )
    assert resp.status_code == 400
