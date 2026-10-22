from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app.bank import matching
from app.core.validierung import UngueltigerWert, land_iso, pruefe_iban, pruefe_leitweg_id, pruefe_ust_id
from app.db import SessionLocal
from app.invoices.kontakte import kontakt_iban_hash
from app.invoices.models import Kontakt
from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


# ---------------------------------------------------------------------------
# Pruefregeln


def test_iban_wird_normalisiert_und_pruefziffer_geprueft():
    assert pruefe_iban("de89 3704 0044 0532 0130 00") == "DE89370400440532013000"
    with pytest.raises(UngueltigerWert, match="Prüfziffer"):
        pruefe_iban("DE89370400440532013001")
    with pytest.raises(UngueltigerWert, match="22 Stellen"):
        pruefe_iban("DE8937040044053201300")


def test_ust_id_formate_je_land():
    assert pruefe_ust_id("de 123 456 789") == "DE123456789"
    assert pruefe_ust_id("ATU12345678") == "ATU12345678"
    assert pruefe_ust_id("CHE-123.456.789 MWST") == "CHE123456789MWST"
    with pytest.raises(UngueltigerWert, match="Format für DE"):
        pruefe_ust_id("DE12345")
    with pytest.raises(UngueltigerWert, match="Länderkürzel"):
        pruefe_ust_id("123456789")


def test_leitweg_id_aufbau_und_pruefziffer():
    assert pruefe_leitweg_id("04011000-1234512345-06") == "04011000-1234512345-06"
    assert pruefe_leitweg_id("04011000-12345-03") == "04011000-12345-03"
    with pytest.raises(UngueltigerWert, match="Prüfziffer"):
        pruefe_leitweg_id("04011000-12345-04")
    with pytest.raises(UngueltigerWert, match="Format"):
        pruefe_leitweg_id("ABC")


def test_land_namen_werden_zu_iso_codes():
    assert land_iso("Deutschland") == "DE"
    assert land_iso("Österreich") == "AT"
    assert land_iso("ch") == "CH"
    assert land_iso("") == "DE"
    with pytest.raises(UngueltigerWert, match="kenne ich nicht"):
        land_iso("Atlantis")


# ---------------------------------------------------------------------------
# API


def _voller_kontakt(**ueberschreiben) -> dict:
    daten = {
        "name": "Stadtwerke Musterstadt", "strasse": "Ring 1", "plz": "12345", "ort": "Musterstadt", "land": "DE",
        "typ": "beide", "anrede": "Frau", "vorname": "Erika", "nachname": "Muster", "telefon": "+49 30 123456",
        "notiz": "Bestellt quartalsweise", "steuernummer": "12/345/67890", "iban": "DE89 3704 0044 0532 0130 00",
        "bic": "COBADEFFXXX", "zahlungsziel_tage": 30, "skonto_prozent": "2.00", "skonto_tage": 10,
        "leitweg_id": "04011000-12345-03", "ust_id": "DE123456789", "email": "einkauf@example.com",
    }
    daten.update(ueberschreiben)
    return daten


def test_kontakt_mit_allen_neuen_feldern(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.post("/kontakte", headers=headers, json=_voller_kontakt())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["typ"] == "beide"
    assert body["iban"] == "DE89370400440532013000"
    assert body["bic"] == "COBADEFFXXX"
    assert body["zahlungsziel_tage"] == 30
    assert body["leitweg_id"] == "04011000-12345-03"
    assert body["archiviert"] is False

    with SessionLocal() as db:
        kontakt = db.get(Kontakt, body["id"])
        assert kontakt.iban_hash == kontakt_iban_hash(kontakt.mandant_id, "DE89370400440532013000")


def test_leere_felder_werden_none_und_ungueltige_iban_wird_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)
    leer = client.post("/kontakte", headers=headers, json={"name": "Leer GmbH", "email": "", "iban": " ", "ust_id": ""})
    assert leer.status_code == 201
    assert (leer.json()["email"], leer.json()["iban"], leer.json()["ust_id"]) == (None, None, None)

    falsch = client.post("/kontakte", headers=headers, json={"name": "X", "iban": "DE89370400440532013001"})
    assert falsch.status_code == 422
    assert "Prüfziffer" in str(falsch.json()["detail"])


