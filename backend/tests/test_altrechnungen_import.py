import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.altrechnungen import storage
from app.altrechnungen.models import Altrechnung
from app.altrechnungen.steuer import SteuerFehler, bestimme_anteile, verteile_zahlung
from app.config import settings
from app.db import SessionLocal
from app.invoices.models import Kontakt
from tests.test_benutzerverwaltung import _register_and_verify
from tests.test_invoices import _invoice_payload, _onboarded_mandant

D = Decimal


# ---------------------------------------------------------------------------
# Steuerlogik


def test_satz_wird_aus_netto_und_brutto_abgeleitet():
    brutto, anteile = bestimme_anteile(netto=D("1000.00"), ust=None, brutto=D("1190.00"), satz=None, netto_je_satz={})
    assert brutto == D("1190.00")
    assert [(a.satz, a.netto, a.ust) for a in anteile] == [(D("19.00"), D("1000.00"), D("190.00"))]
    _, sieben = bestimme_anteile(netto=None, ust=D("7.00"), brutto=D("107.00"), satz=None, netto_je_satz={})
    assert sieben[0].satz == D("7.00") and sieben[0].netto == D("100.00")
    _, null = bestimme_anteile(netto=D("50.00"), ust=D("0"), brutto=D("50.00"), satz=None, netto_je_satz={})
    assert null[0].satz == D("0.00") and null[0].ust == D("0.00")


def test_gemischte_saetze_werden_abgelehnt_statt_geraten():
    with pytest.raises(SteuerFehler, match="gemischte Steuersätze"):
        bestimme_anteile(netto=D("150.00"), ust=None, brutto=D("169.00"), satz=None, netto_je_satz={})
    with pytest.raises(SteuerFehler, match="Betrag fehlt"):
        bestimme_anteile(netto=None, ust=None, brutto=None, satz=None, netto_je_satz={})


def test_netto_je_satz_und_gegenprobe_gegen_brutto():
    brutto, anteile = bestimme_anteile(
        netto=None, ust=None, brutto=D("172.50"), satz=None, netto_je_satz={D("19"): D("100.00"), D("7"): D("50.00")},
    )
    assert brutto == D("172.50")
    assert sum((a.brutto for a in anteile), D("0")) == D("172.50")
    with pytest.raises(SteuerFehler, match="ergeben"):
        bestimme_anteile(netto=None, ust=None, brutto=D("200.00"), satz=None, netto_je_satz={D("19"): D("100.00"), D("7"): D("50.00")})


def test_angegebener_satz_wird_gegen_die_betraege_geprueft_und_2020er_saetze_sind_erlaubt():
    _, anteile = bestimme_anteile(netto=D("100.00"), ust=None, brutto=D("116.00"), satz=D("16"), netto_je_satz={})
    assert anteile[0].satz == D("16.00")
    with pytest.raises(SteuerFehler, match="passt nicht"):
        bestimme_anteile(netto=D("100.00"), ust=None, brutto=D("107.00"), satz=D("19"), netto_je_satz={})
    with pytest.raises(SteuerFehler, match="kein deutscher Steuersatz"):
        bestimme_anteile(netto=D("100.00"), ust=None, brutto=D("112.00"), satz=D("12"), netto_je_satz={})


def test_zahlung_wird_im_verhaeltnis_auf_die_steuersaetze_verteilt():
    _, anteile = bestimme_anteile(
        netto=None, ust=None, brutto=D("172.50"), satz=None, netto_je_satz={D("19"): D("100.00"), D("7"): D("50.00")},
    )
    voll = verteile_zahlung(anteile, D("172.50"))
    assert sum((a.netto for a in voll), D("0")) == D("150.00") and sum((a.ust for a in voll), D("0")) == D("22.50")
    halb = verteile_zahlung(anteile, D("86.25"))
    assert sum((a.brutto for a in halb), D("0")) == D("86.25")
    assert {a.satz: a.netto for a in halb} == {D("19.00"): D("50.00"), D("7.00"): D("25.00")}
    assert verteile_zahlung(anteile, D("0")) == []


# ---------------------------------------------------------------------------
# Import

