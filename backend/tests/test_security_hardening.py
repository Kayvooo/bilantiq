import re
from pathlib import Path
from unittest.mock import patch

import bcrypt
import pyotp
from sqlalchemy import text

from app.auth.models import User
from app.db import SessionLocal
from app.config import settings
from app.receipts import storage


PASSWORD = "correct horse battery staple"


def _register_and_enroll(client, email="security@example.com", company="Sensitive Finance GmbH"):
    register = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "firmenname": company},
    )
    assert register.status_code == 201
    pre = register.json()["pre_auth_token"]
    setup = client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {pre}"})
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    verify = client.post(
        "/auth/mfa/verify",
        headers={"Authorization": f"Bearer {pre}"},
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert verify.status_code == 200
    return secret, verify.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_sensitive_company_contact_and_invoice_text_are_ciphertext_at_rest(client):
    _, token = _register_and_enroll(client)
    headers = _headers(token)

    company = client.patch(
        "/auth/mandant",
        headers=headers,
        json={
            "ust_id": "DE123456789",
            "steuernummer": "12/345/67890",
            "adresse": "Geheime Finanzstrasse 1",
            "iban": "DE89370400440532013000",
        },
    )
    assert company.status_code == 200

    contact = client.post(
        "/kontakte",
        headers=headers,
        json={
            "name": "Max Mustermann Sensitiv",
            "strasse": "Privatweg 7",
            "plz": "90402",
            "ort": "Nuernberg",
            "email": "max-sensitive@example.com",
            "ust_id": "DE987654321",
        },
    )
    assert contact.status_code == 201
    contact_id = contact.json()["id"]

    invoice = client.post(
        "/invoices",
        headers=headers,
        json={
            "kontakt_id": contact_id,
            "leistungsdatum": "2026-10-01",
            "faelligkeitsdatum": "2026-10-15",
            "waehrung": "EUR",
            "betreff": "Vertrauliches Beratungsprojekt",
            "positionen": [{
                "beschreibung": "Streng vertrauliche Finanzberatung",
                "menge": "1",
                "einzelpreis": "100.00",
                "ust_satz": "19.00",
            }],
        },
    )
    assert invoice.status_code == 201

    with SessionLocal.kw["bind"].connect() as connection:  # Verwaltungszugriff, nicht die RLS-Rolle der App
        mandant = connection.execute(
            text("SELECT firmenname, ust_id, steuernummer, adresse, iban FROM mandanten")
        ).mappings().one()
        raw_contact = connection.execute(
            text("SELECT name, strasse, email, ust_id FROM kontakte WHERE id=:id"),
            {"id": contact_id},
        ).mappings().one()
        raw_invoice = connection.execute(
            text("SELECT betreff FROM invoices WHERE id=:id"),
            {"id": invoice.json()["id"]},
        ).mappings().one()
        raw_position = connection.execute(
            text("SELECT beschreibung FROM invoice_positionen WHERE invoice_id=:id"),
            {"id": invoice.json()["id"]},
        ).mappings().one()

    for value in [
        *mandant.values(),
        *raw_contact.values(),
        raw_invoice["betreff"],
        raw_position["beschreibung"],
    ]:
        assert isinstance(value, str)
        assert value.startswith("enc:v2:")

    raw_dump = " ".join(str(value) for value in [
        *mandant.values(), *raw_contact.values(), raw_invoice["betreff"], raw_position["beschreibung"]
    ])
    for plaintext in [
        "Sensitive Finance GmbH", "DE123456789", "12/345/67890", "Geheime Finanzstrasse",
        "Max Mustermann Sensitiv", "max-sensitive@example.com", "Vertrauliches Beratungsprojekt",
        "Streng vertrauliche Finanzberatung",
    ]:
        assert plaintext not in raw_dump

    # API/ORM liefert weiterhin die fachlich benoetigten Klarwerte nach Auth-Pruefung.
    assert client.get("/auth/mandant", headers=headers).json()["ust_id"] == "DE123456789"
    assert client.get("/kontakte", headers=headers).json()[0]["name"] == "Max Mustermann Sensitiv"


def test_receipt_storage_is_ciphertext_on_disk_but_roundtrips(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "receipt_storage_dir", str(tmp_path))
    original = b"%PDF-1.7\nVERTRAULICH: Finanzbeleg\n"
    file_hash = storage.hash_bytes(original)

    relative = storage.save("tenant-1", file_hash, "application/pdf", original)
    raw = (tmp_path / relative).read_bytes()

    assert raw.startswith(b"BQENC2")
    assert original not in raw
    assert storage.read(relative) == original


def test_new_password_hashes_use_argon2_and_legacy_bcrypt_is_upgraded_on_login(client):
    _register_and_enroll(client, email="argon@example.com")
    with SessionLocal() as db:
        user = db.query(User).filter(User.email_lookup_hash.is_not(None)).one()
        assert user.passwort_hash.startswith("$argon2")
        user.passwort_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
        db.commit()

    login = client.post("/auth/login", json={"email": "argon@example.com", "password": PASSWORD})
    assert login.status_code == 200

    with SessionLocal() as db:
        user = db.query(User).filter(User.email_lookup_hash.is_not(None)).one()
        assert user.passwort_hash.startswith("$argon2")


def test_password_change_immediately_invalidates_existing_session(client):
    _, token = _register_and_enroll(client, email="password@example.com")
    headers = _headers(token)

    changed = client.post(
        "/auth/passwort/aendern",
        headers=headers,
        json={"aktuelles_passwort": PASSWORD, "neues_passwort": "new correct horse battery staple"},
    )
    assert changed.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": "password@example.com", "password": PASSWORD}).status_code == 401
    assert client.post(
        "/auth/login",
        json={"email": "password@example.com", "password": "new correct horse battery staple"},
    ).status_code == 200


def test_email_change_requires_code_to_new_address_and_invalidates_sessions(client):
    _, token = _register_and_enroll(client, email="old@example.com")
    headers = _headers(token)

    with patch("app.security.routes.mailer.sende_text_email") as send:
        start = client.post(
            "/security/email/aenderung-starten",
            headers=headers,
            json={"neues_email": "new@example.com", "aktuelles_passwort": PASSWORD},
        )
        assert start.status_code == 204
        assert send.call_count == 1
        assert send.call_args.args[0] == "new@example.com"
        match = re.search(r"\b(\d{6})\b", send.call_args.args[2])
        assert match is not None
        code = match.group(1)

    confirm = client.post(
        "/security/email/aenderung-bestaetigen",
        headers=headers,
        json={"code": code},
    )
    assert confirm.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.post("/auth/login", json={"email": "old@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).status_code == 200


def test_revoke_other_sessions_is_immediate(client):
    secret, token_one = _register_and_enroll(client, email="sessions@example.com")

    login = client.post("/auth/login", json={"email": "sessions@example.com", "password": PASSWORD})
    pre = login.json()["pre_auth_token"]
    second = client.post(
        "/auth/login/mfa",
        headers={"Authorization": f"Bearer {pre}"},
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert second.status_code == 200
    token_two = second.json()["access_token"]

    assert client.get("/auth/me", headers=_headers(token_two)).status_code == 200
    revoke = client.post("/security/sessions/andere-abmelden", headers=_headers(token_one))
    assert revoke.status_code == 204
    assert client.get("/auth/me", headers=_headers(token_one)).status_code == 200
    assert client.get("/auth/me", headers=_headers(token_two)).status_code == 401
