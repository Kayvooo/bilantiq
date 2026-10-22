from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant


def _vorlage_payload(*, naechstes_datum: str, intervall: str = "monatlich", enddatum: str | None = None) -> dict:
    return {
        "bezeichnung": "Cloud-Hosting", "anbieter": "Hosting-Anbieter GmbH",
        "betrag": "29.99", "ust_satz": "19.00", "kategorie": "Software/IT",
        "intervall": intervall, "naechstes_datum": naechstes_datum, "enddatum": enddatum,
    }


def test_create_and_list_wiederkehrende_ausgabe(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum="2026-10-01"))
    assert resp.status_code == 201
    assert resp.json()["aktiv"] is True

    liste = client.get("/wiederkehrende-ausgaben", headers=headers).json()
    assert len(liste) == 1


def test_erzeugen_bucht_ausgabe_ohne_beleg_und_verschiebt_termin(client: TestClient):
    headers = _onboarded_mandant(client)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum=gestern))

    resp = client.post("/wiederkehrende-ausgaben/erzeugen", headers=headers)
    assert resp.status_code == 200
    ergebnis = resp.json()
    assert ergebnis["anzahl"] == 1

    ausgaben = client.get("/ausgaben", headers=headers).json()
    assert len(ausgaben) == 1
    assert ausgaben[0]["receipt_id"] is None
    assert ausgaben[0]["konto"] == "6835"  # Software/IT
    assert float(ausgaben[0]["betrag"]) == 29.99
    assert ausgaben[0]["zahlungsdatum"] == gestern

    vorlage = client.get("/wiederkehrende-ausgaben", headers=headers).json()[0]
    assert vorlage["naechstes_datum"] != gestern


def test_ausgaben_erzeugen_ist_idempotent_ohne_faellige_vorlagen(client: TestClient):
    headers = _onboarded_mandant(client)
    morgen = (date.today() + timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum=morgen))

    resp = client.post("/wiederkehrende-ausgaben/erzeugen", headers=headers).json()
    assert resp["anzahl"] == 0


def test_wiederkehrende_ausgabe_deaktiviert_sich_nach_enddatum(client: TestClient):
    headers = _onboarded_mandant(client)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum=gestern, enddatum=gestern))

    client.post("/wiederkehrende-ausgaben/erzeugen", headers=headers)
    vorlage = client.get("/wiederkehrende-ausgaben", headers=headers).json()[0]
    assert vorlage["aktiv"] is False


def test_deaktivieren_stoppt_weitere_erzeugung(client: TestClient):
    headers = _onboarded_mandant(client)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    vorlage = client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum=gestern)).json()

    client.post(f"/wiederkehrende-ausgaben/{vorlage['id']}/deaktivieren", headers=headers)
    ergebnis = client.post("/wiederkehrende-ausgaben/erzeugen", headers=headers).json()
    assert ergebnis["anzahl"] == 0


def test_wiederkehrende_ausgaben_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    client.post("/wiederkehrende-ausgaben", headers=kevin_headers, json=_vorlage_payload(naechstes_datum="2026-10-01"))

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get("/wiederkehrende-ausgaben", headers=lea_headers).json()
    assert resp == []


def test_list_ausgaben_zeigt_beleg_und_wiederkehrend_gemischt(client: TestClient):
    headers = _onboarded_mandant(client)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-ausgaben", headers=headers, json=_vorlage_payload(naechstes_datum=gestern))
    client.post("/wiederkehrende-ausgaben/erzeugen", headers=headers)

    upload = client.post(
        "/belege", headers=headers,
        files={"file": ("beleg.png", b"\x89PNG\r\n\x1a\nfake-bytes-for-hashing-only", "image/png")},
        data={"force": "false"},
    ).json()
    client.post(
        f"/belege/{upload['id']}/bestaetigen", headers=headers,
            json={
                "betrag": "10.00", "datum": gestern, "anbieter": "Laden", "ust_satz": "19.00",
                "kategorie": "Buerobedarf", "konto": "4930",
            },
    )

    ausgaben = client.get("/ausgaben", headers=headers).json()
    assert len(ausgaben) == 2
    assert {a["receipt_id"] is None for a in ausgaben} == {True, False}