KOPF = "Rechnungsnr.;Datum;Kundennr.;Kunde;Fällig;Netto;USt;Brutto;Status\n"
ZUORDNUNG = {
    "rechnungsnummer": "Rechnungsnr.", "rechnungsdatum": "Datum", "kundennummer": "Kundennr.", "kunde": "Kunde",
    "faelligkeit": "Fällig", "netto": "Netto", "ust": "USt", "brutto": "Brutto", "status": "Status",
}
LISTE = (
    KOPF
    + "RE-2024-0001;15.03.2024;K-1;Müller GmbH;14.04.2024;1000,00;190,00;1190,00;bezahlt\n"
    + "RE-2024-0002;01.10.2025;K-1;Müller GmbH;;500,00;95,00;595,00;offen\n"
    + "RE-2024-0003;05.11.2025;;Müller GmbH;05.12.2025;100,00;7,00;107,00;offen\n"
).encode("utf-8")


def _post(client, headers, pfad, daten: bytes, optionen: dict | None = None, dateiname="rechnungen.csv"):
    form = {"optionen": json.dumps(optionen)} if optionen is not None else {}
    return client.post(pfad, headers=headers, files={"file": (dateiname, daten, "text/csv")}, data=form)


def _opt(**extra) -> dict:
    return {"zuordnung": ZUORDNUNG, **extra}


def _kunde(client, headers, name="Müller GmbH", **extra) -> str:
    antwort = client.post("/kontakte", headers=headers, json={"name": name, "plz": "01067", "ort": "Dresden", **extra})
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


def test_vorschau_schlaegt_die_spalten_der_rechnungsliste_vor(client: TestClient):
    headers = _onboarded_mandant(client)
    antwort = _post(client, headers, "/stammdaten/rechnungen/import/vorschau", LISTE)
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["vorgeschlagene_zuordnung"] == ZUORDNUNG


def test_probelauf_zeigt_offene_betraege_und_legt_nichts_an(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    antwort = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", LISTE, _opt())
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    assert (body["neu"], body["fehler"], body["doppelt"], body["vorhanden"]) == (3, 0, 0, 0)
    hinweise = {z["nummer"]: " ".join(z["hinweise"]) for z in body["zeilen"]}
    assert "Rechnungsdatum plus 14 Tage" in hinweise[3]  # Zeile ohne Faelligkeit
    beispiel = {b["Rechnungsnummer"]: b for b in body["beispiele"]}
    assert beispiel["RE-2024-0001"]["Offener Betrag"] == "0,00"  # bezahlt
    assert beispiel["RE-2024-0002"]["Offener Betrag"] == "595,00"
    assert beispiel["RE-2024-0002"]["Rechnungsdatum"] == "01.10.2025"
    with SessionLocal() as db:
        assert db.query(Altrechnung).count() == 0


def test_import_legt_altrechnungen_an_und_zeigt_offene_nur_wo_offen(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kunde(client, headers, kundennummer="K-1")
    antwort = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt(zahlungsziel_tage=30))
    assert antwort.status_code == 200, antwort.text
    with SessionLocal() as db:
        nach_nummer = {a.nummer: a for a in db.query(Altrechnung).all()}
        assert set(nach_nummer) == {"RE-2024-0001", "RE-2024-0002", "RE-2024-0003"}
        bezahlt, offen, sieben = (nach_nummer[n] for n in ("RE-2024-0001", "RE-2024-0002", "RE-2024-0003"))
        assert bezahlt.offen_beim_import == D("0.00") and bezahlt.brutto == D("1190.00")
        assert offen.offen_beim_import == D("595.00")
        assert offen.faelligkeit.isoformat() == "2025-10-31"  # Rechnungsdatum + 30 Tage
        assert all(a.kontakt_id == kontakt_id for a in nach_nummer.values())
        assert json.loads(sieben.steueranteile) == [{"satz": "7.00", "netto": "100.00", "ust": "7.00"}]


def test_quelldatei_bleibt_verschluesselt_als_nachweis_erhalten(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    antwort = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt())
    assert antwort.status_code == 200, antwort.text
    protokoll = client.get("/stammdaten/importe", headers=headers).json()[0]
    assert protokoll["ziel"] == "rechnungen"
    dateien = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(dateien) == 1 and dateien[0].name.startswith("import-")
    assert b"RE-2024-0001" not in dateien[0].read_bytes()  # Ciphertext, nicht die CSV
    from app.stammdaten.models import Datenimport

    with SessionLocal() as db:
        referenz = db.query(Datenimport).one().datei_referenz
    assert storage.lies(referenz) == LISTE


def test_fehlende_kunden_blockieren_oder_werden_auf_wunsch_angelegt(client: TestClient):
    headers = _onboarded_mandant(client)
    probe = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", LISTE, _opt()).json()
    assert probe["fehler"] == 3
    assert "gibt es noch nicht" in probe["zeilen"][0]["fehler"][0]

    angelegt = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt(fehlende_kunden_anlegen=True))
    assert angelegt.status_code == 200, angelegt.text
    kontakte = client.get("/kontakte", headers=headers).json()
    # K-1 und der Kunde ohne Kundennummer (nur Name "Müller GmbH") sind verschiedene Schluessel: zwei Kontakte.
    assert sorted(k["name"] for k in kontakte) == ["Müller GmbH", "Müller GmbH"]


