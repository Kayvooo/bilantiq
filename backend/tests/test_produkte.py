import pytest
from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant


def _produkt_payload(*, bezeichnung: str) -> dict:
    return {
        "bezeichnung": bezeichnung,
        "beschreibung": "Beratung für kleine Unternehmen",
        "einzelpreis": "125.00",
        "ust_satz": "19.00",
        "einheit": "Stunde",
        "aktiv": True,
    }


def test_produkte_werden_erstellt_und_alphabetisch_gelistet(client: TestClient):
    headers = _onboarded_mandant(client)

    zuerst = client.post("/produkte", headers=headers, json=_produkt_payload(bezeichnung="Workshop"))
    danach = client.post("/produkte", headers=headers, json=_produkt_payload(bezeichnung="Analyse"))

    assert zuerst.status_code == 201
    assert danach.status_code == 201
    assert zuerst.json()["einzelpreis"] == "125.00"

    produkte = client.get("/produkte", headers=headers)
    assert produkte.status_code == 200
    assert [produkt["bezeichnung"] for produkt in produkte.json()] == ["Analyse", "Workshop"]


def test_fremdes_produkt_bleibt_in_liste_und_update_verborgen(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    produkt_id = client.post(
        "/produkte",
        headers=kevin_headers,
        json=_produkt_payload(bezeichnung="Interne Beratung"),
    ).json()["id"]

    eigenes_update = client.patch(
        f"/produkte/{produkt_id}",
        headers=kevin_headers,
        json={"bezeichnung": "Aktualisierte Beratung"},
    )
    assert eigenes_update.status_code == 200
    assert eigenes_update.json()["bezeichnung"] == "Aktualisierte Beratung"
    assert eigenes_update.json()["beschreibung"] == "Beratung für kleine Unternehmen"
    assert eigenes_update.json()["einzelpreis"] == "125.00"

    lea_headers = _onboarded_mandant(client, email="lea@example.com")

    assert client.get("/produkte", headers=lea_headers).json() == []
    update = client.patch(
        f"/produkte/{produkt_id}",
        headers=lea_headers,
        json={"bezeichnung": "Übernommen"},
    )
    assert update.status_code == 404


@pytest.mark.parametrize(
    ("updates", "ungueltiger_wert"),
    [
        ({"einzelpreis": "-0.01"}, "einzelpreis"),
        ({"ust_satz": "100.01"}, "ust_satz"),
    ],
)
def test_ungueltige_produktwerte_werden_abgelehnt(
    client: TestClient,
    updates: dict,
    ungueltiger_wert: str,
):
    headers = _onboarded_mandant(client)
    payload = _produkt_payload(bezeichnung="Analyse") | updates

    response = client.post("/produkte", headers=headers, json=payload)

    assert response.status_code == 422
    assert ungueltiger_wert in str(response.json()["detail"])
