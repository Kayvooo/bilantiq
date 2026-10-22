from datetime import datetime, timezone
from io import BytesIO

import pyotp
from fastapi.testclient import TestClient
from PIL import Image

from app.auth.models import MfaWiederherstellungscode
from app.core.audit_log import AuditLogAppendOnlyError, AuditLogEintrag
from app.core.rls import assert_same_mandant, get_scoped_or_404, MandantMismatchError
from app.core.security import decode_access_token
from app.db import SessionLocal


def _logo_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (12, 12), color=(18, 61, 58)).save(buf, format="PNG")
    return buf.getvalue()


def _register(client: TestClient, email: str = "kevin@example.com", password: str = "correct horse battery staple") -> dict:
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password, "firmenname": "Kevin GmbH"},
    )
    assert resp.status_code == 201
    return resp.json()


def _complete_mfa_enrollment(client: TestClient, pre_auth_token: str) -> tuple[str, str]:
    """Runs mfa/setup + mfa/verify, returns (secret, full_access_token)."""
    headers = {"Authorization": f"Bearer {pre_auth_token}"}
    setup_resp = client.post("/auth/mfa/setup", headers=headers)
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]

    code = pyotp.TOTP(secret).now()
    verify_resp = client.post("/auth/mfa/verify", headers=headers, json={"code": code})
    assert verify_resp.status_code == 200
    return secret, verify_resp.json()["access_token"]


def test_register_meldet_ohne_mfa_direkt_an(client: TestClient):
    """MFA ist optional: nach der Registrierung gibt es sofort eine volle Sitzung."""
    data = _register(client)
    assert data["status"] == "mfa_optional"

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me_resp.status_code == 200

    # Das pre-auth-Token allein schaltet weiterhin nichts frei.
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {data['pre_auth_token']}"}).status_code == 403


def test_mfa_spaeter_aus_laufender_sitzung_einrichten(client: TestClient):
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    start = client.post("/security/mfa/einrichten", headers=headers)
    assert start.status_code == 200
    # Falscher Code aktiviert nichts.
    falsch = client.post("/security/mfa/neu-einrichten/bestaetigen", headers=headers, json={"code": "000000"})
    assert falsch.status_code == 400
    assert client.get("/security", headers=headers).json()["mfa_enabled"] is False

    code = pyotp.TOTP(start.json()["secret"]).now()
    bestaetigt = client.post("/security/mfa/neu-einrichten/bestaetigen", headers=headers, json={"code": code})
    assert bestaetigt.status_code == 200
    assert len(bestaetigt.json()["wiederherstellungscodes"]) == 10  # erste Aktivierung: Codes einmalig im Klartext

    # Danach gilt wieder die zweite Stufe, und eine erneute Ersteinrichtung ist gesperrt.
    login = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert login.json()["status"] == "mfa_required" and login.json()["access_token"] is None
    assert client.post("/security/mfa/einrichten", headers=headers).status_code in (400, 401)


def test_full_enrollment_then_me_works(client: TestClient):
    data = _register(client)
    _, access_token = _complete_mfa_enrollment(client, data["pre_auth_token"])

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["firmenname"] == "Kevin GmbH"
    assert body["rolle"] == "owner"


def test_mfa_setup_is_idempotent_before_verification(client: TestClient):
    """Regression: React StrictMode ruft Effekte im Dev-Modus doppelt auf, ebenso
    ein Seiten-Reload oder ein zweiter Tab. Ein zweiter setup-Aufruf darf den bereits
    angezeigten/gescannten Secret nicht durch einen neuen ersetzen, sonst wird jeder
    korrekt eingegebene Code aus der Authenticator-App abgelehnt."""
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['pre_auth_token']}"}

    erster = client.post("/auth/mfa/setup", headers=headers).json()
    zweiter = client.post("/auth/mfa/setup", headers=headers).json()
    assert erster["secret"] == zweiter["secret"]

    code = pyotp.TOTP(erster["secret"]).now()
    verify_resp = client.post("/auth/mfa/verify", headers=headers, json={"code": code})
    assert verify_resp.status_code == 200