def test_kundennummer_mit_anderem_namen_ist_ein_fehler(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, name="Ganz Anders AG", kundennummer="K-1")
    probe = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", LISTE, _opt()).json()
    assert "gehört zu „Ganz Anders AG“" in probe["zeilen"][0]["fehler"][0]


def test_ablehnungen_negativ_gemischt_entwurf_unbekannter_status_teilzahlung(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    liste = (
        KOPF
        + "R1;01.02.2025;K-1;Müller GmbH;;-100,00;-19,00;-119,00;offen\n"      # Gutschrift
        + "R2;01.02.2025;K-1;Müller GmbH;;150,00;;169,00;offen\n"              # gemischte Saetze
        + "R3;01.02.2025;K-1;Müller GmbH;;100,00;19,00;119,00;entwurf\n"
        + "R4;01.02.2025;K-1;Müller GmbH;;100,00;19,00;119,00;vielleicht\n"
        + "R5;01.02.2025;K-1;Müller GmbH;;100,00;19,00;119,00;teilbezahlt\n"
    ).encode()
    zeilen = {z["nummer"]: " ".join(z["fehler"]) for z in _post(client, headers, "/stammdaten/rechnungen/import/pruefen", liste, _opt()).json()["zeilen"]}
    assert "Gutschriften" in zeilen[2]
    assert "gemischte Steuersätze" in zeilen[3]
    assert "Entwürfe" in zeilen[4]
    assert "kenne ich nicht" in zeilen[5]
    assert "Offener Betrag" in zeilen[6]


def test_teilzahlung_mit_offenem_betrag_und_netto_je_satz_und_2020er_satz(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    liste = (
        "Nr;Datum;Kundennr;Brutto;Offen;N19;N7;Satz\n"
        "A1;01.02.2025;K-1;119,00;19,00;;;19\n"                 # Teilzahlung: 100 bezahlt, 19 offen
        "A2;01.02.2025;K-1;172,50;172,50;100,00;50,00;\n"       # Netto je Satz
        "A3;01.08.2020;K-1;116,00;0;;;16\n"                      # 16 % aus dem zweiten Halbjahr 2020
    ).encode()
    zuordnung = {
        "rechnungsnummer": "Nr", "rechnungsdatum": "Datum", "kundennummer": "Kundennr", "brutto": "Brutto",
        "offener_betrag": "Offen", "netto_19": "N19", "netto_7": "N7", "ust_satz": "Satz",
    }
    antwort = _post(client, headers, "/stammdaten/rechnungen/import", liste, {"zuordnung": zuordnung})
    assert antwort.status_code == 200, antwort.text
    with SessionLocal() as db:
        daten = {a.nummer: a for a in db.query(Altrechnung).all()}
        assert daten["A1"].offen_beim_import == D("19.00")
        assert {e["satz"] for e in json.loads(daten["A2"].steueranteile)} == {"19.00", "7.00"}
        assert json.loads(daten["A3"].steueranteile)[0]["satz"] == "16.00"
        assert daten["A3"].offen_beim_import == D("0.00")


def test_dubletten_in_der_datei_im_bestand_und_andere_schreibweise(client: TestClient):
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    liste = (LISTE.decode() + "RE 2024 0002;02.10.2025;K-1;Müller GmbH;;1,00;0,19;1,19;offen\n").encode()
    probe = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", liste, _opt()).json()
    assert probe["doppelt"] == 1 and probe["neu"] == 3
    assert "Zeile 3" in next(z for z in probe["zeilen"] if z["status"] == "doppelt")["grund"]

    assert _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt()).status_code == 200
    nochmal = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", LISTE, _opt()).json()
    assert (nochmal["vorhanden"], nochmal["neu"]) == (3, 0)
    leer = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt())
    assert leer.status_code == 400 and "Nichts zu importieren" in leer.json()["detail"]


