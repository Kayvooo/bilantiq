"""Altrechnungen in EÜR, UStVA, Dashboard, Cashflow, DATEV und Bankabgleich."""
import json
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.test_altrechnungen_import import _kunde, _post
from tests.test_bank import CAMT, KONTO_IBAN, _import, _konto, _umsaetze
from tests.test_invoices import _onboarded_mandant

D = Decimal
HEUTE = date.today()
VORJAHR = date(HEUTE.year - 1, 12, 31)


def _d(tage: int) -> str:
    return (HEUTE + timedelta(days=tage)).strftime("%d.%m.%Y")


KOPF = "Nr;Datum;Kundennr;Kunde;Fällig;Netto;USt;Brutto;N19;N7;Offen;Status\n"
ZUORDNUNG = {
    "rechnungsnummer": "Nr", "rechnungsdatum": "Datum", "kundennummer": "Kundennr", "kunde": "Kunde", "faelligkeit": "Fällig",
    "netto": "Netto", "ust": "USt", "brutto": "Brutto", "netto_19": "N19", "netto_7": "N7", "offener_betrag": "Offen", "status": "Status",
}
LISTE = (
    KOPF
    + f"RE-A1;{_d(-90)};K-1;Müller GmbH;{_d(-30)};500,00;95,00;595,00;;;;offen\n"               # 19 %, ueberfaellig
    + f"RE-A2;{_d(-60)};K-1;Müller GmbH;{_d(10)};;;172,50;100,00;50,00;;offen\n"               # 19 % und 7 %
    + f"RE-A3;{_d(-400)};K-1;Müller GmbH;{_d(-370)};1000,00;190,00;1190,00;;;;bezahlt\n"       # im Altsystem bezahlt
    + f"RE-A4;{_d(-500)};K-1;Müller GmbH;{_d(-470)};100,00;19,00;119,00;;;;offen\n"            # wird fuers Vorjahr bezahlt
).encode()


def _aufbau(client: TestClient) -> tuple[dict, dict]:
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    antwort = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, {"zuordnung": ZUORDNUNG})
    assert antwort.status_code == 200, antwort.text
    eintraege = client.get("/altrechnungen", headers=headers).json()["eintraege"]
    return headers, {e["nummer"]: e["id"] for e in eintraege}


def _zahle(client, headers, rechnung_id, **json_):
    antwort = client.post(f"/altrechnungen/{rechnung_id}/zahlung", headers=headers, json=json_)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


def _euer(client, headers, jahr=HEUTE.year) -> dict:
    return client.get("/berichte/euer", headers=headers, params={"jahr": jahr}).json()


def _ustva(client, headers) -> dict:
    return client.get("/berichte/ustva", headers=headers, params={"jahr": HEUTE.year, "zeitraum_typ": "monat", "periode": HEUTE.month}).json()


def test_ohne_zahlung_in_bilantiq_zaehlt_keine_altrechnung_als_einnahme_aber_als_forderung(client: TestClient):
    headers, _ = _aufbau(client)
    euer = _euer(client, headers)
    assert D(euer["betriebseinnahmen_netto"]) == 0 and euer["anzahl_einnahmen"] == 0  # auch nicht die im Altsystem bezahlte
    assert D(euer["offene_forderungen_brutto"]) == D("886.50")  # 595 + 172,50 + 119, die bezahlte RE-A3 fehlt
    ustva = _ustva(client, headers)
    assert D(ustva["umsatz_19_netto"]) == 0 and D(ustva["umsatzsteuer_gesamt"]) == 0 and ustva["anzahl_rechnungen"] == 0
    dashboard = client.get("/berichte/dashboard", headers=headers).json()
    assert dashboard["faellige_rechnungen"]["anzahl"] == 2 and D(dashboard["faellige_rechnungen"]["betrag"]) == D("714.00")
    assert dashboard["offene_rechnungen"]["anzahl"] == 1 and D(dashboard["offene_rechnungen"]["betrag"]) == D("172.50")
    assert D(dashboard["einnahmen"]) == 0 and D(dashboard["umsatz_brutto_jahr"]) == 0 and dashboard["top_kunden"] == []


