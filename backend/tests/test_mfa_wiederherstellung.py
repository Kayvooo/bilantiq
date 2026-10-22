"""TOTP-Replay-Schutz und MFA-Wiederherstellungscodes (app/auth/mfa_service.py).

``pyotp.TOTP(...).now()`` liefert in diesen Tests dank der Fixture ``_totp_uhr`` (conftest.py) bei jedem Aufruf den Code
des naechsten Zeitschritts; wer Replay pruefen will, sendet denselben Code-String zweimal.
"""
import re

import pyotp
from fastapi.testclient import TestClient

from app.auth import mfa_service
from app.auth.models import MfaWiederherstellungscode, User
from app.core import security
from app.core.audit_log import AuditLogEintrag
from app.db import SessionLocal

EMAIL = "kevin@example.com"
PW = "correct horse battery staple"
CODE_FORMAT = re.compile(r"^[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}$")


def _kopf(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _registrieren(client: TestClient) -> dict:
    antwort = client.post("/auth/register", json={"email": EMAIL, "password": PW, "firmenname": "Kevin GmbH"})
    assert antwort.status_code == 201
    return antwort.json()


def _mfa_aktivieren(client: TestClient) -> tuple[str, str, list[str]]:
    """Registrierung + Ersteinrichtung. Gibt (TOTP-Secret, Token der vollen Sitzung, Wiederherstellungscodes) zurueck."""
    pre = _kopf(_registrieren(client)["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    antwort = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()})
    assert antwort.status_code == 200
    return secret, antwort.json()["access_token"], antwort.json()["wiederherstellungscodes"]


def _pre_login(client: TestClient) -> dict:
    antwort = client.post("/auth/login", json={"email": EMAIL, "password": PW})
    assert antwort.status_code == 200 and antwort.json()["status"] == "mfa_required"
    return _kopf(antwort.json()["pre_auth_token"])


def _aktionen() -> list[str]:
    with SessionLocal() as db:
        return [e.aktion for e in db.query(AuditLogEintrag).all()]


def _offene_codes() -> int:
    with SessionLocal() as db:
        return db.query(MfaWiederherstellungscode).filter(MfaWiederherstellungscode.verbraucht_am.is_(None)).count()


# ---------------------------------------------------------------------------
# TOTP-Replay-Schutz


def test_pruefe_mfa_zeitschritt_lehnt_verbrauchte_und_aeltere_zeitschritte_ab():
    secret = pyotp.random_base32()
    jetzt = security.aktueller_zeitschritt()
    code = pyotp.TOTP(secret).at(jetzt * 30)
    assert security.pruefe_mfa_zeitschritt(secret=secret, code=code, letzter_zeitschritt=None) == jetzt
    assert security.pruefe_mfa_zeitschritt(secret=secret, code=code, letzter_zeitschritt=jetzt - 1) == jetzt
    assert security.pruefe_mfa_zeitschritt(secret=secret, code=code, letzter_zeitschritt=jetzt) is None
    assert security.pruefe_mfa_zeitschritt(secret=secret, code=code, letzter_zeitschritt=jetzt + 5) is None
    # Toleranz +-1 Schritt bleibt erhalten, ein Code aus Schritt jetzt-1 ist gueltig, solange er nicht verbraucht ist.
    alt = pyotp.TOTP(secret).at((jetzt - 1) * 30)
    assert security.pruefe_mfa_zeitschritt(secret=secret, code=alt, letzter_zeitschritt=None) == jetzt - 1
    assert security.pruefe_mfa_zeitschritt(secret=secret, code="abcdef", letzter_zeitschritt=None) is None
    assert security.pruefe_mfa_zeitschritt(secret=secret, code="ünicö", letzter_zeitschritt=None) is None  # kein TypeError


def test_gleichzeitige_anfragen_mit_demselben_code_nur_eine_gewinnt(client: TestClient):
    secret, _, _ = _mfa_aktivieren(client)
    code = pyotp.TOTP(secret).now()
    with SessionLocal() as erste, SessionLocal() as zweite:
        u1, u2 = erste.query(User).one(), zweite.query(User).one()  # beide sehen noch den alten Zaehler
        assert mfa_service.verbrauche_totp(erste, u1, secret=secret, code=code) is True
        erste.commit()
        # u2 hat den alten Stand im Speicher, das bedingte UPDATE in der Datenbank fuehrt trotzdem zur Ablehnung.
        assert mfa_service.verbrauche_totp(zweite, u2, secret=secret, code=code) is False


def test_login_code_ist_nur_einmal_verwendbar(client: TestClient):
    secret, _, _ = _mfa_aktivieren(client)
    code = pyotp.TOTP(secret).now()
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": code}).status_code == 200
    erneut = client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": code})
    assert erneut.status_code == 400
    assert "falsch oder abgelaufen" in erneut.json()["detail"]
    assert "mfa_code_falsch" in _aktionen()  # zaehlt wie ein falscher Code
    # Ein frischer Code (naechster Zeitschritt) funktioniert weiterhin.
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": pyotp.TOTP(secret).now()}).status_code == 200


def test_code_aus_der_einrichtung_gilt_nicht_nochmal_zum_anmelden(client: TestClient):
    pre = _kopf(_registrieren(client)["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    code = pyotp.TOTP(secret).now()
    assert client.post("/auth/mfa/verify", headers=pre, json={"code": code}).status_code == 200
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": code}).status_code == 400


def test_mfa_verify_wiederholt_mit_demselben_code_wird_abgelehnt(client: TestClient):
    secret, _, _ = _mfa_aktivieren(client)
    code = pyotp.TOTP(secret).now()
    pre = _pre_login(client)
    assert client.post("/auth/mfa/verify", headers=pre, json={"code": code}).status_code == 200
    assert client.post("/auth/mfa/verify", headers=pre, json={"code": code}).status_code == 400


def test_deaktivieren_und_neu_einrichten_verbrauchen_den_code(client: TestClient):
    secret, token, _ = _mfa_aktivieren(client)
    kopf = _kopf(token)
    code = pyotp.TOTP(secret).now()
    start = client.post("/security/mfa/neu-einrichten", headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": code})
    assert start.status_code == 200
    # Derselbe Code ein zweites Mal (Deaktivieren oder erneut Neu-Einrichten): abgelehnt.
    for pfad in ("/security/mfa/deaktivieren", "/security/mfa/neu-einrichten"):
        antwort = client.post(pfad, headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": code})
        assert antwort.status_code == 400, pfad
    # Mit einem frischen Code geht es.
    frisch = pyotp.TOTP(secret).now()
    assert client.post("/security/mfa/deaktivieren", headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": frisch}).status_code == 204


def test_bestaetigter_code_der_neuen_einrichtung_ist_danach_verbraucht(client: TestClient):
    secret, token, _ = _mfa_aktivieren(client)
    kopf = _kopf(token)
    start = client.post(
        "/security/mfa/neu-einrichten", headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()},
    ).json()
    neu = pyotp.TOTP(start["secret"]).now()
    bestaetigt = client.post("/security/mfa/neu-einrichten/bestaetigen", headers=kopf, json={"code": neu})
    assert bestaetigt.status_code == 200
    assert bestaetigt.json()["wiederherstellungscodes"] is None  # keine erste Aktivierung: vorhandene Codes bleiben
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": neu}).status_code == 400
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": pyotp.TOTP(start["secret"]).now()}).status_code == 200


# ---------------------------------------------------------------------------
# Wiederherstellungscodes: Erzeugen


def test_ersteinrichtung_liefert_zehn_einmalcodes_und_speichert_nur_hashes(client: TestClient):
    _, token, codes = _mfa_aktivieren(client)
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(CODE_FORMAT.match(c) for c in codes)
    with SessionLocal() as db:
        zeilen = db.query(MfaWiederherstellungscode).all()
        assert len(zeilen) == 10
        gespeichert = " ".join(z.code_hash for z in zeilen)
    assert all(re.fullmatch(r"[0-9a-f]{64}", z) for z in gespeichert.split())
    assert not any(c.replace("-", "").lower() in gespeichert for c in codes)  # nirgends im Klartext
    assert "mfa_wiederherstellungscodes_erzeugt" in _aktionen()
    assert client.get("/security", headers=_kopf(token)).json()["wiederherstellungscodes_offen"] == 10


def test_codes_gibt_es_nur_einmal_nicht_beim_login_und_nicht_bei_wiederholtem_verify(client: TestClient):
    secret, _, codes = _mfa_aktivieren(client)
    antwort = client.post("/auth/mfa/verify", headers=_pre_login(client), json={"code": pyotp.TOTP(secret).now()})
    assert antwort.status_code == 200 and antwort.json()["wiederherstellungscodes"] is None
    login = client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": pyotp.TOTP(secret).now()})
    assert "wiederherstellungscodes" not in login.json()
    assert _offene_codes() == 10  # unveraendert, nichts neu erzeugt


def test_aktivierung_aus_laufender_sitzung_liefert_ebenfalls_codes(client: TestClient):
    data = _registrieren(client)
    kopf = _kopf(data["access_token"])
    start = client.post("/security/mfa/einrichten", headers=kopf).json()
    antwort = client.post("/security/mfa/neu-einrichten/bestaetigen", headers=kopf, json={"code": pyotp.TOTP(start["secret"]).now()})
    assert antwort.status_code == 200 and len(antwort.json()["wiederherstellungscodes"]) == 10
    assert _offene_codes() == 10


# ---------------------------------------------------------------------------
# Wiederherstellungscodes: Anmelden


def test_anmelden_mit_wiederherstellungscode_verbraucht_ihn(client: TestClient):
    _, _, codes = _mfa_aktivieren(client)
    antwort = client.post("/auth/login/mfa/wiederherstellungscode", headers=_pre_login(client), json={"wiederherstellungscode": codes[0]})
    assert antwort.status_code == 200
    token = antwort.json()["access_token"]
    assert client.get("/auth/me", headers=_kopf(token)).status_code == 200
    assert client.get("/security", headers=_kopf(token)).json()["wiederherstellungscodes_offen"] == 9
    # Zweite Verwendung desselben Codes scheitert, die anderen gelten weiter.
    erneut = client.post("/auth/login/mfa/wiederherstellungscode", headers=_pre_login(client), json={"wiederherstellungscode": codes[0]})
    assert erneut.status_code == 400
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=_pre_login(client), json={"wiederherstellungscode": codes[1]}).status_code == 200
    aktionen = _aktionen()
    assert aktionen.count("mfa_wiederherstellungscode_verwendet") == 2
    assert "mfa_wiederherstellungscode_falsch" in aktionen


def test_eingabe_ist_tolerant_bei_schreibweise(client: TestClient):
    _, _, codes = _mfa_aktivieren(client)
    locker = " " + codes[2].replace("-", "").lower() + " "
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=_pre_login(client), json={"wiederherstellungscode": locker}).status_code == 200


def test_wiederherstellungscode_ist_kontogebunden(client: TestClient):
    _, _, codes = _mfa_aktivieren(client)
    zweiter = client.post("/auth/register", json={"email": "zwei@example.com", "password": PW, "firmenname": "Zwei GmbH"}).json()
    pre = _kopf(zweiter["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()})
    login = client.post("/auth/login", json={"email": "zwei@example.com", "password": PW}).json()
    antwort = client.post(
        "/auth/login/mfa/wiederherstellungscode", headers=_kopf(login["pre_auth_token"]), json={"wiederherstellungscode": codes[0]},
    )
    assert antwort.status_code == 400


def test_falsche_wiederherstellungscodes_zaehlen_im_gemeinsamen_bruteforce_zaehler(client: TestClient):
    secret, _, codes = _mfa_aktivieren(client)
    pre = _pre_login(client)
    falsch = "AAAAA-AAAAA"
    for _ in range(3):
        assert client.post("/auth/login/mfa/wiederherstellungscode", headers=pre, json={"wiederherstellungscode": falsch}).status_code == 400
    # Ein falscher TOTP-Code teilt sich den Zaehler mit den Wiederherstellungscodes ...
    assert client.post("/auth/login/mfa", headers=pre, json={"code": "000000"}).status_code == 400
    # ... der fuenfte Fehlversuch sperrt das Konto (429), danach hilft auch der richtige Wiederherstellungscode nicht.
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=pre, json={"wiederherstellungscode": falsch}).status_code == 429
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=pre, json={"wiederherstellungscode": codes[0]}).status_code == 429
    assert "konto_gesperrt" in _aktionen()
    assert _offene_codes() == 10


def test_wiederherstellungscode_login_braucht_pre_mfa_token(client: TestClient):
    _, token, codes = _mfa_aktivieren(client)
    pfad = "/auth/login/mfa/wiederherstellungscode"
    assert client.post(pfad, json={"wiederherstellungscode": codes[0]}).status_code == 401
    assert client.post(pfad, headers=_kopf(token), json={"wiederherstellungscode": codes[0]}).status_code == 403


# ---------------------------------------------------------------------------
# Wiederherstellungscodes: Neu erzeugen, Deaktivieren


def test_neu_erzeugen_entwertet_alle_alten_codes(client: TestClient):
    secret, token, alt = _mfa_aktivieren(client)
    kopf = _kopf(token)
    # Passwort UND aktueller Code sind Pflicht.
    pfad = "/security/mfa/wiederherstellungscodes/neu"
    falsches_pw = client.post(pfad, headers=kopf, json={"aktuelles_passwort": "falsch falsch falsch", "aktueller_code": pyotp.TOTP(secret).now()})
    assert falsches_pw.status_code == 400
    falscher_code = client.post(pfad, headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": "000000"})
    assert falscher_code.status_code == 400
    assert _offene_codes() == 10 and client.get("/security", headers=kopf).json()["wiederherstellungscodes_offen"] == 10

    code = pyotp.TOTP(secret).now()
    neu = client.post(pfad, headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": code})
    assert neu.status_code == 200
    neue_codes = neu.json()["wiederherstellungscodes"]
    assert len(neue_codes) == 10 and not set(neue_codes) & set(alt)
    assert _offene_codes() == 10
    # Replay: derselbe TOTP-Code ist verbraucht.
    assert client.post(pfad, headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": code}).status_code == 400
    # Alte Codes sind wertlos, neue funktionieren.
    pre = _pre_login(client)
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=pre, json={"wiederherstellungscode": alt[0]}).status_code == 400
    assert client.post("/auth/login/mfa/wiederherstellungscode", headers=pre, json={"wiederherstellungscode": neue_codes[0]}).status_code == 200
    assert "mfa_wiederherstellungscodes_erneuert" in _aktionen()


def test_neu_erzeugen_mit_wiederherstellungscode_als_aktuellem_code(client: TestClient):
    _, token, codes = _mfa_aktivieren(client)
    antwort = client.post(
        "/security/mfa/wiederherstellungscodes/neu", headers=_kopf(token),
        json={"aktuelles_passwort": PW, "aktueller_code": codes[0]},
    )
    assert antwort.status_code == 200 and codes[0] not in antwort.json()["wiederherstellungscodes"]


def test_neu_erzeugen_braucht_aktives_mfa_und_anmeldung(client: TestClient):
    data = _registrieren(client)
    pfad = "/security/mfa/wiederherstellungscodes/neu"
    body = {"aktuelles_passwort": PW, "aktueller_code": "123456"}
    assert client.post(pfad, headers=_kopf(data["access_token"]), json=body).status_code == 400  # MFA aus
    assert client.post(pfad, json=body).status_code == 401
    assert client.post(pfad, headers=_kopf(data["pre_auth_token"]), json=body).status_code == 403


def test_geraet_verloren_mit_wiederherstellungscode_anmelden_und_mfa_neu_einrichten(client: TestClient):
    _, _, codes = _mfa_aktivieren(client)
    token = client.post(
        "/auth/login/mfa/wiederherstellungscode", headers=_pre_login(client), json={"wiederherstellungscode": codes[0]},
    ).json()["access_token"]
    kopf = _kopf(token)
    # Das alte Geraet fehlt: Neu-Einrichten mit Passwort + (weiterem) Wiederherstellungscode.
    start = client.post("/security/mfa/neu-einrichten", headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": codes[1]})
    assert start.status_code == 200
    neu = start.json()["secret"]
    assert client.post("/security/mfa/neu-einrichten/bestaetigen", headers=kopf, json={"code": pyotp.TOTP(neu).now()}).status_code == 200
    assert client.post("/auth/login/mfa", headers=_pre_login(client), json={"code": pyotp.TOTP(neu).now()}).status_code == 200
    assert _offene_codes() == 8  # zwei verbraucht, die uebrigen bleiben


def test_deaktivieren_loescht_codes_und_neue_aktivierung_erzeugt_frische(client: TestClient):
    secret, token, alt = _mfa_aktivieren(client)
    antwort = client.post(
        "/security/mfa/deaktivieren", headers=_kopf(token), json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()},
    )
    assert antwort.status_code == 204
    assert _offene_codes() == 0
    with SessionLocal() as db:
        assert db.query(User).one().mfa_letzter_zeitschritt is None
    neu_token = client.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    start = client.post("/security/mfa/einrichten", headers=_kopf(neu_token)).json()
    bestaetigt = client.post("/security/mfa/neu-einrichten/bestaetigen", headers=_kopf(neu_token), json={"code": pyotp.TOTP(start["secret"]).now()})
    assert bestaetigt.status_code == 200
    assert not set(bestaetigt.json()["wiederherstellungscodes"]) & set(alt)


def test_datenexport_enthaelt_kein_sicherheitsmaterial_der_neuen_felder(client: TestClient):
    _, token, codes = _mfa_aktivieren(client)
    export = client.get("/auth/datenexport", headers=_kopf(token))
    assert export.status_code == 200
    assert "mfa_letzter_zeitschritt" not in export.text
    assert all(c not in export.text for c in codes)