def test_mfa_setup_rejects_once_enabled(client: TestClient):
    data = _register(client)
    _complete_mfa_enrollment(client, data["pre_auth_token"])

    # Nach erfolgreicher Aktivierung darf derselbe pre_auth_token (falls noch
    # gueltig) keinen erneuten Setup mehr ausloesen.
    resp = client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {data['pre_auth_token']}"})
    assert resp.status_code == 400


def test_mfa_deaktivieren_braucht_passwort_und_code(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}
    geheimnis = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert geheimnis.json()["status"] == "mfa_required"
    secret = None
    from app.auth.models import User
    from app.core.crypto import decrypt_field
    from app.db import SessionLocal
    with SessionLocal() as db:
        secret = decrypt_field(db.query(User).one().mfa_secret_encrypted)
    pw = "correct horse battery staple"
    code = pyotp.TOTP(secret).now()

    assert client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": "falsch falsch falsch", "aktueller_code": code}).status_code == 400
    assert client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": pw, "aktueller_code": "000000"}).status_code == 400
    assert client.get("/security", headers=headers).json()["mfa_enabled"] is True

    assert client.post("/security/mfa/deaktivieren", headers=headers, json={"aktuelles_passwort": pw, "aktueller_code": code}).status_code == 204
    # Alle Sitzungen sind widerrufen, der neue Login geht ohne zweiten Faktor.
    assert client.get("/auth/me", headers=headers).status_code == 401
    login = client.post("/auth/login", json={"email": "kevin@example.com", "password": pw}).json()
    assert login["status"] == "mfa_optional"
    assert client.post("/security/mfa/deaktivieren", headers={"Authorization": f"Bearer {login['access_token']}"},
                       json={"aktuelles_passwort": pw, "aktueller_code": code}).status_code == 400


def test_login_ohne_mfa_liefert_sitzung(client: TestClient):
    _register(client)
    resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "mfa_optional"
    token = resp.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_after_mfa_enrollment_requires_second_step(client: TestClient):
    data = _register(client)
    _complete_mfa_enrollment(client, data["pre_auth_token"])

    login_resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert login_resp.status_code == 200
    assert login_resp.json()["status"] == "mfa_required"

    # A pre-auth token alone (without the second MFA code step) must not grant full access.
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {login_resp.json()['pre_auth_token']}"})
    assert me_resp.status_code == 403


def _minutes_until_expiry(access_token: str) -> float:
    payload = decode_access_token(access_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return (expires_at - datetime.now(timezone.utc)).total_seconds() / 60


def test_mfa_verify_remember_device_issues_a_long_lived_token(client: TestClient):
    """"Dieses Geraet 30 Tage merken" bei der Erstenrichtung (MfaEnrollment.tsx)."""
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['pre_auth_token']}"}
    secret = client.post("/auth/mfa/setup", headers=headers).json()["secret"]
    code = pyotp.TOTP(secret).now()

    resp = client.post("/auth/mfa/verify", headers=headers, json={"code": code, "remember_device": True})
    assert resp.status_code == 200
    assert _minutes_until_expiry(resp.json()["access_token"]) > 60 * 24


def test_mfa_verify_without_remember_device_keeps_default_short_lifetime(client: TestClient):
    data = _register(client)
    headers = {"Authorization": f"Bearer {data['pre_auth_token']}"}
    secret = client.post("/auth/mfa/setup", headers=headers).json()["secret"]
    code = pyotp.TOTP(secret).now()

    resp = client.post("/auth/mfa/verify", headers=headers, json={"code": code})
    assert resp.status_code == 200
    assert _minutes_until_expiry(resp.json()["access_token"]) < 60


def test_login_mfa_remember_device_issues_a_long_lived_token(client: TestClient):
    """"Dieses Geraet 30 Tage merken" beim wiederkehrenden Login (MfaChallenge.tsx) --
    Regression fuer haeufiges Erzwungenes-Neuanmelden trotz aktivem MFA."""
    data = _register(client)
    secret, _ = _complete_mfa_enrollment(client, data["pre_auth_token"])

    login_resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    pre_auth_token = login_resp.json()["pre_auth_token"]
    code = pyotp.TOTP(secret).now()

    resp = client.post(
        "/auth/login/mfa", headers={"Authorization": f"Bearer {pre_auth_token}"}, json={"code": code, "remember_device": True},
    )
    assert resp.status_code == 200
    assert _minutes_until_expiry(resp.json()["access_token"]) > 60 * 24


