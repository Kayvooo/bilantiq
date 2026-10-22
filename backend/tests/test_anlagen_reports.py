import csv
import io
from datetime import date

from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _anlage(client: TestClient, headers: dict, *, jahr: int) -> dict:
    response = client.post(
        "/anlagen",
        headers=headers,
        json={
            "bezeichnung": "Produktionsrechner",
            "anschaffungsdatum": f"{jahr}-01-15",
            "anschaffungskosten_netto": "1200.00",
            "nutzungsdauer_jahre": 3,
            "kategorie": "IT",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_anlagen_afa_fliesst_konsistent_in_alle_reports(client: TestClient):
    headers = _onboarded_mandant(client)
    jahr = date.today().year
    anlage = _anlage(client, headers, jahr=jahr)

    euer = client.get(f"/berichte/euer?jahr={jahr}", headers=headers).json()
    assert float(euer["betriebsausgaben_netto"]) == 400.00
    assert euer["anzahl_ausgaben"] == 1
    assert float(euer["ueberschuss_netto"]) == -400.00

    susa = client.get(f"/berichte/susa?jahr={jahr}", headers=headers).json()
    konten = {konto["konto"]: konto for konto in susa["konten"]}
    assert float(susa["summe_soll"]) == float(susa["summe_haben"]) == 400.00
    assert float(konten["4830"]["soll"]) == 400.00
    assert float(konten["0490"]["haben"]) == 400.00

    bwa = client.get(f"/berichte/bwa?jahr={jahr}", headers=headers).json()
    assert float(bwa["kosten_gesamt"]) == 400.00
    assert bwa["kosten_posten"] == [
        {"konto": "4830", "bezeichnung": "Abschreibungen auf Sachanlagen", "betrag": "400.00"}
    ]

    csv_text = client.get(f"/berichte/datev-export?jahr={jahr}", headers=headers).content.decode("utf-8-sig")
    buchungen = list(csv.reader(io.StringIO(csv_text), delimiter=";"))[2:]
    assert len(buchungen) == 1
    assert buchungen[0][0] == "400,00"
    assert buchungen[0][1] == "S"
    assert buchungen[0][6] == "4830"
    assert buchungen[0][7] == "0490"
    assert buchungen[0][8] == ""
    assert buchungen[0][9] == "3112"
    assert buchungen[0][10] == anlage["id"][:8]

    wiederholt = client.get(f"/berichte/susa?jahr={jahr}", headers=headers).json()
    assert wiederholt["summe_soll"] == susa["summe_soll"]
    assert len(client.get(f"/anlagen?jahr={jahr}", headers=headers).json()["anlagen"]) == 1


def test_anlage_ausserhalb_des_nutzungszeitraums_erzeugt_keine_afa_buchung(client: TestClient):
    headers = _onboarded_mandant(client)
    jahr = date.today().year
    _anlage(client, headers, jahr=jahr)

    for zieljahr in (jahr - 1, jahr + 4):
        euer = client.get(f"/berichte/euer?jahr={zieljahr}", headers=headers).json()
        assert float(euer["betriebsausgaben_netto"]) == 0
        assert euer["anzahl_ausgaben"] == 0

        susa = client.get(f"/berichte/susa?jahr={zieljahr}", headers=headers).json()
        assert susa["konten"] == []

        csv_text = client.get(f"/berichte/datev-export?jahr={zieljahr}", headers=headers).content.decode("utf-8-sig")
        assert len(list(csv.reader(io.StringIO(csv_text), delimiter=";"))) == 2


def test_afa_reports_sind_mandantenisoliert(client: TestClient):
    jahr = date.today().year
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    _anlage(client, kevin_headers, jahr=jahr)

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    euer = client.get(f"/berichte/euer?jahr={jahr}", headers=lea_headers).json()
    assert float(euer["betriebsausgaben_netto"]) == 0
    assert client.get(f"/berichte/susa?jahr={jahr}", headers=lea_headers).json()["konten"] == []
