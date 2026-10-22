from fastapi.testclient import TestClient

from tests.test_invoices import _onboarded_mandant


def _produkt_payload(*, lagerbestand_aktiv: bool = True) -> dict:
    return {
        "bezeichnung": "Bio-Kaffeebohnen 1kg",
        "beschreibung": None,
        "einzelpreis": "18.50",
        "ust_satz": "7.00",
        "einheit": "Stück",
        "aktiv": True,
        "lagerbestand_aktiv": lagerbestand_aktiv,
    }


def _bewegung_payload(*, typ: str, menge: str, datum: str = "2026-09-01") -> dict:
    return {"datum": datum, "typ": typ, "menge": menge, "grund": "Testbuchung"}


def test_zugang_und_abgang_ergeben_richtigen_lagerbestand(client: TestClient):
    headers = _onboarded_mandant(client)
    produkt_id = client.post("/produkte", headers=headers, json=_produkt_payload()).json()["id"]

    zugang = client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="zugang", menge="10"),
    )
    assert zugang.status_code == 201
    assert zugang.json()["produkt_id"] == produkt_id

    abgang = client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="abgang", menge="3", datum="2026-09-02"),
    )
    assert abgang.status_code == 201

    produkte = client.get("/produkte", headers=headers).json()
    assert float(produkte[0]["lagerbestand"]) == 7.0


def test_abgang_ueber_bestand_wird_abgelehnt_und_nicht_gebucht(client: TestClient):
    headers = _onboarded_mandant(client)
    produkt_id = client.post("/produkte", headers=headers, json=_produkt_payload()).json()["id"]

    client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="zugang", menge="10"),
    )
    client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="abgang", menge="3", datum="2026-09-02"),
    )

    zu_viel = client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="abgang", menge="8", datum="2026-09-03"),
    )
    assert zu_viel.status_code == 400
    assert "Bestand" in zu_viel.json()["detail"]

    historie = client.get(f"/produkte/{produkt_id}/lagerbewegungen", headers=headers).json()
    assert len(historie) == 2


def test_abgang_darf_bestand_exakt_auf_null_bringen(client: TestClient):
    headers = _onboarded_mandant(client)
    produkt_id = client.post("/produkte", headers=headers, json=_produkt_payload()).json()["id"]

    client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="zugang", menge="5"),
    )
    genau_null = client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="abgang", menge="5", datum="2026-09-02"),
    )
    assert genau_null.status_code == 201

    produkte = client.get("/produkte", headers=headers).json()
    assert float(produkte[0]["lagerbestand"]) == 0.0


def test_lagerbestand_ist_null_wenn_tracking_deaktiviert(client: TestClient):
    headers = _onboarded_mandant(client)
    produkt_id = client.post("/produkte", headers=headers, json=_produkt_payload(lagerbestand_aktiv=False)).json()["id"]

    client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=headers,
        json=_bewegung_payload(typ="zugang", menge="10"),
    )

    produkte = client.get("/produkte", headers=headers).json()
    assert produkte[0]["lagerbestand"] is None
    assert produkte[0]["lagerbestand_aktiv"] is False


def test_lagerbewegungen_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    produkt_id = client.post("/produkte", headers=kevin_headers, json=_produkt_payload()).json()["id"]
    client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=kevin_headers,
        json=_bewegung_payload(typ="zugang", menge="10"),
    )

    lea_headers = _onboarded_mandant(client, email="lea@example.com")

    fremdes_produkt = client.get(f"/produkte/{produkt_id}/lagerbewegungen", headers=lea_headers)
    assert fremdes_produkt.status_code == 404

    fremde_buchung = client.post(
        f"/produkte/{produkt_id}/lagerbewegungen",
        headers=lea_headers,
        json=_bewegung_payload(typ="zugang", menge="1"),
    )
    assert fremde_buchung.status_code == 404
