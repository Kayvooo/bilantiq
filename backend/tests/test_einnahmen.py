import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _payload(*, bezeichnung: str = "Provision", datum: str | None = None) -> dict:
    return {
        "bezeichnung": bezeichnung,
        "betrag_brutto": "119.00",
        "ust_satz": "19.00",
        "datum": datum or f"{date.today().year}-05-10",
        "verwendungszweck": "Partnerprogramm Mai",
    }


def test_sonstige_einnahmen_erstellen_sortieren_und_bearbeiten(client: TestClient):
    headers = _onboarded_mandant(client)
    zuerst = client.post("/einnahmen", headers=headers, json=_payload(bezeichnung="Mai"))
    danach = client.post(
        "/einnahmen",
        headers=headers,
        json=_payload(bezeichnung="Juni", datum=f"{date.today().year}-06-10"),
    )

    assert zuerst.status_code == 201
    assert danach.status_code == 201
    assert zuerst.json()["betrag_brutto"] == "119.00"

    liste = client.get("/einnahmen", headers=headers)
    assert liste.status_code == 200
    assert [eintrag["bezeichnung"] for eintrag in liste.json()] == ["Juni", "Mai"]

    update = client.patch(
        f"/einnahmen/{zuerst.json()['id']}",
        headers=headers,
        json={"bezeichnung": "Mai korrigiert"},
    )
    assert update.status_code == 200
    assert update.json()["bezeichnung"] == "Mai korrigiert"
    assert update.json()["verwendungszweck"] == "Partnerprogramm Mai"


def test_sonstige_einnahmen_sind_mandantenisoliert(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    einnahme_id = client.post("/einnahmen", headers=kevin_headers, json=_payload()).json()["id"]

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    assert client.get("/einnahmen", headers=lea_headers).json() == []
    assert client.patch(
        f"/einnahmen/{einnahme_id}",
        headers=lea_headers,
        json={"bezeichnung": "Fremd"},
    ).status_code == 404


@pytest.mark.parametrize(
    "updates",
    [
        {"betrag_brutto": "0.00"},
        {"betrag_brutto": "-0.01"},
        {"ust_satz": "100.01"},
    ],
)
def test_ungueltige_sonstige_einnahme_wird_abgelehnt(client: TestClient, updates: dict):
    headers = _onboarded_mandant(client)
    response = client.post("/einnahmen", headers=headers, json=_payload() | updates)
    assert response.status_code == 422


def test_sonstige_einnahme_fliesst_konsistent_in_auswertungen(client: TestClient):
    headers = _onboarded_mandant(client)
    jahr = date.today().year
    erstellt = client.post("/einnahmen", headers=headers, json=_payload()).json()

    euer = client.get(f"/berichte/euer?jahr={jahr}", headers=headers).json()
    assert float(euer["betriebseinnahmen_netto"]) == 100.00
    assert euer["anzahl_einnahmen"] == 1

    susa = client.get(f"/berichte/susa?jahr={jahr}", headers=headers).json()
    konten = {konto["konto"]: konto for konto in susa["konten"]}
    assert float(susa["summe_soll"]) == float(susa["summe_haben"]) == 119.00
    assert float(konten["1200"]["soll"]) == 119.00
    assert float(konten["2700"]["haben"]) == 119.00

    bwa = client.get(f"/berichte/bwa?jahr={jahr}", headers=headers).json()
    assert float(bwa["erloese_gesamt"]) == 119.00
    assert bwa["erloes_posten"] == [
        {"konto": "2700", "bezeichnung": "Sonstige betriebliche Ertraege", "betrag": "119.00"}
    ]

    csv_text = client.get(f"/berichte/datev-export?jahr={jahr}", headers=headers).content.decode("utf-8-sig")
    buchungen = list(csv.reader(io.StringIO(csv_text), delimiter=";"))[2:]
    assert len(buchungen) == 1
    assert buchungen[0][0] == "119,00"
    assert buchungen[0][1] == "S"
    assert buchungen[0][6] == "1200"
    assert buchungen[0][7] == "2700"
    assert buchungen[0][8] == "3"
    assert buchungen[0][10] == erstellt["id"][:8]


def test_sonstige_einnahme_aus_anderem_jahr_bleibt_aus_reports(client: TestClient):
    headers = _onboarded_mandant(client)
    jahr = date.today().year
    client.post(
        "/einnahmen",
        headers=headers,
        json=_payload(datum=f"{jahr - 1}-12-31"),
    )

    assert float(client.get(f"/berichte/euer?jahr={jahr}", headers=headers).json()["betriebseinnahmen_netto"]) == 0
    assert client.get(f"/berichte/susa?jahr={jahr}", headers=headers).json()["konten"] == []