def test_filter_nach_typ_und_archiv(client: TestClient):
    headers = _onboarded_mandant(client)
    kunde = client.post("/kontakte", headers=headers, json={"name": "Kunde AG"}).json()
    lieferant = client.post("/kontakte", headers=headers, json={"name": "Lieferant AG", "typ": "lieferant"}).json()
    beide = client.post("/kontakte", headers=headers, json={"name": "Beides AG", "typ": "beide"}).json()

    namen = lambda url: [k["name"] for k in client.get(url, headers=headers).json()]  # noqa: E731
    assert namen("/kontakte?typ=lieferant") == ["Beides AG", "Lieferant AG"]
    assert namen("/kontakte?typ=kunde") == ["Beides AG", "Kunde AG"]

    archiv = client.post(f"/kontakte/{kunde['id']}/archivieren", headers=headers)
    assert archiv.json()["archiviert"] is True
    assert namen("/kontakte") == ["Beides AG", "Lieferant AG"]
    assert namen("/kontakte?archiviert=true") == ["Kunde AG"]

    client.post(f"/kontakte/{kunde['id']}/wiederherstellen", headers=headers)
    assert namen("/kontakte") == ["Beides AG", "Kunde AG", "Lieferant AG"]
    assert lieferant and beide


def test_loeschen_nur_wenn_unbenutzt(client: TestClient):
    headers = _onboarded_mandant(client)
    unbenutzt = client.post("/kontakte", headers=headers, json={"name": "Nie benutzt"}).json()
    benutzt = _kontakt(client, headers)
    client.post("/invoices", headers=headers, json=_invoice_payload(benutzt))

    assert client.delete(f"/kontakte/{unbenutzt['id']}", headers=headers).status_code == 204
    gesperrt = client.delete(f"/kontakte/{benutzt}", headers=headers)
    assert gesperrt.status_code == 409
    assert "archivieren" in gesperrt.json()["detail"]


