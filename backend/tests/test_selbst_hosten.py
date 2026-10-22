"""Selbst-Hosting: konfigurierbarer Speicher mit Startpruefung, optionales SMTP, Registrierungsmodi und der
Wiederherstellungsweg fuer Betreiber (scripts/konto_wiederherstellen.py).

Nichts davon spricht ein echtes Netzwerk an; SMTP ist ueberall eine Attrappe oder abgeschaltet.
"""
import os
import shutil
import stat
from datetime import datetime, timezone
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth.models import AuthSession, User
from app.config import Settings, settings
from app.core import mailer, storage_check
from app.core.audit_log import AuditLogEintrag
from app.core.security import verify_password
from app.db import SessionLocal
from scripts import konto_wiederherstellen
from tests.test_invoices import _kontakt, _onboarded_mandant
from tests.test_versand import _finalized_invoice, _set_kontakt_email

PW = "correct horse battery staple"


# ---------------------------------------------------------------------------
# Speicher: Basisordner, Ableitung der Unterordner
# ---------------------------------------------------------------------------

def test_unterordner_leiten_sich_aus_storage_dir_ab(tmp_path):
    s = Settings(storage_dir=str(tmp_path / "bq"))
    basis = str(tmp_path / "bq")
    assert s.receipt_storage_dir == f"{basis}/receipts"
    assert s.branding_storage_dir == f"{basis}/branding"
    assert s.letterhead_storage_dir == f"{basis}/briefpapier"
    assert s.bank_storage_dir == f"{basis}/bank"
    assert s.altrechnung_storage_dir == f"{basis}/altrechnungen"


def test_einzelner_unterordner_laesst_sich_ueberschreiben(tmp_path):
    s = Settings(storage_dir=str(tmp_path / "bq"), bank_storage_dir=str(tmp_path / "anderes-laufwerk"))
    assert s.bank_storage_dir == str(tmp_path / "anderes-laufwerk")
    assert s.receipt_storage_dir == f"{tmp_path / 'bq'}/receipts"


def test_standard_ist_relativ_zum_arbeitsverzeichnis():
    s = Settings(storage_dir="./data")
    assert s.receipt_storage_dir == "./data/receipts"
    assert Settings(storage_dir="/").receipt_storage_dir == "/receipts"


# ---------------------------------------------------------------------------
# Speicher: Startpruefung
# ---------------------------------------------------------------------------

@pytest.fixture
def speicher(tmp_path, monkeypatch):
    """Leitet alle sechs Speicherpfade auf einen frischen Ordner um."""
    basis = tmp_path / "daten"
    monkeypatch.setattr(settings, "storage_dir", str(basis))
    for feld, name in (("receipt_storage_dir", "receipts"), ("branding_storage_dir", "branding"),
                       ("letterhead_storage_dir", "briefpapier"), ("bank_storage_dir", "bank"),
                       ("altrechnung_storage_dir", "altrechnungen")):
        monkeypatch.setattr(settings, feld, str(basis / name))
    return basis


def test_pruefung_legt_fehlende_ordner_mit_0700_an(speicher):
    ergebnis = storage_check.pruefe_speicher()
    assert len(ergebnis.ordner) == 6
    for ordner in [speicher, *(speicher / n for n in ("receipts", "branding", "briefpapier", "bank", "altrechnungen"))]:
        assert ordner.is_dir()
        assert stat.S_IMODE(ordner.stat().st_mode) == 0o700
    assert list(speicher.glob(".schreibtest-*")) == []  # Probedatei wieder entfernt


def test_pruefung_zieht_zu_weite_rechte_auf_0700_zurueck(speicher):
    (speicher / "receipts").mkdir(parents=True)
    os.chmod(speicher / "receipts", 0o755)
    storage_check.pruefe_speicher()
    assert stat.S_IMODE((speicher / "receipts").stat().st_mode) == 0o700


def test_pruefung_ist_idempotent_und_laesst_vorhandene_dateien_in_ruhe(speicher):
    storage_check.pruefe_speicher()
    datei = speicher / "receipts" / "mandant" / "beleg.pdf"
    datei.parent.mkdir()
    datei.write_bytes(b"inhalt")
    storage_check.pruefe_speicher()
    assert datei.read_bytes() == b"inhalt"


def test_pfad_ist_eine_datei_gibt_lesbare_meldung(speicher):
    speicher.parent.mkdir(parents=True, exist_ok=True)
    speicher.write_text("ich bin eine Datei")
    with pytest.raises(storage_check.SpeicherFehler) as exc:
        storage_check.pruefe_speicher()
    meldung = str(exc.value)
    assert "kein Ordner" in meldung
    assert "docs/self-hosting.md" in meldung