def _session_minutes_until_expiry(access_token: str) -> float:
    from app.auth.models import AuthSession

    session_id = decode_access_token(access_token)["sid"]
    with SessionLocal() as db:
        session = db.get(AuthSession, session_id)
        expires_at = session.laeuft_ab_am
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (expires_at - datetime.now(timezone.utc)).total_seconds() / 60


def test_remember_device_verlaengert_auch_die_serverseitige_session(client: TestClient):
    """Regression: Ohne gleiche Laufzeit der AuthSession waere das 30-Tage-JWT nach
    access_token_minutes serverseitig ungueltig und die Neuanmeldung kaeme zurueck."""
    data = _register(client)
    secret, _ = _complete_mfa_enrollment(client, data["pre_auth_token"])

    def login(remember: bool) -> str:
        pre = client.post(
            "/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"},
        ).json()["pre_auth_token"]
        resp = client.post(
            "/auth/login/mfa",
            headers={"Authorization": f"Bearer {pre}"},
            json={"code": pyotp.TOTP(secret).now(), "remember_device": remember},
        )
        assert resp.status_code == 200
        return resp.json()["access_token"]

    remembered = login(True)
    assert _session_minutes_until_expiry(remembered) > 60 * 24 * 29
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {remembered}"}).status_code == 200

    short = login(False)
    assert _session_minutes_until_expiry(short) < 60


def test_wrong_password_gives_generic_error_and_locks_after_five_attempts(client: TestClient):
    _register(client)
    for _ in range(5):
        resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "wrong-password"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "E-Mail oder Passwort ist falsch."

    # Sixth attempt, even with the correct password, is locked out now.
    locked_resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert locked_resp.status_code == 401
    assert locked_resp.json()["detail"] == "E-Mail oder Passwort ist falsch."


def test_unknown_email_gives_same_generic_error_as_wrong_password(client: TestClient):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "E-Mail oder Passwort ist falsch."


def test_deletion_anonymizes_but_keeps_membership_and_audit_log(client: TestClient):
    data = _register(client)
    secret, access_token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {access_token}"}

    delete_resp = client.request(
        "DELETE", "/auth/me", headers=headers,
        json={"passwort": "correct horse battery staple", "mfa_code": pyotp.TOTP(secret).now()},
    )
    assert delete_resp.status_code == 204

    # The account can no longer log in ...
    login_resp = client.post("/auth/login", json={"email": "kevin@example.com", "password": "correct horse battery staple"})
    assert login_resp.status_code == 401

    # ... but the audit trail from before the deletion is still there, unmodified.
    with SessionLocal() as db:
        aktionen = [row.aktion for row in db.query(AuditLogEintrag).order_by(AuditLogEintrag.zeitpunkt).all()]
    assert "registrierung" in aktionen
    assert "mfa_aktiviert" in aktionen
    assert "loeschantrag" in aktionen

    # Wiederherstellungscode-Hashes des geloeschten Kontos bleiben nicht zurueck (gilt unter SQLite; unter Postgres
    # sieht diese Sitzung ohne Mandantenkontext ohnehin keine Zeilen).
    with SessionLocal() as db:
        assert db.query(MfaWiederherstellungscode).count() == 0


def test_audit_log_cannot_be_modified_or_deleted():
    with SessionLocal() as db:
        eintrag = AuditLogEintrag(aktion="test_aktion")
        db.add(eintrag)
        db.commit()

        eintrag.aktion = "veraendert"
        try:
            db.commit()
            assert False, "Aendern eines Audit-Log-Eintrags haette fehlschlagen muessen"
        except AuditLogAppendOnlyError:
            db.rollback()

        db.delete(eintrag)
        try:
            db.commit()
            assert False, "Loeschen eines Audit-Log-Eintrags haette fehlschlagen muessen"
        except AuditLogAppendOnlyError:
            db.rollback()


