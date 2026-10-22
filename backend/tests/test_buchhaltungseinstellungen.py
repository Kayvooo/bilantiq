import pytest
from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant


def test_buchhaltungseinstellungen_liefern_defaults_und_lassen_sich_speichern(client: TestClient):
    headers = _onboarded_mandant(client)

    defaults = client.get("/buchhaltungseinstellungen", headers=headers)
    assert defaults.status_code == 200
    assert defaults.json() == {
        "standard_zahlungsziel_tage": 14,
        "standard_ust_satz": "19.00",
        "kleinunternehmer": False,
    }

    gespeichert = client.put(
        "/buchhaltungseinstellungen",
        headers=headers,
        json={
            "standard_zahlungsziel_tage": 30,
            "standard_ust_satz": "7.00",
            "kleinunternehmer": True,
        },
    )
    assert gespeichert.status_code == 200
    assert gespeichert.json()["standard_zahlungsziel_tage"] == 30
    assert gespeichert.json()["standard_ust_satz"] == "7.00"
    assert gespeichert.json()["kleinunternehmer"] is True
    assert client.get("/buchhaltungseinstellungen", headers=headers).json() == gespeichert.json()


def test_buchhaltungseinstellungen_sind_mandantenisoliert(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    client.put(
        "/buchhaltungseinstellungen",
        headers=kevin_headers,
        json={
            "standard_zahlungsziel_tage": 45,
            "standard_ust_satz": "16.00",
            "kleinunternehmer": False,
        },
    )

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    assert client.get("/buchhaltungseinstellungen", headers=lea_headers).json() == {
        "standard_zahlungsziel_tage": 14,
        "standard_ust_satz": "19.00",
        "kleinunternehmer": False,
    }
    client.put(
        "/buchhaltungseinstellungen",
        headers=lea_headers,
        json={
            "standard_zahlungsziel_tage": 5,
            "standard_ust_satz": "0.00",
            "kleinunternehmer": True,
        },
    )
    assert client.get("/buchhaltungseinstellungen", headers=kevin_headers).json()["standard_zahlungsziel_tage"] == 45


@pytest.mark.parametrize(
    "payload",
    [
        {"standard_zahlungsziel_tage": -1, "standard_ust_satz": "19.00", "kleinunternehmer": False},
        {"standard_zahlungsziel_tage": 366, "standard_ust_satz": "19.00", "kleinunternehmer": False},
        {"standard_zahlungsziel_tage": 14, "standard_ust_satz": "100.01", "kleinunternehmer": False},
    ],
)
def test_ungueltige_buchhaltungseinstellungen_werden_abgelehnt(client: TestClient, payload: dict):
    headers = _onboarded_mandant(client)
    assert client.put("/buchhaltungseinstellungen", headers=headers, json=payload).status_code == 422