def test_ordner_unter_einer_datei_kann_nicht_angelegt_werden(tmp_path, monkeypatch):
    datei = tmp_path / "datei"
    datei.write_text("x")
    monkeypatch.setattr(storage_check, "speicherordner", lambda: [("Belege", str(datei / "unterordner"))])
    with pytest.raises(storage_check.SpeicherFehler) as exc:
        storage_check.pruefe_speicher()
    assert "Belege" in str(exc.value)
    assert "Traceback" not in str(exc.value)


@pytest.mark.skipif(os.geteuid() == 0, reason="root darf auch in 0500-Ordner schreiben")
def test_nicht_beschreibbarer_ordner_wird_gemeldet(speicher):
    speicher.mkdir(parents=True)
    os.chmod(speicher, 0o500)
    try:
        with pytest.raises(storage_check.SpeicherFehler) as exc:
            storage_check.pruefe_speicher()
        assert "nicht geschrieben werden" in str(exc.value)
    finally:
        os.chmod(speicher, 0o700)


def test_alle_probleme_werden_gesammelt(tmp_path, monkeypatch):
    datei = tmp_path / "datei"
    datei.write_text("x")
    monkeypatch.setattr(storage_check, "speicherordner", lambda: [("A", str(datei)), ("B", str(datei / "b"))])
    with pytest.raises(storage_check.SpeicherFehler) as exc:
        storage_check.pruefe_speicher()
    assert "A:" in str(exc.value) and "B:" in str(exc.value)


def test_kommando_liefert_exit_code_ohne_stacktrace(speicher, capsys):
    assert storage_check.main() == 0
    assert "in Ordnung" in capsys.readouterr().out

    shutil.rmtree(speicher)  # Ordner existiert jetzt; eine Datei an seine Stelle setzen
    speicher.write_text("x")
    assert storage_check.main() == 1
    fehler = capsys.readouterr().err
    assert fehler.startswith("FEHLER:")
    assert "Traceback" not in fehler


def test_app_startet_nicht_mit_kaputtem_speicher_und_nennt_den_grund(tmp_path, monkeypatch, caplog):
    from app.main import app

    datei = tmp_path / "datei"
    datei.write_text("x")
    monkeypatch.setattr(storage_check, "speicherordner", lambda: [("Belege", str(datei / "x"))])
    # Andere Tests (Alembic-Läufe) können vorhandene Logger per fileConfig abschalten;
    # der Test hängt deshalb nicht von der Logger-Konfiguration anderer Tests ab.
    import logging

    main_logger = logging.getLogger("app.main")
    monkeypatch.setattr(main_logger, "disabled", False)
    monkeypatch.setattr(main_logger, "propagate", True)
    with caplog.at_level("CRITICAL", logger="app.main"):
        with pytest.raises(storage_check.SpeicherFehler) as info:
            with TestClient(app):
                pass
    assert "Dateispeicher ist nicht benutzbar" in str(info.value)
    assert "Dateispeicher ist nicht benutzbar" in caplog.text


def test_app_startet_mit_funktionierendem_speicher(speicher):
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert (speicher / "receipts").is_dir()


def test_beleg_landet_unter_storage_dir_und_traversal_bleibt_blockiert(speicher):
    from app.core.secure_storage import read_encrypted, write_encrypted

    storage_check.pruefe_speicher()
    write_encrypted(settings.receipt_storage_dir, "m1/a.pdf", b"daten", purpose_prefix="receipt-file")
    assert (speicher / "receipts" / "m1" / "a.pdf").is_file()
    assert stat.S_IMODE((speicher / "receipts" / "m1" / "a.pdf").stat().st_mode) == 0o600
    assert read_encrypted(settings.receipt_storage_dir, "m1/a.pdf", purpose_prefix="receipt-file") == b"daten"
    for boese in ("../../etc/passwd", "m1/../../außerhalb.pdf", "/etc/passwd"):
        with pytest.raises(ValueError):
            write_encrypted(settings.receipt_storage_dir, boese, b"x", purpose_prefix="receipt-file")
        with pytest.raises(ValueError):
            read_encrypted(settings.receipt_storage_dir, boese, purpose_prefix="receipt-file")