def test_mandant_scoping_helpers_reject_cross_mandant_access(client: TestClient):
    kevin = _register(client, email="kevin@example.com")
    _, kevin_token = _complete_mfa_enrollment(client, kevin["pre_auth_token"])
    kevin_mandant_id = client.get("/auth/me", headers={"Authorization": f"Bearer {kevin_token}"}).json()["mandant_id"]

    lea = _register(client, email="lea@example.com")
    _, lea_token = _complete_mfa_enrollment(client, lea["pre_auth_token"])
    lea_mandant_id = client.get("/auth/me", headers={"Authorization": f"Bearer {lea_token}"}).json()["mandant_id"]

    assert kevin_mandant_id != lea_mandant_id
    try:
        assert_same_mandant(lea_mandant_id, kevin_mandant_id)
        assert False, "unterschiedliche Mandanten haetten abgelehnt werden muessen"
    except MandantMismatchError:
        pass

    from app.auth.models import Mandant

    with SessionLocal() as db:
        try:
            get_scoped_or_404(db, Mandant, lea_mandant_id, mandant_id=kevin_mandant_id)
            assert False, "Zugriff auf fremden Mandanten haette 404 auesloesen muessen"
        except Exception as exc:
            assert exc.status_code == 404


def test_get_and_update_mandant_stammdaten(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/auth/mandant", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["firmenname"] == "Kevin GmbH"
    assert initial.json()["ust_id"] is None

    update = client.patch(
        "/auth/mandant",
        headers=headers,
        json={"ust_id": "DE123456789", "steuernummer": "12/345/67890", "adresse": "Musterstr. 1, 12345 Berlin"},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["ust_id"] == "DE123456789"
    assert body["steuernummer"] == "12/345/67890"
    assert body["adresse"] == "Musterstr. 1, 12345 Berlin"
    assert body["firmenname"] == "Kevin GmbH"  # unset fields stay unchanged

    reread = client.get("/auth/mandant", headers=headers)
    assert reread.json()["ust_id"] == "DE123456789"


def test_steuerberater_kontakt_ist_pflegbar_und_optional(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/auth/mandant", headers=headers).json()
    assert initial["steuerberater_name"] is None
    assert initial["steuerberater_email"] is None
    assert initial["steuerberater_telefon"] is None

    update = client.patch(
        "/auth/mandant", headers=headers,
        json={"steuerberater_name": "Kanzlei Mustermann", "steuerberater_email": "kanzlei@example.com", "steuerberater_telefon": "+49 30 1234567"},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["steuerberater_name"] == "Kanzlei Mustermann"
    assert body["steuerberater_email"] == "kanzlei@example.com"
    assert body["steuerberater_telefon"] == "+49 30 1234567"
    assert body["ust_id"] is None  # weiterhin unabhaengig von den Steuer-Stammdaten


def test_rechnungsvorlage_ist_pflegbar_und_validiert(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/auth/mandant", headers=headers).json()
    assert initial["rechnungsvorlage"] is None
    assert initial["akzentfarbe"] is None

    update = client.patch("/auth/mandant", headers=headers, json={"rechnungsvorlage": "modern", "akzentfarbe": "#FF00AA"})
    assert update.status_code == 200
    body = update.json()
    assert body["rechnungsvorlage"] == "modern"
    assert body["akzentfarbe"] == "#FF00AA"

    ungueltige_vorlage = client.patch("/auth/mandant", headers=headers, json={"rechnungsvorlage": "verspielt"})
    assert ungueltige_vorlage.status_code == 422

    ungueltige_farbe = client.patch("/auth/mandant", headers=headers, json={"akzentfarbe": "rot"})
    assert ungueltige_farbe.status_code == 422


def test_rechnungsvorlage_vorschau_gibt_pdf_zurueck_ohne_zu_speichern(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={"vorlage": "minimal", "akzentfarbe": "#112233"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"

    unveraendert = client.get("/auth/mandant", headers=headers).json()
    assert unveraendert["rechnungsvorlage"] is None
    assert unveraendert["akzentfarbe"] is None


def test_rechnungsvorlage_vorschau_get_existiert_nicht_mehr_und_iban_geht_per_body(client: TestClient):
    """IBAN/BIC/Fusszeile duerfen nicht als Query-Parameter (Zugriffslog) uebertragen werden."""
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/auth/mandant/rechnungsvorlage/vorschau?iban=DE89370400440532013000", headers=headers).status_code == 405
    ohne = client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={"zeige_girocode": True})
    mit = client.post(
        "/auth/mandant/rechnungsvorlage/vorschau", headers=headers,
        json={"zeige_girocode": True, "iban": "DE89370400440532013000", "bic": "COBADEFFXXX", "briefpapier_id": None},
    )
    assert mit.status_code == 200 and mit.content[:4] == b"%PDF"
    assert mit.content != ohne.content  # ungespeicherte IBAN erzeugt einen GiroCode
    assert client.get("/auth/mandant", headers=headers).json()["iban"] in (None, "")
    assert client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={"akzentfarbe": "rot"}).status_code == 422


def test_logo_upload_download_und_entfernen(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/auth/mandant", headers=headers).json()
    assert initial["hat_logo"] is False

    upload = client.post(
        "/auth/mandant/logo", headers=headers,
        files={"file": ("logo.png", _logo_png(), "image/png")},
    )
    assert upload.status_code == 200
    assert upload.json()["hat_logo"] is True

    download = client.get("/auth/mandant/logo", headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert download.content == _logo_png()

    delete = client.delete("/auth/mandant/logo", headers=headers)
    assert delete.status_code == 200
    assert delete.json()["hat_logo"] is False
    assert client.get("/auth/mandant/logo", headers=headers).status_code == 404


def test_logo_upload_lehnt_falschen_dateityp_ab(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/auth/mandant/logo", headers=headers,
        files={"file": ("logo.txt", b"kein bild", "text/plain")},
    )
    assert resp.status_code == 400


def test_fusszeile_text_ist_pflegbar_und_erscheint_im_pdf(client: TestClient):
    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}

    ohne_fusszeile = client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={}).content

    update = client.patch(
        "/auth/mandant", headers=headers,
        json={"fusszeile_text": "Bank Beispiel · IBAN DE00 0000 0000 0000 0000 00"},
    )
    assert update.status_code == 200
    assert update.json()["fusszeile_text"] == "Bank Beispiel · IBAN DE00 0000 0000 0000 0000 00"

    mit_fusszeile = client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={}).content
    assert ohne_fusszeile != mit_fusszeile

    client.post("/auth/mandant/logo", headers=headers, files={"file": ("logo.png", _logo_png(), "image/png")})
    mit_logo_und_fusszeile = client.post("/auth/mandant/rechnungsvorlage/vorschau", headers=headers, json={}).content
    assert mit_fusszeile != mit_logo_und_fusszeile


def test_get_mandant_requires_full_auth(client: TestClient):
    data = _register(client)
    resp = client.get("/auth/mandant", headers={"Authorization": f"Bearer {data['pre_auth_token']}"})
    assert resp.status_code == 403


def test_rechnungsvorschau_zeigt_datum_im_pdf_nicht_im_iso_format(client: TestClient):
    import shutil
    import subprocess
    from datetime import date

    import pytest

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext (poppler) nicht installiert")

    data = _register(client)
    _, token = _complete_mfa_enrollment(client, data["pre_auth_token"])
    headers = {"Authorization": f"Bearer {token}"}
    kontakt = client.post(
        "/kontakte", headers=headers,
        json={"name": "Beispiel Kunde GmbH", "strasse": "Kundenweg 2", "plz": "80331", "ort": "Muenchen", "land": "DE", "ist_geschaeftskunde": True},
    ).json()["id"]

    resp = client.post(
        "/invoices/vorschau", headers=headers,
        json={
            "kontakt_id": kontakt, "leistungsdatum": "2026-10-08", "faelligkeitsdatum": "2026-10-22", "waehrung": "EUR",
            "positionen": [{"beschreibung": "Beratung", "menge": "1", "einzelpreis": "100.00", "ust_satz": "19.00"}],
        },
    )
    assert resp.status_code == 200
    text = subprocess.run(["pdftotext", "-", "-"], input=resp.content, capture_output=True, check=True).stdout.decode()

    assert "08.10.2026" in text and "22.10.2026" in text
    assert "2026-10-08" not in text and "2026-10-22" not in text
    assert date(2026, 10, 8).isoformat() not in text