def test_nummer_einer_bilantiq_rechnung_wird_nicht_ueberschrieben(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kunde(client, headers, kundennummer="K-1")
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    nummer = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()["nummer"]
    liste = (KOPF + f"{nummer};01.02.2025;K-1;Müller GmbH;;100,00;19,00;119,00;offen\n").encode()
    probe = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", liste, _opt()).json()
    assert "gibt es schon als Rechnung in Bilantiq" in probe["zeilen"][0]["fehler"][0]


def test_pflichtspalten_muessen_zugeordnet_sein(client: TestClient):
    headers = _onboarded_mandant(client)
    ohne_betrag = {k: v for k, v in ZUORDNUNG.items() if k not in ("netto", "ust", "brutto")}
    antwort = _post(client, headers, "/stammdaten/rechnungen/import/pruefen", LISTE, {"zuordnung": ohne_betrag})
    assert antwort.status_code == 400 and "Betrag" in antwort.json()["detail"]


def test_rueckgaengig_entfernt_altrechnungen_neue_kunden_und_quelldatei(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers = _onboarded_mandant(client)
    importiert = _post(client, headers, "/stammdaten/rechnungen/import", LISTE, _opt(fehlende_kunden_anlegen=True)).json()
    zurueck = client.post(f"/stammdaten/importe/{importiert['import_id']}/rueckgaengig", headers=headers)
    assert zurueck.status_code == 200, zurueck.text
    assert zurueck.json() == {"geloescht": 5, "behalten": 0}  # 3 Altrechnungen und 2 neue Kontakte
    with SessionLocal() as db:
        assert db.query(Altrechnung).count() == 0 and db.query(Kontakt).count() == 0
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_mitglied_darf_nicht_importieren_und_mandanten_sind_getrennt(client: TestClient):
    kevin = _onboarded_mandant(client, email="kevin@example.com")
    _kunde(client, kevin, kundennummer="K-1")
    assert _post(client, kevin, "/stammdaten/rechnungen/import", LISTE, _opt()).status_code == 200
    code = client.post("/auth/einladungen", headers=kevin, json={"rolle": "mitglied"}).json()["code"]
    mitglied = _register_and_verify(client, "mitglied@example.com", einladungscode=code)
    assert _post(client, mitglied, "/stammdaten/rechnungen/import/vorschau", LISTE).status_code == 403

    anna = _onboarded_mandant(client, email="anna@example.com")
    _kunde(client, anna, kundennummer="K-1")
    # Gleiche Nummern bei einem anderen Mandanten sind keine Dubletten.
    assert _post(client, anna, "/stammdaten/rechnungen/import/pruefen", LISTE, _opt()).json()["neu"] == 3
    # Der Export gibt es fuer Rechnungslisten nicht.
    assert client.get("/stammdaten/rechnungen/export", headers=kevin).status_code == 422


def test_ust_spalte_wird_nach_den_werten_als_satz_oder_betrag_erkannt():
    from app.stammdaten.felder import schlage_zuordnung_vor

    kopf = ["Nr", "Datum", "Kunde", "Netto", "MwSt", "Brutto"]
    betraege = [["R1", "01.01.2025", "A", "100,00", "19,00", "119,00"], ["R2", "02.01.2025", "A", "50,00", "9,50", "59,50"]]
    saetze = [["R1", "01.01.2025", "A", "100,00", "19", "119,00"], ["R2", "02.01.2025", "A", "50,00", "7 %", "53,50"]]
    assert schlage_zuordnung_vor("rechnungen", kopf, betraege)["ust"] == "MwSt"
    erkannt = schlage_zuordnung_vor("rechnungen", kopf, saetze)
    assert erkannt["ust_satz"] == "MwSt" and "ust" not in erkannt
