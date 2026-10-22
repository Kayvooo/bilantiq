"""E-Mail-Versand von Rechnungen/Angeboten/Mahnungen (app/core/mailer.py).

smtplib.SMTP wird an der Importstelle in app.core.mailer gemockt -- es findet nie ein
echter Netzwerk-/SMTP-Zugriff statt, siehe Docstring von mailer.sende_email()."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant
from tests.test_mahnwesen import _finalized_overdue_invoice
from tests.test_quotes import _quote_payload


def _set_kontakt_email(client: TestClient, headers: dict, kontakt_id: str, email: str = "kunde@example.com") -> str:
    resp = client.patch(f"/kontakte/{kontakt_id}", headers=headers, json={"email": email})
    assert resp.status_code == 200
    return email


def _finalized_invoice(client: TestClient, headers: dict, kontakt_id: str) -> dict:
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    return client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()


def _versendetes_angebot(client: TestClient, headers: dict, kontakt_id: str) -> dict:
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    return client.post(f"/angebote/{draft['id']}/versenden", headers=headers).json()


def _pdf_attachment(sent_message):
    return next(part for part in sent_message.walk() if part.get_content_disposition() == "attachment")


# ---------------------------------------------------------------------------
# Rechnungen -- POST /invoices/{id}/versenden
# ---------------------------------------------------------------------------

def test_send_invoice_email_success(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    email = _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["versendet_am"] is not None

    mock_smtp.return_value.starttls.assert_called_once()
    mock_smtp.return_value.login.assert_called_once()
    mock_smtp.return_value.send_message.assert_called_once()
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    assert sent["To"] == email
    assert sent["Subject"] == f"Rechnung {invoice['nummer']}"
    attachment = _pdf_attachment(sent)
    assert attachment.get_filename() == f"Rechnung_{invoice['nummer']}.pdf"
    assert bytes(attachment.get_payload(decode=True))[:4] == b"%PDF"

    # Zeitstempel ist auch persistiert, nicht nur in der Response dieses Aufrufs.
    fetched = client.get(f"/invoices/{invoice['id']}", headers=headers).json()
    assert fetched["versendet_am"] is not None


def test_send_invoice_with_custom_text_uses_override(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(
            f"/invoices/{invoice['id']}/versenden", headers=headers, json={"text": "Individueller Grusstext"}
        )

    assert resp.status_code == 200
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    text_part = next(part for part in sent.walk() if part.get_content_type() == "text/plain")
    assert "Individueller Grusstext" in text_part.get_payload(decode=True).decode("utf-8")


def test_send_invoice_default_text_enthaelt_keinen_zahllink(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 200
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    text_part = next(part for part in sent.walk() if part.get_content_type() == "text/plain")
    body = text_part.get_payload(decode=True).decode("utf-8")
    assert f"Rechnung {invoice['nummer']}" in body
    assert "Online bezahlen" not in body and "/zahlen/" not in body
    assert "zahllink_vorhanden" not in resp.json()


def test_send_invoice_without_kontakt_email_returns_400(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)  # keine E-Mail hinterlegt
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 400
    mock_smtp.assert_not_called()


def test_send_draft_invoice_returns_400(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/invoices/{draft['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 400
    mock_smtp.assert_not_called()


def test_send_invoice_cross_mandant_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kontakt_id = _kontakt(client, kevin_headers)
    _set_kontakt_email(client, kevin_headers, kontakt_id)
    invoice = _finalized_invoice(client, kevin_headers, kontakt_id)

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/invoices/{invoice['id']}/versenden", headers=lea_headers, json={})

    assert resp.status_code == 404
    mock_smtp.assert_not_called()


# ---------------------------------------------------------------------------
# Angebote -- POST /angebote/{id}/per-email-senden
#
# Bewusst nicht .../versenden -- dieser Pfad ist bereits belegt (finalisiert den
# Entwurf: vergibt die Angebotsnummer, setzt status="versendet", siehe test_quotes.py).
# ---------------------------------------------------------------------------

def test_send_quote_email_success(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    email = _set_kontakt_email(client, headers, kontakt_id)
    quote = _versendetes_angebot(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/angebote/{quote['id']}/per-email-senden", headers=headers, json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["email_versendet_am"] is not None
    # Der schon vorher gesetzte Finalisierungs-Zeitpunkt bleibt unberuehrt -- eigenes Feld.
    assert body["status"] == "versendet"

    mock_smtp.return_value.send_message.assert_called_once()
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    assert sent["To"] == email
    assert sent["Subject"] == f"Angebot {quote['nummer']}"
    attachment = _pdf_attachment(sent)
    assert attachment.get_filename() == f"Angebot_{quote['nummer']}.pdf"
    assert bytes(attachment.get_payload(decode=True))[:4] == b"%PDF"


def test_send_quote_without_kontakt_email_returns_400(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    quote = _versendetes_angebot(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/angebote/{quote['id']}/per-email-senden", headers=headers, json={})

    assert resp.status_code == 400
    mock_smtp.assert_not_called()


def test_send_draft_quote_returns_400(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    draft = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/angebote/{draft['id']}/per-email-senden", headers=headers, json={})

    assert resp.status_code == 400
    mock_smtp.assert_not_called()


def test_send_quote_cross_mandant_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kontakt_id = _kontakt(client, kevin_headers)
    _set_kontakt_email(client, kevin_headers, kontakt_id)
    quote = _versendetes_angebot(client, kevin_headers, kontakt_id)

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/angebote/{quote['id']}/per-email-senden", headers=lea_headers, json={})

    assert resp.status_code == 404
    mock_smtp.assert_not_called()


# ---------------------------------------------------------------------------
# Mahnungen -- POST /mahnungen/{id}/versenden
#
# Kein Entwurfs-Check: eine Mahnung existiert laut app/mahnwesen/models.py immer
# nur final, es gibt keinen Entwurfsstatus zu testen.
# ---------------------------------------------------------------------------

def test_send_mahnung_email_success(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)
    email = _set_kontakt_email(client, headers, invoice["kontakt_id"])
    mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/mahnungen/{mahnung['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["versendet_am"] is not None

    mock_smtp.return_value.send_message.assert_called_once()
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    assert sent["To"] == email
    attachment = _pdf_attachment(sent)
    assert attachment.get_filename() == f"Mahnung_{invoice['nummer']}_Stufe1.pdf"
    assert bytes(attachment.get_payload(decode=True))[:4] == b"%PDF"


def test_send_mahnung_without_kontakt_email_returns_400(client: TestClient):
    headers = _onboarded_mandant(client)
    invoice = _finalized_overdue_invoice(client, headers)  # keine E-Mail hinterlegt
    mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/mahnungen/{mahnung['id']}/versenden", headers=headers, json={})

    assert resp.status_code == 400
    mock_smtp.assert_not_called()


def test_send_mahnung_cross_mandant_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_invoice = _finalized_overdue_invoice(client, kevin_headers)
    _set_kontakt_email(client, kevin_headers, kevin_invoice["kontakt_id"])
    kevin_mahnung = client.post(f"/invoices/{kevin_invoice['id']}/mahnung", headers=kevin_headers).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        resp = client.post(f"/mahnungen/{kevin_mahnung['id']}/versenden", headers=lea_headers, json={})

    assert resp.status_code == 404
    mock_smtp.assert_not_called()


# ---------------------------------------------------------------------------
# Reply-To und Versandlimit je Mandant (Release-Haertung, Missbrauchsschutz)
# ---------------------------------------------------------------------------

def test_versand_setzt_reply_to_auf_die_anmeldeadresse_des_nutzers(client: TestClient):
    headers = _onboarded_mandant(client, email="chef@firma.example")
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200
    sent = mock_smtp.return_value.send_message.call_args[0][0]
    assert sent["Reply-To"] == "chef@firma.example"
    assert "noreply" in sent["From"]  # Absender bleibt die Systemadresse


def test_reply_to_laesst_sich_abschalten(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.core.mailversand.settings.email_reply_to_nutzer", False)
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200
    assert mock_smtp.return_value.send_message.call_args[0][0]["Reply-To"] is None


def test_angebot_und_mahnung_tragen_ebenfalls_reply_to(client: TestClient):
    headers = _onboarded_mandant(client, email="chef@firma.example")
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    quote = _versendetes_angebot(client, headers, kontakt_id)
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        assert client.post(f"/angebote/{quote['id']}/per-email-senden", headers=headers, json={}).status_code == 200
    assert mock_smtp.return_value.send_message.call_args[0][0]["Reply-To"] == "chef@firma.example"

    invoice = _finalized_overdue_invoice(client, headers)
    _set_kontakt_email(client, headers, invoice["kontakt_id"])
    mahnung = client.post(f"/invoices/{invoice['id']}/mahnung", headers=headers).json()
    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        assert client.post(f"/mahnungen/{mahnung['id']}/versenden", headers=headers, json={}).status_code == 200
    assert mock_smtp.return_value.send_message.call_args[0][0]["Reply-To"] == "chef@firma.example"


def test_versandlimit_je_mandant_blockiert_ueber_alle_drei_arten(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.core.mailversand.settings.email_limit_pro_stunde", 2)
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)
    quote = _versendetes_angebot(client, headers, kontakt_id)

    with patch("app.core.mailer.smtplib.SMTP") as mock_smtp:
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200
        assert client.post(f"/angebote/{quote['id']}/per-email-senden", headers=headers, json={}).status_code == 200
        blockiert = client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={})
        assert blockiert.status_code == 429
        assert int(blockiert.headers["Retry-After"]) >= 60
        assert "Versandlimit" in blockiert.json()["detail"]
        assert client.post(f"/angebote/{quote['id']}/per-email-senden", headers=headers, json={}).status_code == 429
    assert mock_smtp.return_value.send_message.call_count == 2  # die gesperrten haben nichts verschickt

    # Anderer Mandant ist davon unberuehrt.
    andere = _onboarded_mandant(client, email="zweiter@example.com")
    k2 = _kontakt(client, andere)
    _set_kontakt_email(client, andere, k2)
    rechnung2 = _finalized_invoice(client, andere, k2)
    with patch("app.core.mailer.smtplib.SMTP"):
        assert client.post(f"/invoices/{rechnung2['id']}/versenden", headers=andere, json={}).status_code == 200


def test_versandlimit_tag_und_zuruecksetzen_ueber_zeitfenster(client: TestClient, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.core.audit_log import AuditLogEintrag
    from app.db import SessionLocal

    monkeypatch.setattr("app.core.mailversand.settings.email_limit_pro_tag", 1)
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)
    with patch("app.core.mailer.smtplib.SMTP"):
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 429
        # Ereignisse aelter als 24 h zaehlen nicht mehr. Der Audit-Log ist append-only (auch unter Postgres per
        # Trigger), deshalb wird die Uhr des Limits vorgestellt statt Zeitstempel zu aendern.
        spaeter = datetime.now(timezone.utc) + timedelta(hours=25)
        monkeypatch.setattr("app.core.mailversand._jetzt", lambda: spaeter)
        assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200


def test_versandlimit_null_schaltet_es_ab(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.core.mailversand.settings.email_limit_pro_stunde", 0)
    monkeypatch.setattr("app.core.mailversand.settings.email_limit_pro_tag", 0)
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    _set_kontakt_email(client, headers, kontakt_id)
    invoice = _finalized_invoice(client, headers, kontakt_id)
    with patch("app.core.mailer.smtplib.SMTP"):
        for _ in range(3):
            assert client.post(f"/invoices/{invoice['id']}/versenden", headers=headers, json={}).status_code == 200
