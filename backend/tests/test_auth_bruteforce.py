"""Brute-Force-Schutz der Auth-Pfade (Release-Plan 4.1/4.3): Login, MFA-Code, Registrierung, MFA-Deaktivierung,
Passwortaenderung, Benutzer-Enumeration und serverseitiges Abmelden."""
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth import routes as auth_routes
from app.auth.models import User
from app.core import ratelimit
from app.core.audit_log import AuditLogEintrag
from app.db import SessionLocal
from tests.test_auth import _complete_mfa_enrollment, _register

EMAIL = "kevin@example.com"
PW = "correct horse battery staple"


def _mfa_nutzer(client: TestClient) -> tuple[str, dict]:
    """Konto mit aktivem MFA. Gibt (TOTP-Secret, Header der vollen Sitzung) zurueck."""
    daten = _register(client)
    secret, token = _complete_mfa_enrollment(client, daten["pre_auth_token"])
    return secret, {"Authorization": f"Bearer {token}"}


def _pre_token(client: TestClient) -> dict:
    antwort = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert antwort.status_code == 200 and antwort.json()["status"] == "mfa_required"
    return {"Authorization": f"Bearer {antwort.json()['pre_auth_token']}"}


def _falscher_code(secret: str) -> str:
    richtig = {pyotp.TOTP(secret).at(datetime.now(timezone.utc) + timedelta(seconds=d)) for d in (-30, 0, 30)}
    return next(f"{n:06d}" for n in range(100000, 100100) if f"{n:06d}" not in richtig)


def _sperre_ablaufen_lassen() -> None:
    with SessionLocal() as db:
        user = db.query(User).one()
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()


# ---------------------------------------------------------------------------
# MFA-Code beim Anmelden


def test_mfa_code_raten_beim_login_sperrt_das_konto_nach_fuenf_fehlversuchen(client: TestClient):
    secret, _ = _mfa_nutzer(client)
    pre = _pre_token(client)
    falsch = _falscher_code(secret)

    for _ in range(4):
        assert client.post("/auth/login/mfa", headers=pre, json={"code": falsch}).status_code == 400
    # Der fuenfte Fehlversuch sperrt das Konto und meldet das auch (429 statt 400).
    assert client.post("/auth/login/mfa", headers=pre, json={"code": falsch}).status_code == 429

    # Jetzt gesperrt: auch der richtige Code wird nicht mehr akzeptiert ...
    richtig = pyotp.TOTP(secret).now()
    gesperrt = client.post("/auth/login/mfa", headers=pre, json={"code": richtig})
    assert gesperrt.status_code == 429
    # ... und auch eine neue Anmeldung mit Passwort ist blockiert (generische Meldung, kein Hinweis auf das Konto).
    erneut = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert erneut.status_code == 401 and erneut.json()["detail"] == "E-Mail oder Passwort ist falsch."

    with SessionLocal() as db:
        aktionen = [e.aktion for e in db.query(AuditLogEintrag).all()]
    assert aktionen.count("mfa_code_falsch") == 5
    assert "konto_gesperrt" in aktionen


def test_erneutes_anmelden_mit_passwort_setzt_den_mfa_zaehler_nicht_zurueck(client: TestClient):
    secret, _ = _mfa_nutzer(client)
    falsch = _falscher_code(secret)
    for _ in range(4):
        pre = _pre_token(client)  # jedes Mal ein frisches Pre-Auth-Token mit korrektem Passwort
        assert client.post("/auth/login/mfa", headers=pre, json={"code": falsch}).status_code == 400

    pre = _pre_token(client)
    assert client.post("/auth/login/mfa", headers=pre, json={"code": falsch}).status_code == 429  # 5. Fehlversuch sperrt
    assert client.post("/auth/login", json={"email": EMAIL, "password": PW}).status_code == 401  # gesperrt


