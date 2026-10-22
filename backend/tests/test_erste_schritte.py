from fastapi.testclient import TestClient

from tests.test_invoices import _invoice_payload, _kontakt
from tests.test_invoices import _onboarded_mandant as _mandant
from tests.test_receipts import (
    _clear_extractor_override,  # noqa: F401  (autouse-Fixture)
    _extraction,
    _FakeExtractor,
    _use_extractor,
)

REIHENFOLGE = ["unternehmen", "design", "kunde", "rechnung", "beleg", "bank", "umzug", "steuerberater"]


def _stand(client: TestClient, headers: dict) -> dict:
    antwort = client.get("/erste-schritte", headers=headers)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


def _erledigt(stand: dict) -> set[str]:
    return {s["id"] for s in stand["schritte"] if s["erledigt"]}


def test_checkliste_hat_feste_reihenfolge_und_ziele(client: TestClient):
    headers = _mandant(client)

    stand = _stand(client, headers)

    assert [s["id"] for s in stand["schritte"]] == REIHENFOLGE
    assert stand["gesamt"] == 8
    assert {s["id"]: s["ziel"] for s in stand["schritte"]} == {
        "unternehmen": "settings", "design": "rechnungsvorlage", "kunde": "contacts", "rechnung": "invoices",
        "beleg": "receipts", "bank": "bank", "umzug": "umzug", "steuerberater": "steuerberater",
    }
    assert [s["id"] for s in stand["schritte"] if s["optional"]] == ["umzug", "steuerberater"]


def test_fortschritt_folgt_den_vorhandenen_daten(client: TestClient):
    headers = _mandant(client)  # setzt Anschrift und USt-IdNr.
    assert _erledigt(_stand(client, headers)) == {"unternehmen"}

    kontakt_id = _kontakt(client, headers)
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    assert _erledigt(_stand(client, headers)) == {"unternehmen", "kunde"}  # Entwurf zählt noch nicht

    client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers)
    _use_extractor(_FakeExtractor(_extraction()))
    client.post("/belege", headers=headers, files={"file": ("b.png", b"\x89PNG\r\n\x1a\nes", "image/png")})
    client.post("/bank/konten", headers=headers, json={"bezeichnung": "Konto"})
    client.patch("/auth/mandant", headers=headers, json={"steuerberater_name": "Kanzlei Beispiel"})

    stand = _stand(client, headers)
    assert _erledigt(stand) == set(REIHENFOLGE) - {"design", "umzug"}  # der Umzug ist erst mit einem Import erledigt
    assert (stand["erledigt"], stand["gesamt"]) == (6, 8)


def test_unternehmensdaten_brauchen_anschrift_und_steuerkennung(client: TestClient):
    headers = _mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"ust_id": None})
    assert "unternehmen" not in _erledigt(_stand(client, headers))

    client.patch("/auth/mandant", headers=headers, json={"steuernummer": "12/345/67890"})

    assert "unternehmen" in _erledigt(_stand(client, headers))


def test_bank_schritt_hat_keinen_tarifhinweis(client: TestClient):
    headers = _mandant(client)

    hinweise = {s["id"]: s["hinweis"] for s in _stand(client, headers)["schritte"]}

    assert hinweise["bank"] is None


def test_fortschritt_eines_anderen_mandanten_zaehlt_nicht(client: TestClient):
    kopf_a = _mandant(client, email="a@example.com")
    kopf_b = _mandant(client, email="b@example.com")
    _kontakt(client, kopf_a)
    client.post("/bank/konten", headers=kopf_a, json={"bezeichnung": "Konto A"})

    assert _erledigt(_stand(client, kopf_b)) == {"unternehmen"}


def test_checkliste_braucht_eine_anmeldung(client: TestClient):
    assert client.get("/erste-schritte").status_code == 401