@pytest.mark.parametrize("feld", ["jwt_secret", "email_lookup_secret", "blind_index_secret", "field_encryption_key"])
def test_platzhalter_aus_der_env_vorlage_werden_abgelehnt(feld):
    with pytest.raises(ValueError, match="Platzhalter"):
        Settings(**{feld: "generate-with-openssl-rand-hex-32"})
    with pytest.raises(ValueError, match="Platzhalter"):
        Settings(**{feld: "SET_ME"})


def test_platzhalter_im_schluesselring_wird_abgelehnt():
    with pytest.raises(ValueError, match="DATA_ENCRYPTION_KEYS"):
        Settings(data_encryption_keys="v1:generate-with-python-secrets-base64")


# ---------------------------------------------------------------------------
# SMTP optional
# ---------------------------------------------------------------------------

def test_app_laesst_sich_ohne_smtp_konfigurieren():
    s = Settings(smtp_host=None, smtp_user=None, smtp_password=None, smtp_absender=None)
    assert s.email_aktiv is False
    assert s.absender_adresse is None


@pytest.mark.parametrize("wert", ["", "   ", "SET_ME"])
def test_leere_werte_und_platzhalter_zaehlen_als_nicht_gesetzt(wert):
    s = Settings(smtp_host="mail.example.org", smtp_user="u@example.org", smtp_password=wert)
    assert s.smtp_password is None
    assert s.email_aktiv is False


def test_absender_faellt_auf_smtp_user_zurueck_aber_nie_auf_eine_fremde_domain():
    mit_adresse = Settings(smtp_host="h", smtp_user="konto@example.org", smtp_password="p", smtp_absender=None)
    assert mit_adresse.absender_adresse == "konto@example.org" and mit_adresse.email_aktiv
    ohne_adresse = Settings(smtp_host="h", smtp_user="benutzername", smtp_password="p", smtp_absender=None)
    assert ohne_adresse.absender_adresse is None and not ohne_adresse.email_aktiv
    ausdruecklich = Settings(smtp_host="h", smtp_user="benutzername", smtp_password="p", smtp_absender="rechnung@example.org")
    assert ausdruecklich.absender_adresse == "rechnung@example.org"


@pytest.fixture
def ohne_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_password", None)


def test_mailer_verbindet_sich_ohne_smtp_nie_und_wirft_klaren_fehler(ohne_smtp):
    with patch("app.core.mailer.smtplib.SMTP") as smtp:
        with pytest.raises(mailer.EmailNichtEingerichtet) as exc:
            mailer.sende_text_email("a@example.org", "Betreff", "Text")
        with pytest.raises(mailer.EmailNichtEingerichtet):
            mailer.sende_email("a@example.org", "B", "T", b"%PDF", "a.pdf", "Firma")
    smtp.assert_not_called()
    assert "nicht eingerichtet" in str(exc.value)


def test_rechnung_versenden_meldet_503_statt_still_zu_scheitern(client: TestClient, monkeypatch):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)
    monkeypatch.setattr(settings, "smtp_host", None)

    with patch("app.core.mailer.smtplib.SMTP") as smtp:
        antwort = client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={})
    assert antwort.status_code == 503
    assert "nicht eingerichtet" in antwort.json()["detail"]
    smtp.assert_not_called()
    # Nichts wurde als versendet verbucht.
    assert client.get(f"/invoices/{invoice['id']}", headers=headers).json()["versendet_am"] is None
    # Das PDF laesst sich weiterhin herunterladen (die Meldung verweist darauf).
    assert client.get(f"/invoices/{invoice['id']}/pdf", headers=headers).status_code == 200


def test_passwort_vergessen_ohne_smtp_sagt_ehrlich_dass_es_nicht_geht(client: TestClient, ohne_smtp):
    client.post("/auth/register", json={"email": "owner@example.org", "password": PW, "firmenname": "Test GmbH"})
    bekannt = client.post("/auth/passwort/vergessen", json={"email": "owner@example.org"})
    unbekannt = client.post("/auth/passwort/vergessen", json={"email": "niemand@example.org"})
    # Gleiche Antwort fuer bekannte und unbekannte Adressen: keine Konto-Enumeration.
    assert bekannt.status_code == unbekannt.status_code == 503
    assert bekannt.json() == unbekannt.json()
    assert "nicht möglich" in bekannt.json()["detail"]
    assert "self-hosting" in bekannt.json()["detail"]