def test_zahlung_zaehlt_im_zahlungsmonat_netto_und_ust_je_steuersatz(client: TestClient):
    headers, ids = _aufbau(client)
    _zahle(client, headers, ids["RE-A1"])  # ganz, heute
    _zahle(client, headers, ids["RE-A2"], betrag="86.25")  # genau die Haelfte

    euer = _euer(client, headers)
    assert D(euer["betriebseinnahmen_netto"]) == D("500.00") + D("75.00") and euer["anzahl_einnahmen"] == 2
    assert D(euer["offene_forderungen_brutto"]) == D("86.25") + D("119.00")

    ustva = _ustva(client, headers)
    assert (D(ustva["umsatz_19_netto"]), D(ustva["umsatzsteuer_19"])) == (D("550.00"), D("104.50"))  # 500 + 50, 95 + 9,50
    assert (D(ustva["umsatz_7_netto"]), D(ustva["umsatzsteuer_7"])) == (D("25.00"), D("1.75"))
    assert D(ustva["umsatzsteuer_gesamt"]) == D("106.25") and ustva["anzahl_rechnungen"] == 2

    dashboard = client.get("/berichte/dashboard", headers=headers).json()
    assert D(dashboard["einnahmen"]) == D("575.00")
    assert D(dashboard["monatswerte"][HEUTE.month - 1]["einnahmen"]) == D("575.00")
    assert D(dashboard["umsatz_brutto_jahr"]) == D("595.00") + D("86.25")
    assert dashboard["top_kunden"] == [{"name": "Müller GmbH", "betrag": "681.25"}]
    assert dashboard["faellige_rechnungen"]["anzahl"] == 1 and D(dashboard["faellige_rechnungen"]["betrag"]) == D("119.00")
    assert D(dashboard["offene_rechnungen"]["betrag"]) == D("86.25")


def test_zahlung_im_vorjahr_zaehlt_nur_im_vorjahr(client: TestClient):
    headers, ids = _aufbau(client)
    _zahle(client, headers, ids["RE-A4"], datum=VORJAHR.isoformat())
    assert D(_euer(client, headers, HEUTE.year - 1)["betriebseinnahmen_netto"]) == D("100.00")
    assert D(_euer(client, headers)["betriebseinnahmen_netto"]) == 0


def test_cashflow_nutzt_faelligkeit_und_restbetrag(client: TestClient):
    headers, ids = _aufbau(client)
    vorher = client.get("/berichte/cashflow", headers=headers).json()
    assert vorher["ueberfaellige_rechnungen_anzahl"] == 2 and D(vorher["ueberfaellige_rechnungen_betrag"]) == D("714.00")
    assert D(vorher["wochen"][1]["erwarteter_zufluss"]) == D("172.50")  # RE-A2 in zehn Tagen
    _zahle(client, headers, ids["RE-A2"], betrag="72.50")
    assert D(client.get("/berichte/cashflow", headers=headers).json()["wochen"][1]["erwarteter_zufluss"]) == D("100.00")
    _zahle(client, headers, ids["RE-A1"])
    nachher = client.get("/berichte/cashflow", headers=headers).json()
    assert nachher["ueberfaellige_rechnungen_anzahl"] == 1 and D(nachher["ueberfaellige_rechnungen_betrag"]) == D("119.00")


def test_datev_export_bucht_zahlungen_auf_altrechnungen_mit_alter_nummer(client: TestClient):
    headers, ids = _aufbau(client)
    _zahle(client, headers, ids["RE-A1"])
    _zahle(client, headers, ids["RE-A2"])
    csv_text = client.get("/berichte/datev-export", headers=headers, params={"jahr": HEUTE.year}).content.decode("utf-8-sig")
    zeilen = [z for z in csv_text.splitlines() if "Altrechnung" in z]
    assert len(zeilen) == 3  # RE-A1 (19 %) und RE-A2 (19 % und 7 %), je Steuersatz eine Zeile
    a1 = next(z for z in zeilen if "RE-A1" in z)
    assert '"595,00"' in a1 and '"8400"' in a1 and '"RE-A1"' in a1 and HEUTE.strftime("%d%m") in a1
    assert {'"8300"', '"8400"'} <= {s for z in zeilen if "RE-A2" in z for s in z.split(";") if s in ('"8300"', '"8400"')}
    susa = client.get("/berichte/susa", headers=headers, params={"jahr": HEUTE.year}).json()
    assert any(k["konto"] == "8400" for k in susa["konten"])


def test_mandant_sieht_nur_eigene_zahlungen_in_den_berichten(client: TestClient):
    headers, ids = _aufbau(client)
    _zahle(client, headers, ids["RE-A1"])
    anna = _onboarded_mandant(client, email="anna@example.com")
    assert D(_euer(client, anna)["betriebseinnahmen_netto"]) == 0
    assert D(_euer(client, anna)["offene_forderungen_brutto"]) == 0


