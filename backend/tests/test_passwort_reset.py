"""Passwort vergessen / zuruecksetzen (app/auth/passwort_reset.py).

Der Mailversand ist in diesen Tests IMMER eine Attrappe (``mailer.sende_text_email`` bzw. ``smtplib.SMTP`` werden ersetzt):
Es wird nie ein echter SMTP-Server angesprochen, die Zustellung ist also nicht geprueft.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth import passwort_reset
from app.auth.models import AuthSession, PasswortResetToken, User
from app.config import settings
from app.core.audit_log import AuditLogEintrag
from app.db import SessionLocal

EMAIL = "kevin@example.com"
PW = "correct horse battery staple"
NEUES_PW = "ein ganz neues passwort 2026"
LINK = re.compile(r"https://app\.test\.invalid/#passwort-zuruecksetzen/([0-9a-f-]{36})\.([0-9a-f]{64})")


@pytest.fixture(autouse=True)
def _ohne_wartezeit(monkeypatch):
    monkeypatch.setattr(passwort_reset, "MIN_ANTWORTZEIT_SEKUNDEN", 0.0)


@pytest.fixture
def postfach():
    """Faengt gesendete Mails ab: Liste von (empfaenger, betreff, text)."""
    gesendet: list[tuple[str, str, str]] = []
    with patch("app.core.mailer.sende_text_email", side_effect=lambda e, b, t, *a, **k: gesendet.append((e, b, t))):
        yield gesendet


def _registrieren(client: TestClient, email: str = EMAIL) -> dict:
    antwort = client.post("/auth/register", json={"email": email, "password": PW, "firmenname": "Kevin GmbH"})
    assert antwort.status_code == 201
    return antwort.json()


def _kopf(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token_aus(postfach) -> str:
    treffer = LINK.search(postfach[-1][2])
    assert treffer, postfach[-1][2]
    return f"{treffer.group(1)}.{treffer.group(2)}"


def _anfordern(client: TestClient, email: str = EMAIL):
    return client.post("/auth/passwort/vergessen", json={"email": email})


def _aktionen() -> list[str]:
    with SessionLocal() as db:
        return [e.aktion for e in db.query(AuditLogEintrag).all()]


# ---------------------------------------------------------------------------
# Anfordern


def test_anfordern_antwortet_fuer_bekannte_und_unbekannte_adressen_identisch(client: TestClient, postfach):
    _registrieren(client)
    bekannt = _anfordern(client)
    unbekannt = _anfordern(client, "gibtsnicht@example.com")
    assert bekannt.status_code == unbekannt.status_code == 202
    assert bekannt.json() == unbekannt.json() == {"detail": passwort_reset.ANTWORT_TEXT}
    assert bekannt.headers.get("content-length") == unbekannt.headers.get("content-length")
    assert [m[0] for m in postfach] == [EMAIL]  # nur die bekannte Adresse bekommt eine Mail


def test_mail_enthaelt_link_mit_fragment_und_den_token_nur_als_hash_in_der_datenbank(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    empfaenger, betreff, text = postfach[0]
    assert empfaenger == EMAIL and "zurücksetzen" in betreff
    treffer = LINK.search(text)
    assert treffer
    user_id, geheimnis = treffer.groups()
    assert "?" not in treffer.group(0) and "/#" in treffer.group(0)  # Fragment: erreicht keinen Server und kein Zugriffslog
    assert len(geheimnis) == 64  # 256 Bit
    with SessionLocal() as db:
        zeile = db.query(PasswortResetToken).one()
        assert zeile.user_id == user_id == db.query(User).one().id
        assert zeile.token_hash != geheimnis and re.fullmatch(r"[0-9a-f]{64}", zeile.token_hash)
        assert geheimnis not in zeile.token_hash
        assert zeile.ablauf_am.replace(tzinfo=timezone.utc) - zeile.erstellt_am.replace(tzinfo=timezone.utc) == timedelta(minutes=60)
        assert zeile.verbraucht_am is None
    assert "passwort_reset_angefordert" in _aktionen()


def test_neue_anforderung_entwertet_den_aelteren_token(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    alt = _token_aus(postfach)
    _anfordern(client)
    neu = _token_aus(postfach)
    assert alt != neu
    assert client.post("/auth/passwort/zuruecksetzen", json={"token": alt, "neues_passwort": NEUES_PW}).status_code == 400
    assert client.post("/auth/passwort/zuruecksetzen", json={"token": neu, "neues_passwort": NEUES_PW}).status_code == 204


def test_geloeschtes_konto_und_fehlende_frontend_url_senden_nichts_und_antworten_gleich(client: TestClient, postfach, monkeypatch):
    _registrieren(client)
    monkeypatch.setattr(settings, "app_frontend_url", None)
    antwort = _anfordern(client)
    assert antwort.status_code == 202 and antwort.json() == {"detail": passwort_reset.ANTWORT_TEXT}
    assert postfach == []
    monkeypatch.setattr(settings, "app_frontend_url", "https://app.test.invalid")
    with SessionLocal() as db:  # wie nach der Anonymisierung (DELETE /auth/me): geloescht_am gesetzt
        db.query(User).one().geloescht_am = datetime.now(timezone.utc)
        db.commit()
    assert _anfordern(client).status_code == 202
    assert postfach == []


def test_fehlgeschlagener_mailversand_aendert_die_antwort_nicht_und_leakt_keinen_token(client: TestClient, caplog):
    # Alembics fileConfig (in test_migrations.py im selben Prozess aufgerufen) deaktiviert bestehende Logger.
    logging.getLogger("bilantiq.passwort_reset").disabled = False
    _registrieren(client)
    with patch("app.core.mailer.sende_text_email", side_effect=OSError("smtp down")), caplog.at_level(logging.INFO):
        antwort = _anfordern(client)
    assert antwort.status_code == 202 and antwort.json() == {"detail": passwort_reset.ANTWORT_TEXT}
    assert "OSError" in caplog.text
    with SessionLocal() as db:
        assert db.query(PasswortResetToken).count() == 1
    assert not re.search(r"[0-9a-f]{64}", caplog.text) and EMAIL not in caplog.text


def test_mail_geht_ueber_den_mailer_mit_starttls_gegen_eine_attrappe(client: TestClient):
    _registrieren(client)
    with patch("app.core.mailer.smtplib.SMTP") as smtp:
        assert _anfordern(client).status_code == 202
    server = smtp.return_value
    server.starttls.assert_called_once()
    nachricht = server.send_message.call_args[0][0]
    assert nachricht["To"] == EMAIL
    assert LINK.search(message_from_bytes(nachricht.as_bytes()).get_payload(decode=True).decode())


def test_limits_gelten_pro_konto_und_pro_ip_auch_fuer_unbekannte_adressen(client: TestClient, postfach):
    _registrieren(client)
    for adresse in (EMAIL, "gibtsnicht@example.com"):
        assert [_anfordern(client, adresse).status_code for _ in range(3)] == [202, 202, 202]
        sperre = _anfordern(client, adresse)  # 4. Anfrage in der Stunde: identisch fuer bekannte und unbekannte Adresse
        assert sperre.status_code == 429 and "Retry-After" in sperre.headers
    assert len(postfach) == 3
    # IP-Limit: 10 Anfragen je Stunde ueber alle Adressen (bisher 8 verbraucht, 2 Konto-Sperren zaehlen mit).
    from app.core import ratelimit

    ratelimit.zuruecksetzen()
    codes = [_anfordern(client, f"nutzer{i}@example.com").status_code for i in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_antwortzeit_wird_auf_mindestdauer_aufgefuellt(client: TestClient, postfach, monkeypatch):
    _registrieren(client)
    monkeypatch.setattr(passwort_reset, "MIN_ANTWORTZEIT_SEKUNDEN", 0.3)
    for adresse in (EMAIL, "gibtsnicht@example.com"):
        start = time.monotonic()
        assert _anfordern(client, adresse).status_code == 202
        assert time.monotonic() - start >= 0.3


def test_ungueltige_adresse_wird_abgelehnt(client: TestClient):
    assert _anfordern(client, "keine-mail").status_code == 422


# ---------------------------------------------------------------------------
# Zuruecksetzen


def _zuruecksetzen(client: TestClient, token: str, passwort: str = NEUES_PW):
    return client.post("/auth/passwort/zuruecksetzen", json={"token": token, "neues_passwort": passwort})


def test_zuruecksetzen_setzt_passwort_widerruft_sitzungen_und_benachrichtigt(client: TestClient, postfach):
    data = _registrieren(client)
    alter_zugang = _kopf(data["access_token"])
    assert client.get("/auth/me", headers=alter_zugang).status_code == 200
    _anfordern(client)
    antwort = _zuruecksetzen(client, _token_aus(postfach))
    assert antwort.status_code == 204

    assert client.get("/auth/me", headers=alter_zugang).status_code == 401  # alle Sitzungen widerrufen
    assert client.post("/auth/login", json={"email": EMAIL, "password": PW}).status_code == 401
    neu = client.post("/auth/login", json={"email": EMAIL, "password": NEUES_PW})
    assert neu.status_code == 200
    with SessionLocal() as db:
        # Die Sitzung aus der Registrierung ist widerrufen; nur die neue vom Login mit dem neuen Passwort ist offen.
        sitzungen = db.query(AuthSession).order_by(AuthSession.erstellt_am).all()
        assert [s.widerrufen_am is not None for s in sitzungen] == [True, False]
        zeile = db.query(PasswortResetToken).one()
        assert zeile.verbraucht_am is not None
        assert db.query(User).one().passwort_geaendert_am is not None
    # Zweite Mail: Benachrichtigung ueber die Aenderung, ohne Link.
    assert len(postfach) == 2 and postfach[1][0] == EMAIL
    assert "geändert" in postfach[1][1] and not LINK.search(postfach[1][2])
    aktionen = _aktionen()
    assert "passwort_zurueckgesetzt" in aktionen


def test_token_ist_einmalig(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    token = _token_aus(postfach)
    assert _zuruecksetzen(client, token).status_code == 204
    zweiter = _zuruecksetzen(client, token, "noch ein anderes passwort 77")
    assert zweiter.status_code == 400 and zweiter.json()["detail"] == passwort_reset.UNGUELTIGER_LINK
    assert client.post("/auth/login", json={"email": EMAIL, "password": NEUES_PW}).status_code == 200
    assert "passwort_reset_abgelehnt" in _aktionen()


def test_abgelaufener_token_wird_abgelehnt(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    token = _token_aus(postfach)
    with SessionLocal() as db:
        zeile = db.query(PasswortResetToken).one()
        zeile.ablauf_am = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert _zuruecksetzen(client, token).status_code == 400
    assert client.post("/auth/login", json={"email": EMAIL, "password": PW}).status_code == 200  # Passwort unveraendert


def test_falsche_und_kaputte_token_werden_abgelehnt(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    token = _token_aus(postfach)
    user_id, geheimnis = token.split(".")
    falsch = [
        f"{user_id}.{'0' * 64}",                       # richtiger Nutzer, falsches Geheimnis
        f"{'1' * 8}-1111-1111-1111-{'1' * 12}.{geheimnis}",  # unbekannter Nutzer, richtiges Geheimnis
        geheimnis,                                      # Nutzer-ID fehlt
        f"{user_id}.{geheimnis[:-1]}",                  # abgeschnitten
        f"{user_id}.{geheimnis.upper()}",               # Gross-/Kleinschreibung gehoert zum Token
        "voelliger unsinn",
    ]
    for kandidat in falsch:
        antwort = _zuruecksetzen(client, kandidat)
        assert antwort.status_code == 400 and antwort.json()["detail"] == passwort_reset.UNGUELTIGER_LINK, kandidat
    with SessionLocal() as db:
        assert db.query(PasswortResetToken).one().verbraucht_am is None  # der echte Token ist unangetastet
    assert _zuruecksetzen(client, token).status_code == 204


def test_token_eines_anderen_kontos_ist_nutzlos(client: TestClient, postfach):
    _registrieren(client)
    _registrieren(client, "zwei@example.com")
    _anfordern(client, EMAIL)
    _anfordern(client, "zwei@example.com")
    _, geheimnis_a = _token_aus(postfach[:1]).split(".")
    with SessionLocal() as db:
        id_b = db.query(User).filter(User.id != _token_aus(postfach[:1]).split(".")[0]).one().id
    assert _zuruecksetzen(client, f"{id_b}.{geheimnis_a}").status_code == 400


def test_passwortregeln_wie_bei_der_normalen_aenderung(client: TestClient, postfach):
    _registrieren(client)
    _anfordern(client)
    token = _token_aus(postfach)
    assert _zuruecksetzen(client, token, "zukurz").status_code == 422
    assert _zuruecksetzen(client, token, "x" * 257).status_code == 422
    with SessionLocal() as db:
        assert db.query(PasswortResetToken).one().verbraucht_am is None  # ein Formfehler verbraucht den Token nicht
    assert _zuruecksetzen(client, token).status_code == 204


def test_mfa_bleibt_nach_dem_reset_bestehen_und_wird_beim_login_weiter_verlangt(client: TestClient, postfach):
    pre = _kopf(_registrieren(client)["pre_auth_token"])
    secret = client.post("/auth/mfa/setup", headers=pre).json()["secret"]
    verify = client.post("/auth/mfa/verify", headers=pre, json={"code": pyotp.TOTP(secret).now()}).json()
    codes = verify["wiederherstellungscodes"]
    # Eine laufende MFA-Neueinrichtung (ausstehendes Secret) wird mit dem Reset verworfen.
    kopf = _kopf(verify["access_token"])
    client.post("/security/mfa/neu-einrichten", headers=kopf, json={"aktuelles_passwort": PW, "aktueller_code": pyotp.TOTP(secret).now()})
    _anfordern(client)
    assert _zuruecksetzen(client, _token_aus(postfach)).status_code == 204

    login = client.post("/auth/login", json={"email": EMAIL, "password": NEUES_PW}).json()
    assert login["status"] == "mfa_required" and login["access_token"] is None
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.mfa_enabled and user.mfa_secret_encrypted and user.mfa_pending_secret_encrypted is None
    pre_neu = _kopf(login["pre_auth_token"])
    assert client.post("/auth/login/mfa", headers=pre_neu, json={"code": "000000"}).status_code == 400
    assert client.post("/auth/login/mfa", headers=pre_neu, json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    # Wiederherstellungscodes funktionieren weiter (der Reset hat sie nicht angetastet).
    erneut = client.post("/auth/login", json={"email": EMAIL, "password": NEUES_PW}).json()
    assert client.post(
        "/auth/login/mfa/wiederherstellungscode", headers=_kopf(erneut["pre_auth_token"]), json={"wiederherstellungscode": codes[0]},
    ).status_code == 200


def test_pre_mfa_token_vor_dem_reset_ist_danach_ungueltig(client: TestClient, postfach):
    pre = _kopf(_registrieren(client)["pre_auth_token"])
    _anfordern(client)
    assert _zuruecksetzen(client, _token_aus(postfach)).status_code == 204
    assert client.post("/auth/mfa/setup", headers=pre).status_code == 401


def test_reset_hebt_eine_kontosperre_nicht_auf(client: TestClient, postfach):
    _registrieren(client)
    for _ in range(5):
        client.post("/auth/login", json={"email": EMAIL, "password": "falsch falsch falsch"})
    _anfordern(client)
    assert _zuruecksetzen(client, _token_aus(postfach)).status_code == 204
    assert client.post("/auth/login", json={"email": EMAIL, "password": NEUES_PW}).status_code == 401  # noch gesperrt (15 min)


def test_zuruecksetzen_ist_pro_ip_begrenzt(client: TestClient):
    codes = [_zuruecksetzen(client, "unsinn-unsinn").status_code for _ in range(21)]
    assert codes[:20] == [400] * 20 and codes[20] == 429