def test_nach_ablauf_der_sperre_funktioniert_der_richtige_code_und_setzt_zurueck(client: TestClient):
    secret, _ = _mfa_nutzer(client)
    pre = _pre_token(client)
    for _ in range(5):
        client.post("/auth/login/mfa", headers=pre, json={"code": _falscher_code(secret)})
    _sperre_ablaufen_lassen()

    antwort = client.post("/auth/login/mfa", headers=pre, json={"code": pyotp.TOTP(secret).now()})
    assert antwort.status_code == 200
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.failed_login_count == 0 and user.locked_until is None


def test_richtiger_mfa_code_vor_dem_limit_setzt_den_zaehler_zurueck(client: TestClient):
    secret, _ = _mfa_nutzer(client)
    pre = _pre_token(client)
    for _ in range(3):
        client.post("/auth/login/mfa", headers=pre, json={"code": _falscher_code(secret)})
    assert client.post("/auth/login/mfa", headers=pre, json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    with SessionLocal() as db:
        assert db.query(User).one().failed_login_count == 0


# ---------------------------------------------------------------------------
# Erstes Einrichten von MFA mit dem Pre-Auth-Token


def test_mfa_einrichtung_zaehlt_falsche_codes_ebenfalls(client: TestClient):
    daten = _register(client)
    pre = {"Authorization": f"Bearer {daten['pre_auth_token']}"}
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    falsch = _falscher_code(secret)
    for _ in range(4):
        assert client.post("/auth/mfa/verify", headers=pre, json={"code": falsch}).status_code == 400
    assert client.post("/auth/mfa/verify", headers=pre, json={"code": falsch}).status_code == 429
    assert client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()}).status_code == 429


# ---------------------------------------------------------------------------
# MFA deaktivieren / Passwort aendern (Code-/Passwort-Raten mit laufender Sitzung)


def test_mfa_deaktivierung_begrenzt_das_raten_des_codes(client: TestClient):
    secret, headers = _mfa_nutzer(client)
    falsch = _falscher_code(secret)
    for _ in range(4):
        assert client.post(
            "/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": falsch},
        ).status_code == 400
    assert client.post(
        "/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": falsch},
    ).status_code == 429

    richtig = pyotp.TOTP(secret).now()
    gesperrt = client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": richtig})
    assert gesperrt.status_code == 429
    assert client.get("/security", headers=headers).json()["mfa_enabled"] is True  # MFA blieb aktiv


def test_mfa_zaehler_laesst_sich_nicht_ueber_die_passwortpruefung_zuruecksetzen(client: TestClient):
    """Ein Angreifer mit Sitzung und Passwort darf den Code-Zaehler nicht durch erfolgreiche Passwortpruefungen leeren."""
    secret, headers = _mfa_nutzer(client)
    falsch = _falscher_code(secret)
    for _ in range(4):
        client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": falsch})
    # Passwort stimmt hier, also ein "erfolgreicher" Schritt an anderer Stelle (Passwort aendern wuerde alle Sitzungen beenden,
    # darum die Mailaenderung, die nur das Passwort prueft; der SMTP-Versand schlaegt in der Testumgebung fehl -> 502).
    client.post("/security/email/aenderung-starten", headers=headers, json={"neues_email": "neu@example.com", "aktuelles_passwort": PW})
    client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": falsch})
    antwort = client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()})
    assert antwort.status_code == 429


def test_passwortaenderung_begrenzt_das_raten_des_aktuellen_passworts(client: TestClient):
    daten = _register(client)
    headers = {"Authorization": f"Bearer {daten['access_token']}"}
    falsch = {"aktuelles_passwort": "falsch-falsch-falsch", "neues_passwort": "ein neues langes Passwort"}
    for _ in range(4):
        assert client.post("/auth/passwort/aendern", headers=headers, json=falsch).status_code == 400
    assert client.post("/auth/passwort/aendern", headers=headers, json=falsch).status_code == 429
    gesperrt = client.post("/auth/passwort/aendern", headers=headers, json={"aktuelles_passwort": PW, "neues_passwort": "ein neues langes Passwort"})
    assert gesperrt.status_code == 429