def test_email_aenderung_ohne_smtp_meldet_503(client: TestClient, ohne_smtp):
    headers = _onboarded_mandant(client)
    antwort = client.post(
        "/security/email/aenderung-starten", headers=headers,
        json={"neues_email": "neu@example.org", "aktuelles_passwort": PW},
    )
    assert antwort.status_code == 503
    assert "nicht eingerichtet" in antwort.json()["detail"]


def test_registrierung_und_anmeldung_funktionieren_ohne_smtp(client: TestClient, ohne_smtp):
    registrierung = client.post("/auth/register", json={"email": "owner@example.org", "password": PW, "firmenname": "Test GmbH"})
    assert registrierung.status_code == 201
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": PW})
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# Registrierungsmodi
# ---------------------------------------------------------------------------

def test_standardmodus_ist_first_account(monkeypatch):
    monkeypatch.delenv("REGISTRATION_MODE")  # conftest setzt "open" fuer die uebrigen Tests
    assert Settings().registration_mode == "first_account"


def test_unbekannter_modus_wird_abgelehnt():
    with pytest.raises(ValueError):
        Settings(registration_mode="alle")


def test_open_erlaubt_beliebig_viele_firmen(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "open")
    for i in range(3):
        antwort = client.post("/auth/register", json={"email": f"p{i}@example.org", "password": PW, "firmenname": f"F{i}"})
        assert antwort.status_code == 201


def test_first_account_erlaubt_nur_das_erste_konto(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "first_account")
    erstes = client.post("/auth/register", json={"email": "erste@example.org", "password": PW, "firmenname": "Erste GmbH"})
    assert erstes.status_code == 201
    zweites = client.post("/auth/register", json={"email": "zweite@example.org", "password": PW, "firmenname": "Zweite GmbH"})
    assert zweites.status_code == 403
    assert "geschlossen" in zweites.json()["detail"]
    with SessionLocal() as db:
        assert db.query(User).count() == 1


def _owner_mit_einladungscode(client: TestClient) -> tuple[dict, str]:
    """Legt (im Modus open) einen Inhaber an und erzeugt einen Einladungscode."""
    antwort = client.post("/auth/register", json={"email": "owner@example.org", "password": PW, "firmenname": "Test GmbH"})
    owner = {"Authorization": f"Bearer {antwort.json()['access_token']}"}
    antwort = client.post("/auth/einladungen", headers=owner, json={"rolle": "mitglied"})
    assert antwort.status_code == 201, antwort.text
    return owner, antwort.json()["code"]


def test_first_account_erlaubt_beitritt_per_einladungscode(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "open")
    owner, code = _owner_mit_einladungscode(client)
    monkeypatch.setattr(settings, "registration_mode", "first_account")
    ohne_code = client.post("/auth/register", json={"email": "fremd@example.org", "password": PW, "firmenname": "Fremd"})
    assert ohne_code.status_code == 403
    falscher_code = client.post("/auth/register", json={"email": "fremd@example.org", "password": PW, "einladungscode": "FALSCHFALSCH"})
    assert falscher_code.status_code == 400
    mit_code = client.post("/auth/register", json={"email": "kollegin@example.org", "password": PW, "einladungscode": code})
    assert mit_code.status_code == 201
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {mit_code.json()['access_token']}"}).json()
    assert me["rolle"] == "mitglied"


def test_geloeschtes_erstkonto_oeffnet_die_registrierung_nicht_wieder(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "first_account")
    client.post("/auth/register", json={"email": "erste@example.org", "password": PW, "firmenname": "Erste GmbH"})
    with SessionLocal() as db:
        db.query(User).update({User.geloescht_am: datetime.now(timezone.utc)})
        db.commit()
    antwort = client.post("/auth/register", json={"email": "neu@example.org", "password": PW, "firmenname": "Neu GmbH"})
    assert antwort.status_code == 403


def test_closed_sperrt_jede_selbstregistrierung_auch_mit_code(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "registration_mode", "open")
    owner, code = _owner_mit_einladungscode(client)
    monkeypatch.setattr(settings, "registration_mode", "closed")
    assert client.post("/auth/register", json={"email": "a@example.org", "password": PW, "firmenname": "A"}).status_code == 403
    assert client.post("/auth/register", json={"email": "b@example.org", "password": PW, "einladungscode": code}).status_code == 403
    # Der Inhaber legt Mitglieder weiterhin direkt an.
    direkt = client.post("/auth/mitglieder", headers=owner, json={"email": "c@example.org", "rolle": "mitglied"})
    assert direkt.status_code == 201


# ---------------------------------------------------------------------------
# Wiederherstellungsweg fuer Betreiber
# ---------------------------------------------------------------------------

