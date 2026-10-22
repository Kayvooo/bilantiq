import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.ai.client import get_ai_client
from app.ai.schemas import AssistantPlan
from app.config import settings
from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant


class FakeAi:
    def __init__(self, *, json_results=None, text_result="Aus den Bilantiq-Daten ergibt sich keine Auffaelligkeit."):
        self.json_results = list(json_results or [])
        self.text_result = text_result
        self.text_messages: list[list[dict[str, str]]] = []
        self.json_messages: list[list[dict[str, str]]] = []

    def complete_json(self, messages, schema):
        self.json_messages.append(messages)
        result = self.json_results.pop(0)
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)

    def complete_text(self, messages):
        self.text_messages.append(messages)
        return self.text_result


@pytest.fixture
def use_fake_ai(client):
    configured = []

    def _set(fake: FakeAi):
        client.app.dependency_overrides[get_ai_client] = lambda: fake
        configured.append(fake)
        return fake

    yield _set
    client.app.dependency_overrides.pop(get_ai_client, None)


def _invoice_draft(kontakt_id: str) -> dict:
    today = date.today()
    return {
        "kontakt_id": kontakt_id,
        "leistungsdatum": today.isoformat(),
        "faelligkeitsdatum": (today + timedelta(days=14)).isoformat(),
        "waehrung": "EUR",
        "positionen": [
            {
                "beschreibung": "Webentwicklung",
                "menge": "10",
                "einzelpreis": "90.00",
                "ust_satz": "19.00",
                "kategorie": "Dienstleistung",
            }
        ],
        "betreff": "Webentwicklung",
    }


def _quote_draft(kontakt_id: str) -> dict:
    return {
        "kontakt_id": kontakt_id,
        "gueltig_bis": (date.today() + timedelta(days=14)).isoformat(),
        "waehrung": "EUR",
        "positionen": [
            {
                "beschreibung": "Website-Relaunch",
                "menge": "1",
                "einzelpreis": "2500.00",
                "ust_satz": "19.00",
            }
        ],
    }


def test_ai_disabled_returns_503(client, monkeypatch):
    headers = _onboarded_mandant(client)
    monkeypatch.setattr(settings, "ai_enabled", False)

    response = client.post("/ai/assistent", headers=headers, json={"frage": "Wie hoch ist mein Gewinn?"})

    assert response.status_code == 503
    assert "nicht aktiviert" in response.json()["detail"]


def test_assistant_uses_only_current_tenant_data(client, use_fake_ai):
    kevin = _onboarded_mandant(client, email="kevin@example.com")
    kontakt_id = _kontakt(client, kevin)
    invoice = client.post("/invoices", headers=kevin, json=_invoice_payload(kontakt_id)).json()
    client.post(f"/invoices/{invoice['id']}/finalize", headers=kevin)

    lea = _onboarded_mandant(client, email="lea@example.com")
    fake = use_fake_ai(FakeAi(
        json_results=[AssistantPlan(tool="offene_rechnungen")],
        text_result="Es gibt keine offenen Rechnungen.",
    ))

    response = client.post("/ai/assistent", headers=lea, json={"frage": "Welche Rechnungen sind offen?"})

    assert response.status_code == 200
    assert response.json()["tool"] == "offene_rechnungen"
    assert len(fake.text_messages) == 1
    answer_payload = json.loads(fake.text_messages[0][-1]["content"])
    assert answer_payload["daten"]["rechnungen"] == []


def test_invoice_ai_returns_form_draft_without_persisting(client, use_fake_ai):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    use_fake_ai(FakeAi(json_results=[_invoice_draft(kontakt_id)]))

    response = client.post(
        "/ai/rechnungsentwurf",
        headers=headers,
        json={"anweisung": "10 Stunden Webentwicklung fuer den Beispiel Kunden zu 90 Euro."},
    )

    assert response.status_code == 200
    assert response.json()["kontakt_id"] == kontakt_id
    assert response.json()["positionen"][0]["beschreibung"] == "Webentwicklung"
    assert client.get("/invoices", headers=headers).json() == []


def test_quote_ai_returns_form_draft_without_persisting(client, use_fake_ai):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    use_fake_ai(FakeAi(json_results=[_quote_draft(kontakt_id)]))

    response = client.post(
        "/ai/angebotsentwurf",
        headers=headers,
        json={"anweisung": "Angebot fuer einen Website-Relaunch zu 2500 Euro netto."},
    )

    assert response.status_code == 200
    assert response.json()["kontakt_id"] == kontakt_id
    assert client.get("/angebote", headers=headers).json() == []


def test_ai_draft_rejects_foreign_contact(client, use_fake_ai):
    foreign = _onboarded_mandant(client, email="foreign@example.com")
    foreign_contact = _kontakt(client, foreign)
    owner = _onboarded_mandant(client, email="owner@example.com")
    _kontakt(client, owner)
    use_fake_ai(FakeAi(json_results=[_invoice_draft(foreign_contact)]))

    response = client.post(
        "/ai/rechnungsentwurf",
        headers=owner,
        json={"anweisung": "Rechnung an einen Kunden."},
    )

    assert response.status_code == 404
    assert client.get("/invoices", headers=owner).json() == []


def test_invoice_text_suggestion_does_not_send_email(client, use_fake_ai):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
    use_fake_ai(FakeAi(text_result="Guten Tag,\n\nanbei erhalten Sie Ihre Rechnung.\n"))

    with patch("app.core.mailer.sende_email") as sende_email:
        response = client.post(
            "/ai/textvorschlag",
            headers=headers,
            json={"art": "rechnung", "objekt_id": final["id"], "ton": "freundlich"},
        )

    assert response.status_code == 200
    assert "anbei" in response.json()["text"]
    sende_email.assert_not_called()
    unchanged = client.get(f"/invoices/{final['id']}", headers=headers).json()
    assert unchanged["versendet_am"] is None


def test_mahnung_text_suggestion_is_tenant_scoped(client, use_fake_ai):
    owner = _onboarded_mandant(client, email="owner@example.com")
    kontakt_id = _kontakt(client, owner)
    payload = _invoice_payload(kontakt_id)
    payload["faelligkeitsdatum"] = (date.today() - timedelta(days=1)).isoformat()
    draft = client.post("/invoices", headers=owner, json=payload).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=owner).json()
    mahnung = client.post(f"/invoices/{final['id']}/mahnung", headers=owner).json()

    foreign = _onboarded_mandant(client, email="foreign@example.com")
    use_fake_ai(FakeAi(text_result="Bitte begleichen Sie den offenen Betrag."))

    response = client.post(
        "/ai/textvorschlag",
        headers=foreign,
        json={"art": "mahnung", "objekt_id": mahnung["id"], "ton": "bestimmt"},
    )

    assert response.status_code == 404