# ---------------------------------------------------------------------------
# Rate-Limits pro IP


def test_login_ist_pro_ip_begrenzt(client: TestClient, monkeypatch):
    monkeypatch.setattr(auth_routes, "LOGIN_PRO_IP", (3, 300))
    for _ in range(3):
        assert client.post("/auth/login", json={"email": "wer@example.com", "password": "irgendwas-langes"}).status_code == 401
    blockiert = client.post("/auth/login", json={"email": "wer@example.com", "password": "irgendwas-langes"})
    assert blockiert.status_code == 429
    assert int(blockiert.headers["Retry-After"]) >= 1


def test_registrierung_ist_pro_ip_begrenzt_auch_beim_raten_von_einladungscodes(client: TestClient, monkeypatch):
    monkeypatch.setattr(auth_routes, "REGISTRIERUNG_PRO_IP", (3, 3600))
    for i in range(3):
        antwort = client.post("/auth/register", json={"email": f"x{i}@example.com", "password": PW, "einladungscode": "AAAAAAAAAAAA"})
        assert antwort.status_code == 400
    assert client.post("/auth/register", json={"email": "x9@example.com", "password": PW, "einladungscode": "BBBBBBBBBBBB"}).status_code == 429
    assert client.post("/auth/register", json={"email": "ok@example.com", "password": PW, "firmenname": "Firma"}).status_code == 429


def test_mfa_code_versuche_sind_pro_ip_begrenzt(client: TestClient, monkeypatch):
    secret, _ = _mfa_nutzer(client)
    pre = _pre_token(client)
    ratelimit.zuruecksetzen()
    monkeypatch.setattr(auth_routes, "MFA_CODE_PRO_IP", (2, 300))
    assert client.post("/auth/login/mfa", headers=pre, json={"code": _falscher_code(secret)}).status_code == 400
    assert client.post("/auth/login/mfa", headers=pre, json={"code": _falscher_code(secret)}).status_code == 400
    assert client.post("/auth/login/mfa", headers=pre, json={"code": _falscher_code(secret)}).status_code == 429


def test_ratelimit_fenster_laeuft_ab(monkeypatch):
    jetzt = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: jetzt[0])
    ratelimit.begrenze("k", limit=2, fenster_sekunden=60)
    ratelimit.begrenze("k", limit=2, fenster_sekunden=60)
    with pytest.raises(Exception) as fehler:
        ratelimit.begrenze("k", limit=2, fenster_sekunden=60)
    assert fehler.value.status_code == 429
    ratelimit.begrenze("anderer", limit=2, fenster_sekunden=60)  # andere Schluessel sind unabhaengig
    jetzt[0] += 61
    ratelimit.begrenze("k", limit=2, fenster_sekunden=60)  # Fenster abgelaufen


# ---------------------------------------------------------------------------
# Benutzer-Enumeration / Timing


def test_login_antworten_verraten_nicht_ob_das_konto_existiert(client: TestClient):
    _register(client)
    unbekannt = client.post("/auth/login", json={"email": "niemand@example.com", "password": "falsch-falsch-falsch"})
    falsches_pw = client.post("/auth/login", json={"email": EMAIL, "password": "falsch-falsch-falsch"})
    assert (unbekannt.status_code, unbekannt.json()) == (falsches_pw.status_code, falsches_pw.json())


def test_login_rechnet_auch_bei_unbekanntem_oder_gesperrtem_konto_einen_passworthash(client: TestClient, monkeypatch):
    """Sonst antwortet "unbekannt" in Millisekunden und "bekannt" in ~100 ms: die Zeit verraet das Konto."""
    _register(client)
    aufrufe: list[str] = []
    original = auth_routes.verify_password
    monkeypatch.setattr(auth_routes, "verify_password", lambda pw, h: aufrufe.append(h) or original(pw, h))

    client.post("/auth/login", json={"email": "niemand@example.com", "password": "falsch-falsch-falsch"})
    assert len(aufrufe) == 1  # unbekanntes Konto: Dummy-Hash geprueft

    for _ in range(5):
        client.post("/auth/login", json={"email": EMAIL, "password": "falsch-falsch-falsch"})
    aufrufe.clear()
    client.post("/auth/login", json={"email": EMAIL, "password": PW})  # gesperrt
    assert len(aufrufe) == 1