def _konto(client: TestClient, email="owner@example.org", mfa=False) -> dict:
    reg = client.post("/auth/register", json={"email": email, "password": PW, "firmenname": "Test GmbH"}).json()
    kopf = {"Authorization": f"Bearer {reg['pre_auth_token']}"}
    if mfa:
        secret = client.post("/auth/mfa/setup", headers=kopf).json()["secret"]
        client.post("/auth/mfa/verify", headers=kopf, json={"code": pyotp.TOTP(secret).now()})
    return reg


def test_wiederherstellung_setzt_passwort_widerruft_sitzungen_und_protokolliert(client: TestClient):
    reg = _konto(client)
    alter_token = {"Authorization": f"Bearer {reg['access_token']}"}
    assert client.get("/auth/me", headers=alter_token).status_code == 200
    with SessionLocal() as db:
        user = db.query(User).one()
        user.failed_login_count = 5  # gesperrtes Konto
        db.commit()
        meldung = konto_wiederherstellen.wiederherstellen(db, email="OWNER@example.org", neues_passwort="ein ganz neues passwort 2026")
    assert "Passwort gesetzt" in meldung

    assert client.get("/auth/me", headers=alter_token).status_code == 401
    assert client.post("/auth/login", json={"email": "owner@example.org", "password": PW}).status_code == 401
    assert client.post("/auth/login", json={"email": "owner@example.org", "password": "ein ganz neues passwort 2026"}).status_code == 200
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.failed_login_count == 0 and user.locked_until is None
        assert verify_password("ein ganz neues passwort 2026", user.passwort_hash)
        eintrag = db.query(AuditLogEintrag).filter(AuditLogEintrag.aktion == "konto_wiederhergestellt_betreiber").one()
        assert eintrag.user_id == user.id
        assert "ein ganz neues passwort" not in (eintrag.kontext or "")
        assert db.query(AuthSession).filter(AuthSession.widerrufen_am.is_(None)).count() == 1  # nur die neue Anmeldung


def test_wiederherstellung_laesst_mfa_standardmaessig_aktiv_und_schaltet_sie_auf_wunsch_ab(client: TestClient):
    _konto(client, mfa=True)
    with SessionLocal() as db:
        konto_wiederherstellen.wiederherstellen(db, email="owner@example.org", neues_passwort="ein ganz neues passwort 2026")
        assert db.query(User).one().mfa_enabled is True
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": "ein ganz neues passwort 2026"})
    assert login.json()["status"] == "mfa_required"

    with SessionLocal() as db:
        konto_wiederherstellen.wiederherstellen(
            db, email="owner@example.org", neues_passwort="noch ein neues passwort 2026", mfa_zuruecksetzen=True,
        )
        user = db.query(User).one()
        assert user.mfa_enabled is False and user.mfa_secret_encrypted is None
    login = client.post("/auth/login", json={"email": "owner@example.org", "password": "noch ein neues passwort 2026"})
    assert login.json()["status"] == "mfa_optional"


def test_wiederherstellung_lehnt_unbekannte_konten_und_kurze_passwoerter_ab(client: TestClient):
    _konto(client)
    with SessionLocal() as db:
        with pytest.raises(konto_wiederherstellen.WiederherstellungsFehler, match="kein aktives Konto"):
            konto_wiederherstellen.wiederherstellen(db, email="niemand@example.org", neues_passwort="ein ganz neues passwort 2026")
        with pytest.raises(konto_wiederherstellen.WiederherstellungsFehler, match="Zeichen"):
            konto_wiederherstellen.wiederherstellen(db, email="owner@example.org", neues_passwort="kurz")
        assert verify_password(PW, db.query(User).one().passwort_hash)  # unveraendert


def test_kommando_zufallspasswort_und_kontenliste(client: TestClient, capsys):
    _konto(client)
    assert konto_wiederherstellen.main(["--konten-auflisten"]) == 0
    assert "owner@example.org  (MFA aus)" in capsys.readouterr().out

    assert konto_wiederherstellen.main(["--email", "owner@example.org", "--zufallspasswort"]) == 0
    ausgabe = capsys.readouterr().out
    neu = ausgabe.rsplit(": ", 1)[1].strip()
    assert len(neu) >= 12
    assert client.post("/auth/login", json={"email": "owner@example.org", "password": neu}).status_code == 200

    assert konto_wiederherstellen.main(["--email", "unbekannt@example.org", "--zufallspasswort"]) == 1
    assert capsys.readouterr().err.startswith("FEHLER:")