# ---------------------------------------------------------------------------
# Bankabgleich


def _camt_fuer(nummer: str) -> bytes:
    return CAMT.replace(b"RE-2026-0001", nummer.encode())


def test_bankabgleich_schlaegt_offene_altrechnung_vor_und_bestaetigt_mit_buchungsdatum(client: TestClient):
    # Brutto 1240,00 ist der Betrag der Beispiel-Zahlung. Netto/USt fehlen, deshalb Brutto + Satz ableiten:
    headers = _onboarded_mandant(client)
    _kunde(client, headers, name="Beispiel Kunde GmbH", kundennummer="K-1")
    liste = (KOPF + f"RE-ALT-7;{_d(-40)};K-1;Beispiel Kunde GmbH;{_d(-10)};1042,02;197,98;1240,00;;;;offen\n").encode()
    assert _post(client, headers, "/stammdaten/rechnungen/import", liste, {"zuordnung": ZUORDNUNG}).status_code == 200
    konto = _konto(client, headers, iban=KONTO_IBAN)
    assert _import(client, headers, konto["id"], _camt_fuer("RE-ALT-7")).status_code == 201

    eingang = next(u for u in _umsaetze(client, headers) if D(u["betrag"]) > 0)
    assert eingang["vorschlag"]["typ"] == "altrechnung" and eingang["vorschlag"]["sicher"] is True
    assert "RE-ALT-7" in eingang["vorschlag"]["anzeige"]
    antwort = client.post("/bank/zuordnungen/bestaetigen", headers=headers, json={"umsatz_ids": [eingang["id"]]})
    assert antwort.json() == {"bestaetigt": 1, "uebersprungen": []}

    rechnung = client.get("/altrechnungen", headers=headers).json()["eintraege"][0]
    assert (rechnung["status"], rechnung["offen"]) == ("bezahlt", "0.00")
    assert rechnung["zahlungen"][0]["datum"] == "2026-10-02" and rechnung["zahlungen"][0]["quelle"] == "bankabgleich"
    [zugeordnet] = _umsaetze(client, headers, "zugeordnet")
    assert (zugeordnet["zuordnung_typ"], zugeordnet["zuordnung_id"]) == ("altrechnung", rechnung["id"])
    # Die Zahlung zaehlt jetzt in der EÜR des Jahres 2026 mit 1042,02 netto.
    assert D(_euer(client, headers, 2026)["betriebseinnahmen_netto"]) == D("1042.02")
    aufheben = client.post(f"/bank/umsaetze/{zugeordnet['id']}/zuordnung-aufheben", headers=headers)
    assert aufheben.status_code == 400 and "nicht zurücknehmen" in aufheben.json()["detail"]


def test_bankzahlung_darf_eine_teilzahlung_sein_aber_nie_mehr_als_offen(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, name="Beispiel Kunde GmbH", kundennummer="K-1")
    liste = (
        KOPF
        + f"RE-GROSS;{_d(-40)};K-1;Beispiel Kunde GmbH;{_d(-10)};1260,50;239,50;1500,00;;;;offen\n"
        + f"RE-KLEIN;{_d(-40)};K-1;Beispiel Kunde GmbH;{_d(-10)};84,03;15,97;100,00;;;;offen\n"
    ).encode()
    assert _post(client, headers, "/stammdaten/rechnungen/import", liste, {"zuordnung": ZUORDNUNG}).status_code == 200
    konto = _konto(client, headers, iban=KONTO_IBAN)
    assert _import(client, headers, konto["id"], CAMT).status_code == 201
    eingang = next(u for u in _umsaetze(client, headers) if D(u["betrag"]) > 0)
    ids = {e["nummer"]: e["id"] for e in client.get("/altrechnungen", headers=headers).json()["eintraege"]}

    zu_viel = client.post(f"/bank/umsaetze/{eingang['id']}/zuordnen", headers=headers, json={"typ": "altrechnung", "ziel_id": ids["RE-KLEIN"]})
    assert zu_viel.status_code == 400 and "höher als der offene Betrag" in zu_viel.json()["detail"]
    teil = client.post(f"/bank/umsaetze/{eingang['id']}/zuordnen", headers=headers, json={"typ": "altrechnung", "ziel_id": ids["RE-GROSS"]})
    assert teil.status_code == 200, teil.text
    gross = next(e for e in client.get("/altrechnungen", headers=headers).json()["eintraege"] if e["nummer"] == "RE-GROSS")
    assert (gross["status"], gross["offen"]) == ("ueberfaellig", "260.00")