def test_uebergrosse_passwoerter_werden_vor_dem_hashen_abgelehnt(client: TestClient):
    riesig = "a" * 5000
    assert client.post("/auth/login", json={"email": EMAIL, "password": riesig}).status_code == 422
    assert client.post("/auth/register", json={"email": EMAIL, "password": riesig, "firmenname": "x"}).status_code == 422


# ---------------------------------------------------------------------------
# Sitzungen


def test_logout_beendet_die_sitzung_serverseitig(client: TestClient):
    daten = _register(client)
    headers = {"Authorization": f"Bearer {daten['access_token']}"}
    zweite = client.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    assert client.get("/auth/me", headers=headers).status_code == 200

    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    # Andere Sitzungen bleiben bestehen.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {zweite}"}).status_code == 200


def test_logout_braucht_eine_gueltige_sitzung(client: TestClient):
    assert client.post("/auth/logout").status_code == 401


# ---------------------------------------------------------------------------
# Konto loeschen (DELETE /auth/me) braucht Passwort und -- bei aktivem MFA -- den aktuellen Code


def _loeschen(client: TestClient, headers: dict, **body):
    return client.request("DELETE", "/auth/me", headers=headers, json=body)


def test_konto_loeschen_ohne_bestaetigung_oder_mit_falschem_passwort_wird_abgelehnt(client: TestClient):
    secret, headers = _mfa_nutzer(client)
    assert client.request("DELETE", "/auth/me", headers=headers).status_code == 422  # Body fehlt
    falsch = _loeschen(client, headers, passwort="falsches-passwort-123", mfa_code=pyotp.TOTP(secret).now())
    assert falsch.status_code == 400
    # Konto lebt weiter, Anmeldung klappt noch
    assert client.get("/auth/me", headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.query(User).one().geloescht_am is None


def test_konto_loeschen_mit_mfa_verlangt_code_und_zaehlt_falsche_codes(client: TestClient):
    secret, headers = _mfa_nutzer(client)
    ohne_code = _loeschen(client, headers, passwort=PW)
    assert ohne_code.status_code == 400
    assert "MFA" in ohne_code.json()["detail"]
    falsch = _falscher_code(secret)
    assert _loeschen(client, headers, passwort=PW, mfa_code=falsch).status_code == 400
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.geloescht_am is None
        assert user.failed_login_count == 1


def test_konto_loeschen_fehlversuche_sperren_das_konto_im_gemeinsamen_zaehler(client: TestClient):
    _, headers = _mfa_nutzer(client)
    for _ in range(4):
        assert _loeschen(client, headers, passwort="falsches-passwort-123").status_code == 400
    assert _loeschen(client, headers, passwort="falsches-passwort-123").status_code == 429
    # gesperrt: auch mit richtigen Angaben geht es jetzt nicht
    assert _loeschen(client, headers, passwort=PW).status_code == 429
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.geloescht_am is None and user.locked_until is not None
        aktionen = [e.aktion for e in db.query(AuditLogEintrag).all()]
    assert "passwort_pruefung_fehlgeschlagen" in aktionen and "konto_gesperrt" in aktionen


def test_konto_loeschen_ohne_mfa_braucht_nur_das_passwort(client: TestClient):
    daten = _register(client)
    assert daten["status"] == "mfa_optional" or daten.get("access_token")
    headers = {"Authorization": f"Bearer {daten['access_token']}"}
    assert _loeschen(client, headers, passwort="falsches-passwort-123").status_code == 400
    assert _loeschen(client, headers, passwort=PW).status_code == 204
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.geloescht_am is not None and user.failed_login_count == 0
