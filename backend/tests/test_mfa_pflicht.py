"""MFA-Pflicht und frische Bestaetigung sensibler Aktionen (docs/specs/mfa-pflicht.md, Sicherheitspaket F3).

Die Testumgebung laeuft sonst mit MFA_PFLICHT=aus (tests/conftest.py). Hier wird die Richtlinie je Test eingeschaltet, damit jede
Regel ohne die Funktion fehlschlaegt.
"""
import time

import jwt
import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth.models import User
from app.config import settings
from app.core.audit_log import AuditLogEintrag
from app.db import SessionLocal
from scripts import konto_wiederherstellen
from tests.test_security_headers import _starte_mit

PW = "correct horse battery staple"
IBAN_A = "DE02120300000000202051"
IBAN_B = "DE89370400440532013000"


@pytest.fixture
def pflicht_owner(monkeypatch):
    monkeypatch.setattr(settings, "mfa_pflicht", "owner")


@pytest.fixture
def pflicht_alle(monkeypatch):
    monkeypatch.setattr(settings, "mfa_pflicht", "alle")


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _owner_mit_mfa(client: TestClient, email: str = "owner@example.org", firma: str = "Pflicht GmbH"):
    """Registriert und richtet MFA ueber den Einrichtungsweg ein. Gibt (Header, TOTP-Secret, Wiederherstellungscodes) zurueck."""
    reg = client.post("/auth/register", json={"email": email, "password": PW, "firmenname": firma}).json()
    pre = _bearer(reg["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    antwort = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()}).json()
    return _bearer(antwort["access_token"]), secret, antwort["wiederherstellungscodes"]


def _anmelden(client: TestClient, email: str, secret: str, **extra) -> dict:
    login = client.post("/auth/login", json={"email": email, "password": PW}).json()
    assert login["status"] == "mfa_required"
    antwort = client.post(
        "/auth/login/mfa", headers=_bearer(login["pre_auth_token"]), json={"code": pyotp.TOTP(secret).now(), **extra},
    )
    assert antwort.status_code == 200, antwort.text
    return _bearer(antwort.json()["access_token"])


def _bestaetigung(client: TestClient, headers: dict, secret: str, aktion: str) -> dict:
    antwort = client.post("/auth/bestaetigung", headers=headers, json={"aktion": aktion, "code": pyotp.TOTP(secret).now()})
    assert antwort.status_code == 200, antwort.text
    return {"X-Bestaetigung": antwort.json()["bestaetigung_token"]}


def _umgeschrieben(token: str, **aenderungen) -> str:
    daten = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    daten.update(aenderungen)
    return jwt.encode(daten, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Pflicht fuer Owner: Anmeldung, Einrichtungs-Scope, Bestandsupgrade


def test_neuer_owner_bekommt_nur_den_einrichtungsweg_keine_fachliche_sitzung(client: TestClient, pflicht_owner):
    reg = client.post("/auth/register", json={"email": "neu@example.org", "password": PW, "firmenname": "Neu GmbH"}).json()
    assert reg["status"] == "mfa_einrichtung_erforderlich"
    assert reg["access_token"] is None
    pre = _bearer(reg["pre_auth_token"])

    # Das Einrichtungs-Token oeffnet die Einrichtung ...
    assert client.post("/auth/mfa/setup", headers=pre).status_code == 200
    # ... aber keine fachliche Route (403 = falscher Token-Scope).
    for pfad in ("/auth/me", "/auth/mandant", "/anlagen", "/auth/datenexport", "/lohn/mitarbeitende"):
        assert client.get(pfad, headers=pre).status_code == 403, pfad


def test_einrichtung_stellt_erst_nach_bestaetigtem_code_eine_volle_sitzung_aus(client: TestClient, pflicht_owner):
    reg = client.post("/auth/register", json={"email": "neu@example.org", "password": PW, "firmenname": "Neu GmbH"}).json()
    pre = _bearer(reg["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]

    falsch = client.post("/auth/mfa/verify", headers=pre, json={"code": "000000"})
    assert falsch.status_code == 400 and "access_token" not in falsch.json()

    ok = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200
    assert len(ok.json()["wiederherstellungscodes"]) == 10  # Notfallweg entsteht mit der Pflicht-Einrichtung
    assert client.get("/auth/me", headers=_bearer(ok.json()["access_token"])).status_code == 200


def test_bestehender_owner_ohne_mfa_kommt_beim_login_nur_in_die_einrichtung(client: TestClient, monkeypatch):
    # Konto entsteht noch ohne Pflicht (Bestandsinstanz vor dem Update) ...
    reg = client.post("/auth/register", json={"email": "alt@example.org", "password": PW, "firmenname": "Alt GmbH"}).json()
    assert reg["status"] == "mfa_optional"
    alt = _bearer(reg["access_token"])
    assert client.get("/auth/me", headers=alt).status_code == 200

    # ... dann gilt die Pflicht (Update auf die neue Version).
    monkeypatch.setattr(settings, "mfa_pflicht", "owner")
    # Die schon ausgestellte volle Sitzung wird sofort verworfen, ohne Migration und ohne erneute Anmeldung.
    verworfen = client.get("/auth/me", headers=alt)
    assert verworfen.status_code == 401
    assert "Zwei-Faktor" in verworfen.json()["detail"]
    assert client.get("/auth/mandant", headers=alt).status_code == 401

    login = client.post("/auth/login", json={"email": "alt@example.org", "password": PW}).json()
    assert login["status"] == "mfa_einrichtung_erforderlich" and login["access_token"] is None

    pre = _bearer(login["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    erledigt = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()})
    assert client.get("/auth/me", headers=_bearer(erledigt.json()["access_token"])).status_code == 200


# ---------------------------------------------------------------------------
# Rollen: Mitglied ohne Pflicht vs. "alle"


def _einladen(client: TestClient, owner: dict, secret: str) -> str:
    bestaetigung = _bestaetigung(client, owner, secret, "benutzer_verwalten")
    antwort = client.post("/auth/einladungen", headers={**owner, **bestaetigung}, json={"rolle": "mitglied"})
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["code"]


def test_mitglied_ohne_pflicht_arbeitet_ohne_mfa(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = _einladen(client, owner, secret)
    reg = client.post("/auth/register", json={"email": "mitglied@example.org", "password": PW, "einladungscode": code}).json()
    assert reg["status"] == "mfa_optional" and reg["access_token"]
    assert client.get("/auth/me", headers=_bearer(reg["access_token"])).json()["rolle"] == "mitglied"


def test_richtlinie_alle_erzwingt_mfa_auch_fuer_mitglieder_und_verwirft_bestehende_sitzungen(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "mfa_pflicht", "owner")
    owner, secret, _ = _owner_mit_mfa(client)
    code = _einladen(client, owner, secret)
    reg = client.post("/auth/register", json={"email": "mitglied@example.org", "password": PW, "einladungscode": code}).json()
    sitzung = _bearer(reg["access_token"])
    assert client.get("/auth/me", headers=sitzung).status_code == 200

    monkeypatch.setattr(settings, "mfa_pflicht", "alle")
    assert client.get("/auth/me", headers=sitzung).status_code == 401
    login = client.post("/auth/login", json={"email": "mitglied@example.org", "password": PW}).json()
    assert login["status"] == "mfa_einrichtung_erforderlich" and login["access_token"] is None


def test_rollenwechsel_in_der_datenbank_wirkt_sofort_nicht_das_token(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = _einladen(client, owner, secret)
    reg = client.post("/auth/register", json={"email": "mitglied@example.org", "password": PW, "einladungscode": code}).json()
    sitzung = _bearer(reg["access_token"])
    assert client.get("/auth/me", headers=sitzung).status_code == 200  # Mitglied ohne MFA

    from app.auth.models import Mitgliedschaft

    with SessionLocal() as db:
        db.query(Mitgliedschaft).filter(Mitgliedschaft.rolle == "mitglied").update({"rolle": "owner"})
        db.commit()
    # Das alte Token nennt keine Rolle; mit der neuen Rolle gilt die Pflicht sofort.
    assert client.get("/auth/me", headers=sitzung).status_code == 401


# ---------------------------------------------------------------------------
# MFA abschalten


def test_pflicht_mfa_laesst_sich_nicht_abschalten_neu_einrichten_geht(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    antwort = client.post(
        "/security/mfa/deaktivieren", headers=owner, json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()},
    )
    assert antwort.status_code == 403
    with SessionLocal() as db:
        assert db.query(User).one().mfa_enabled is True

    neu = client.post(
        "/security/mfa/neu-einrichten", headers=owner, json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()},
    )
    assert neu.status_code == 200


def test_mitglied_ohne_pflicht_darf_mfa_abschalten(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = _einladen(client, owner, secret)
    reg = client.post("/auth/register", json={"email": "mitglied@example.org", "password": PW, "einladungscode": code}).json()
    pre = _bearer(reg["pre_auth_token"])
    mitglied_secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    sitzung = _bearer(client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(mitglied_secret).now()}).json()["access_token"])
    antwort = client.post(
        "/security/mfa/deaktivieren", headers=sitzung,
        json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(mitglied_secret).now()},
    )
    assert antwort.status_code == 204


# ---------------------------------------------------------------------------
# Frische Bestaetigung (Step-up)


def test_iban_aenderung_verlangt_frische_bestaetigung(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)

    ohne = client.patch("/auth/mandant", headers=owner, json={"iban": IBAN_A})
    assert ohne.status_code == 428
    assert client.get("/auth/mandant", headers=owner).json()["iban"] in (None, "")  # nichts wurde geschrieben

    bestaetigt = client.patch("/auth/mandant", headers={**owner, **_bestaetigung(client, owner, secret, "iban_aendern")}, json={"iban": IBAN_A})
    assert bestaetigt.status_code == 200 and bestaetigt.json()["iban"] == IBAN_A


def test_unveraenderte_iban_und_design_felder_brauchen_keine_bestaetigung(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    mit = {**owner, **_bestaetigung(client, owner, secret, "iban_aendern")}
    assert client.patch("/auth/mandant", headers=mit, json={"iban": IBAN_A}).status_code == 200

    # Das Design-Formular schickt die IBAN unveraendert mit: keine neue Bestaetigung noetig.
    assert client.patch("/auth/mandant", headers=owner, json={"iban": IBAN_A, "akzentfarbe": "#123456"}).status_code == 200
    # Andere Stammdaten ohne Bankbezug gehoeren nicht zur Klasse.
    assert client.patch("/auth/mandant", headers=owner, json={"ust_id": "DE123456789"}).status_code == 200
    # Eine andere IBAN dagegen wieder schon.
    assert client.patch("/auth/mandant", headers=owner, json={"iban": IBAN_B}).status_code == 428


@pytest.mark.parametrize(
    "methode,pfad,json_body,erfolg",
    [
        ("POST", "/auth/einladungen", {"rolle": "mitglied"}, 201),
        ("POST", "/auth/mitglieder", {"email": "direkt@example.org", "rolle": "mitglied"}, 201),
        ("GET", "/auth/datenexport", None, 200),
    ],
)
def test_benutzerverwaltung_und_gesamtexport_verlangen_bestaetigung(client: TestClient, pflicht_owner, methode, pfad, json_body, erfolg):
    owner, secret, _ = _owner_mit_mfa(client)
    assert client.request(methode, pfad, headers=owner, json=json_body).status_code == 428
    aktion = "gesamtexport" if pfad.endswith("datenexport") else "benutzer_verwalten"
    mit = {**owner, **_bestaetigung(client, owner, secret, aktion)}
    assert client.request(methode, pfad, headers=mit, json=json_body).status_code == erfolg


def test_mitglied_entfernen_verlangt_bestaetigung(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    mit = {**owner, **_bestaetigung(client, owner, secret, "benutzer_verwalten")}
    angelegt = client.post("/auth/mitglieder", headers=mit, json={"email": "direkt@example.org", "rolle": "mitglied"}).json()
    ziel = f"/auth/mitglieder/{angelegt['user_id']}/entfernen"
    assert client.post(ziel, headers=owner).status_code == 428
    assert client.post(ziel, headers=mit).status_code == 204


def test_bestaetigung_gilt_nur_fuer_ihre_aktionsklasse(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    export = {**owner, **_bestaetigung(client, owner, secret, "gesamtexport")}
    assert client.get("/auth/datenexport", headers=export).status_code == 200
    assert client.post("/auth/einladungen", headers=export, json={}).status_code == 428
    assert client.patch("/auth/mandant", headers=export, json={"iban": IBAN_A}).status_code == 428


def test_bestaetigung_ist_an_die_sitzung_gebunden(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    token = _bestaetigung(client, owner, secret, "gesamtexport")
    zweite_sitzung = _anmelden(client, "owner@example.org", secret)
    assert client.get("/auth/datenexport", headers={**zweite_sitzung, **token}).status_code == 428
    assert client.get("/auth/datenexport", headers={**owner, **token}).status_code == 200


def test_bestaetigung_eines_anderen_kontos_oder_mandanten_wird_verworfen(client: TestClient, pflicht_owner):
    a, secret_a, _ = _owner_mit_mfa(client, "a@example.org", "A GmbH")
    b, _, _ = _owner_mit_mfa(client, "b@example.org", "B GmbH")
    fremd = _bestaetigung(client, a, secret_a, "gesamtexport")
    assert client.get("/auth/datenexport", headers={**b, **fremd}).status_code == 428


def test_abgelaufene_manipulierte_und_fremde_token_werden_verworfen(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    token = _bestaetigung(client, owner, secret, "gesamtexport")["X-Bestaetigung"]

    abgelaufen = _umgeschrieben(token, exp=int(time.time()) - 5)
    assert client.get("/auth/datenexport", headers={**owner, "X-Bestaetigung": abgelaufen}).status_code == 428

    andere_klasse = _umgeschrieben(token, aktion="benutzer_verwalten")
    assert client.get("/auth/datenexport", headers={**owner, "X-Bestaetigung": andere_klasse}).status_code == 428

    veraltete_version = _umgeschrieben(token, sv=-1)
    assert client.get("/auth/datenexport", headers={**owner, "X-Bestaetigung": veraltete_version}).status_code == 428

    falsch_signiert = jwt.encode(jwt.decode(token, options={"verify_signature": False}), "anderes-geheimnis" * 3, algorithm="HS256")
    assert client.get("/auth/datenexport", headers={**owner, "X-Bestaetigung": falsch_signiert}).status_code == 428
    assert client.get("/auth/datenexport", headers={**owner, "X-Bestaetigung": "kein-token"}).status_code == 428

    # Das Bestaetigungs-Token ist kein Zugriffstoken.
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 403


def test_bestaetigung_endet_mit_der_sitzung(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    token = _bestaetigung(client, owner, secret, "gesamtexport")
    assert client.post("/auth/logout", headers=owner).status_code == 204
    assert client.get("/auth/datenexport", headers={**owner, **token}).status_code == 401


def test_gueltigkeitsfenster_ist_kurz(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    assert settings.bestaetigung_minuten == 5
    antwort = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": pyotp.TOTP(secret).now()}).json()
    daten = jwt.decode(antwort["bestaetigung_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert 0 < daten["exp"] - time.time() <= 5 * 60 + 5


def test_bestaetigung_prueft_den_code_mit_replay_schutz_und_sperre(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = pyotp.TOTP(secret).now()
    erst = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": code})
    assert erst.status_code == 200
    replay = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": code})
    assert replay.status_code == 400  # derselbe TOTP-Code laesst sich nicht noch einmal verwenden

    for _ in range(settings.failed_login_limit):
        client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": "000000"})
    gesperrt = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": pyotp.TOTP(secret).now()})
    assert gesperrt.status_code == 429


def test_wiederherstellungscode_bestaetigt_einmalig(client: TestClient, pflicht_owner):
    owner, _, codes = _owner_mit_mfa(client)
    ok = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": codes[0]})
    assert ok.status_code == 200
    nochmal = client.post("/auth/bestaetigung", headers=owner, json={"aktion": "gesamtexport", "code": codes[0]})
    assert nochmal.status_code == 400


def test_geraet_merken_ersetzt_keine_frische_bestaetigung(client: TestClient, pflicht_owner):
    _, secret, _ = _owner_mit_mfa(client)
    lange_sitzung = _anmelden(client, "owner@example.org", secret, remember_device=True)
    assert client.get("/auth/me", headers=lange_sitzung).status_code == 200
    assert client.get("/auth/datenexport", headers=lange_sitzung).status_code == 428
    assert client.patch("/auth/mandant", headers=lange_sitzung, json={"iban": IBAN_A}).status_code == 428


def test_mitglied_kann_owner_aktionen_auch_mit_eigener_bestaetigung_nicht_ausfuehren(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = _einladen(client, owner, secret)
    reg = client.post("/auth/register", json={"email": "mitglied@example.org", "password": PW, "einladungscode": code}).json()
    pre = _bearer(reg["pre_auth_token"])
    m_secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    mitglied = _bearer(client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(m_secret).now()}).json()["access_token"])
    mit = {**mitglied, **_bestaetigung(client, mitglied, m_secret, "benutzer_verwalten")}
    assert client.post("/auth/einladungen", headers=mit, json={}).status_code == 403
    assert client.patch("/auth/mandant", headers=mit, json={"iban": IBAN_A}).status_code == 403


def test_bestaetigung_wird_protokolliert_ohne_den_code(client: TestClient, pflicht_owner):
    owner, secret, _ = _owner_mit_mfa(client)
    code = pyotp.TOTP(secret).now()
    assert client.post("/auth/bestaetigung", headers=owner, json={"aktion": "iban_aendern", "code": code}).status_code == 200
    with SessionLocal() as db:
        eintraege = db.query(AuditLogEintrag).filter(AuditLogEintrag.aktion == "bestaetigung_erteilt").all()
        assert len(eintraege) == 1 and eintraege[0].kontext == "iban_aendern"
        alles = " ".join(f"{e.aktion} {e.kontext}" for e in db.query(AuditLogEintrag).all())
    assert code not in alles


# ---------------------------------------------------------------------------
# Recovery darf die Richtlinie nicht umgehen


def test_betreiber_reset_fuehrt_den_owner_in_die_neueinrichtung_nicht_zu_einem_zugang_ohne_mfa(client: TestClient, pflicht_owner):
    owner, _, _ = _owner_mit_mfa(client)
    with SessionLocal() as db:
        konto_wiederherstellen.wiederherstellen(
            db, email="owner@example.org", neues_passwort="ein ganz neues passwort 2026", mfa_zuruecksetzen=True,
        )
    assert client.get("/auth/me", headers=owner).status_code == 401  # Sitzungen widerrufen
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": "ein ganz neues passwort 2026"}).json()
    assert login["status"] == "mfa_einrichtung_erforderlich" and login["access_token"] is None


def test_passwort_vergessen_laesst_mfa_aktiv(client: TestClient, pflicht_owner):
    _, _, _ = _owner_mit_mfa(client)
    with SessionLocal() as db:
        konto_wiederherstellen.wiederherstellen(db, email="owner@example.org", neues_passwort="ein ganz neues passwort 2026")
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": "ein ganz neues passwort 2026"}).json()
    assert login["status"] == "mfa_required"


def test_anmeldung_mit_wiederherstellungscode_bleibt_moeglich_und_ist_mfa(client: TestClient, pflicht_owner):
    _, _, codes = _owner_mit_mfa(client)
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": PW}).json()
    antwort = client.post(
        "/auth/login/mfa/wiederherstellungscode", headers=_bearer(login["pre_auth_token"]), json={"wiederherstellungscode": codes[0]},
    )
    assert antwort.status_code == 200
    assert client.get("/auth/me", headers=_bearer(antwort.json()["access_token"])).status_code == 200


# ---------------------------------------------------------------------------
# Konfiguration


def test_mfa_pflicht_aus_ist_in_produktion_und_staging_verboten():
    for env in ("production", "staging"):
        ergebnis = _starte_mit(
            {"APP_ENV": env, "TRUSTED_HOSTS_RAW": "api.example.org", "CORS_ALLOWED_ORIGINS_RAW": "https://example.org", "MFA_PFLICHT": "aus"},
            "from app.main import app",
        )
        assert ergebnis.returncode != 0, env
        assert "MFA_PFLICHT" in ergebnis.stderr


def test_standard_der_richtlinie_ist_owner():
    """Ohne gesetzte Variable gilt owner (die Testumgebung setzt sonst "aus", deshalb ein eigener Prozess ohne MFA_PFLICHT)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k != "MFA_PFLICHT"}
    ergebnis = subprocess.run(
        [sys.executable, "-c", "from app.config import settings; print('STANDARD=' + settings.mfa_pflicht)"],
        cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True, timeout=120,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr[-2000:]
    assert "STANDARD=owner" in ergebnis.stdout
