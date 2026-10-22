from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _vorlage_payload(kontakt_id: str, *, naechstes_datum: str, intervall: str = "monatlich", enddatum: str | None = None) -> dict:
    return {
        "kontakt_id": kontakt_id,
        "bezeichnung": "Hosting-Abo",
        "intervall": intervall,
        "naechstes_datum": naechstes_datum,
        "enddatum": enddatum,
        "positionen": [{"beschreibung": "Hosting", "menge": "1", "einzelpreis": "49.00", "ust_satz": "19.00"}],
    }


def test_create_and_list_wiederkehrende_rechnung(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    resp = client.post("/wiederkehrende-rechnungen", headers=headers, json=_vorlage_payload(kontakt_id, naechstes_datum="2026-10-01"))
    assert resp.status_code == 201
    body = resp.json()
    assert body["kontakt_name"] == "Beispiel Kunde GmbH"
    assert body["aktiv"] is True

    liste = client.get("/wiederkehrende-rechnungen", headers=headers).json()
    assert len(liste) == 1


def test_erzeugen_erstellt_entwurf_und_verschiebt_naechsten_termin(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-rechnungen", headers=headers, json=_vorlage_payload(kontakt_id, naechstes_datum=gestern))

    resp = client.post("/wiederkehrende-rechnungen/erzeugen", headers=headers)
    assert resp.status_code == 200
    ergebnis = resp.json()
    assert ergebnis["anzahl"] == 1

    rechnung = client.get(f"/invoices/{ergebnis['erzeugte_rechnungen'][0]}", headers=headers).json()
    assert rechnung["status"] == "entwurf"  # nie automatisch final
    assert float(rechnung["netto_gesamt"]) == 49.00

    vorlage = client.get("/wiederkehrende-rechnungen", headers=headers).json()[0]
    erwartetes_naechstes = _add_one_month(gestern)
    assert vorlage["naechstes_datum"] == erwartetes_naechstes


def _add_one_month(iso_date: str) -> str:
    jahr, monat, tag = (int(part) for part in iso_date.split("-"))
    if monat == 12:
        jahr, monat = jahr + 1, 1
    else:
        monat += 1
    import calendar
    tag = min(tag, calendar.monthrange(jahr, monat)[1])
    return f"{jahr:04d}-{monat:02d}-{tag:02d}"


def test_erzeugen_ist_idempotent_ohne_faellige_vorlagen(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    morgen = (date.today() + timedelta(days=1)).isoformat()
    client.post("/wiederkehrende-rechnungen", headers=headers, json=_vorlage_payload(kontakt_id, naechstes_datum=morgen))

    resp = client.post("/wiederkehrende-rechnungen/erzeugen", headers=headers).json()
    assert resp["anzahl"] == 0


def test_vorlage_deaktiviert_sich_nach_enddatum(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    client.post(
        "/wiederkehrende-rechnungen", headers=headers,
        json=_vorlage_payload(kontakt_id, naechstes_datum=gestern, enddatum=gestern),
    )

    client.post("/wiederkehrende-rechnungen/erzeugen", headers=headers)
    vorlage = client.get("/wiederkehrende-rechnungen", headers=headers).json()[0]
    assert vorlage["aktiv"] is False


def test_deaktivieren_stoppt_weitere_erzeugung(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    gestern = (date.today() - timedelta(days=1)).isoformat()
    vorlage = client.post("/wiederkehrende-rechnungen", headers=headers, json=_vorlage_payload(kontakt_id, naechstes_datum=gestern)).json()

    client.post(f"/wiederkehrende-rechnungen/{vorlage['id']}/deaktivieren", headers=headers)
    ergebnis = client.post("/wiederkehrende-rechnungen/erzeugen", headers=headers).json()
    assert ergebnis["anzahl"] == 0


def test_wiederkehrende_rechnung_enddatum_vor_start_wird_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    resp = client.post(
        "/wiederkehrende-rechnungen", headers=headers,
        json=_vorlage_payload(kontakt_id, naechstes_datum="2026-10-01", enddatum="2026-09-01"),
    )
    assert resp.status_code == 400


def test_wiederkehrende_rechnungen_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_kontakt = _kontakt(client, kevin_headers)
    client.post("/wiederkehrende-rechnungen", headers=kevin_headers, json=_vorlage_payload(kevin_kontakt, naechstes_datum="2026-10-01"))

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get("/wiederkehrende-rechnungen", headers=lea_headers).json()
    assert resp == []