def test_patch_pflichtfeld_leer_und_iban_aendern(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt = client.post("/kontakte", headers=headers, json={"name": "Alt GmbH"}).json()

    assert client.patch(f"/kontakte/{kontakt['id']}", headers=headers, json={"name": None}).status_code == 400
    neu = client.patch(f"/kontakte/{kontakt['id']}", headers=headers, json={"iban": "DE02120300000000202051", "typ": "lieferant"})
    assert neu.status_code == 200
    with SessionLocal() as db:
        zeile = db.get(Kontakt, kontakt["id"])
        assert zeile.iban_hash == kontakt_iban_hash(zeile.mandant_id, "DE02120300000000202051")
        assert zeile.typ == "lieferant"
    client.patch(f"/kontakte/{kontakt['id']}", headers=headers, json={"iban": None})
    with SessionLocal() as db:
        assert db.get(Kontakt, kontakt["id"]).iban_hash is None


def test_fremder_mandant_kann_nicht_archivieren_oder_loeschen(client: TestClient):
    headers_a = _onboarded_mandant(client, "a@example.com")
    headers_b = _onboarded_mandant(client, "b@example.com")
    kontakt = client.post("/kontakte", headers=headers_a, json={"name": "Geheim GmbH"}).json()

    assert client.post(f"/kontakte/{kontakt['id']}/archivieren", headers=headers_b).status_code == 404
    assert client.delete(f"/kontakte/{kontakt['id']}", headers=headers_b).status_code == 404


def _xrechnung(client: TestClient, headers: dict, kontakt_id: str) -> tuple[etree._Element, dict]:
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
    resp = client.post(f"/invoices/{final['id']}/e-rechnung", headers=headers)
    assert resp.status_code == 200
    return etree.fromstring(resp.content), final


def test_xrechnung_kaeuferreferenz_aus_leitweg_id_sonst_kundennummer_sonst_nummer(client: TestClient):
    headers = _onboarded_mandant(client)
    behoerde = client.post("/kontakte", headers=headers, json=_voller_kontakt()).json()
    root, _ = _xrechnung(client, headers, behoerde["id"])
    kinder = [etree.QName(kind).localname for kind in root]
    assert kinder.index("BuyerReference") == kinder.index("DocumentCurrencyCode") + 1
    assert root.find(f"{{{CBC}}}BuyerReference").text == "04011000-12345-03"

    mit_nummer = client.post("/kontakte", headers=headers, json=_voller_kontakt(leitweg_id=None, kundennummer="K-77")).json()
    assert _xrechnung(client, headers, mit_nummer["id"])[0].find(f"{{{CBC}}}BuyerReference").text == "K-77"

    ohne = _kontakt(client, headers, email="einkauf@kunde.example")
    root, final = _xrechnung(client, headers, ohne)
    assert root.find(f"{{{CBC}}}BuyerReference").text == final["nummer"]


def test_produkt_artikelnummer(client: TestClient):
    headers = _onboarded_mandant(client)
    produkt = client.post(
        "/produkte", headers=headers,
        json={"bezeichnung": "Beratung", "einzelpreis": "90.00", "ust_satz": "19", "einheit": "Stunde", "artikelnummer": "B-01"},
    )
    assert produkt.status_code == 201
    assert produkt.json()["artikelnummer"] == "B-01"
    geaendert = client.patch(f"/produkte/{produkt.json()['id']}", headers=headers, json={"artikelnummer": "B-02"})
    assert geaendert.json()["artikelnummer"] == "B-02"


# ---------------------------------------------------------------------------
# Bankabgleich mit bekannter IBAN


def test_bekannte_iban_hilft_beim_eingang_macht_ihn_aber_nicht_sicher():
    umsatz = matching.Umsatz(
        "u1", date(2026, 10, 2), Decimal("1240.00"), "PayPal Europe", "Danke", iban_kontakt_ids=frozenset({"k1"}),
    )
    rechnung = matching.RechnungKandidat("r1", "RE-2026-0001", Decimal("1240.00"), "Beispiel Kunde GmbH", date(2026, 10, 10), kontakt_id="k1")
    vorschlag = matching.vorschlag_fuer_eingang(umsatz, [rechnung])
    assert vorschlag is not None
    assert vorschlag.sicher is False
    assert "IBAN bekannt (Kontakt Beispiel Kunde GmbH)" in vorschlag.gruende

    fremd = matching.Umsatz("u2", date(2026, 10, 2), Decimal("1240.00"), "PayPal Europe", "Danke")
    assert matching.vorschlag_fuer_eingang(fremd, [rechnung]) is None


def test_iban_eines_lieferanten_ordnet_ausgang_dem_beleg_zu():
    umsatz = matching.Umsatz(
        "u1", date(2026, 10, 20), Decimal("-49.90"), "ZAHLUNGSDIENST 4711", "Abo",
        iban_lieferanten=("Nordwind Hosting GmbH",),
    )
    beleg = matching.BelegKandidat("b1", "beleg", Decimal("49.90"), "Nordwind Hosting", date(2026, 9, 1), None)
    vorschlag = matching.vorschlag_fuer_ausgang(umsatz, [beleg])
    assert vorschlag is not None
    assert "IBAN gehört zu Lieferant Nordwind Hosting GmbH" in vorschlag.gruende


def test_bankabgleich_findet_kontakt_ueber_iban(client: TestClient):
    from tests.test_invoices import _onboarded_mandant as onboarded

    headers = onboarded(client)
    kontakt = client.post("/kontakte", headers=headers, json={**_voller_kontakt(iban="DE02120300000000202051"), "name": "Beispiel Kunde GmbH"}).json()
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt["id"])).json()
    client.post(f"/invoices/{draft['id']}/finalize", headers=headers)

    from app.bank.models import Bankumsatz
    from app.bank.service import berechne_vorschlaege

    with SessionLocal() as db:
        mandant_id = db.get(Kontakt, kontakt["id"]).mandant_id
        # Nicht gespeichert: berechne_vorschlaege liest nur die Felder.
        umsatz = Bankumsatz(
            id="u-test", mandant_id=mandant_id, buchungsdatum=date.today(),
            betrag=Decimal(draft["brutto_gesamt"]), gegenpartei_name="Zahlungsdienst",
            gegenpartei_iban="DE02 1203 0000 0000 2020 51", verwendungszweck="Danke",
        )
        vorschlag = berechne_vorschlaege(db, mandant_id, [umsatz])["u-test"]
        assert vorschlag.ziel_id == draft["id"]
        assert any("IBAN bekannt" in grund for grund in vorschlag.gruende)
