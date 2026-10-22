import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bank import matching
from app.bank.parser_camt import lese_camt
from app.bank.parser_csv import CsvProfil, lese_csv, vorschau_csv
from app.bank.rohdaten import ImportFehler
from app.config import settings
from tests.test_invoices import _invoice_payload, _kontakt
from tests.test_invoices import _onboarded_mandant as _mandant
from tests.test_receipts import (
    _clear_extractor_override,  # noqa: F401  (autouse-Fixture)
    _extraction,
    _FakeExtractor,
    _onboarded_mandant,
    _use_extractor,
)

FIXTURES = Path(__file__).parent / "fixtures"
CAMT = (FIXTURES / "camt053_beispiel.xml").read_bytes()
SPARKASSE_CSV = (FIXTURES / "kontoauszug_sparkasse_stil.csv").read_bytes()
REVOLUT_CSV = (FIXTURES / "kontoauszug_revolut_stil.csv").read_bytes()
KONTO_IBAN = "DE89370400440532013000"


# ---------------------------------------------------------------------------
# CAMT.053


def test_camt_liest_gebuchte_eintraege_mit_vorzeichen_und_gegenpartei():
    auszug = lese_camt(CAMT)

    assert auszug.konto_iban == KONTO_IBAN
    assert [(u.buchungsdatum.isoformat(), u.betrag) for u in auszug.umsaetze] == [
        ("2026-10-02", Decimal("1240.00")),
        ("2026-10-03", Decimal("-49.90")),
        ("2026-10-04", Decimal("-100.00")),
        ("2026-10-04", Decimal("-200.00")),
    ]
    eingang, ausgang, sammel_a, sammel_b = auszug.umsaetze
    assert (eingang.gegenpartei_name, eingang.gegenpartei_iban) == ("Beispiel Kunde GmbH", "DE02120300000000202051")
    assert eingang.verwendungszweck == "Rechnung RE-2026-0001 Danke"
    assert eingang.end_to_end_id == "E2E-1001"
    assert (ausgang.gegenpartei_name, ausgang.end_to_end_id) == ("Nordwind Hosting GmbH", None)
    assert (sammel_a.gegenpartei_name, sammel_b.gegenpartei_name) == ("Lieferant A", "Lieferant B")


def test_camt_ueberspringt_vorgemerkte_eintraege():
    assert all("vorgemerkt" not in u.verwendungszweck for u in lese_camt(CAMT).umsaetze)


def test_camt_kehrt_stornobuchungen_um():
    xml = b"""<?xml version="1.0"?><Document><BkToCstmrStmt><Stmt><Ntry>
      <Amt Ccy="EUR">20.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><RvslInd>true</RvslInd><Sts>BOOK</Sts>
      <BookgDt><Dt>2026-10-02</Dt></BookgDt><AddtlNtryInf>Rueckbuchung</AddtlNtryInf>
    </Ntry></Stmt></BkToCstmrStmt></Document>"""

    [umsatz] = lese_camt(xml).umsaetze

    assert umsatz.betrag == Decimal("20.00")
    assert umsatz.verwendungszweck == "Rueckbuchung"


@pytest.mark.parametrize(
    "daten,meldung",
    [
        (b"kein xml", "kein gültiges XML"),
        (b'<?xml version="1.0"?><Document/>', "keine Umsätze"),
        (b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/hostname">]><a>&x;</a>', "DOCTYPE"),
    ],
)
def test_camt_lehnt_ungeeignete_dateien_verstaendlich_ab(daten, meldung):
    with pytest.raises(ImportFehler, match=meldung):
        lese_camt(daten)


# ---------------------------------------------------------------------------
# CSV


def test_csv_im_sparkassen_stil_wird_erkannt_und_gelesen():
    vorschau = vorschau_csv(SPARKASSE_CSV)

    assert (vorschau.trennzeichen, vorschau.anzahl_zeilen) == (";", 3)
    profil = vorschau.vorgeschlagenes_profil
    assert profil is not None
    assert (profil.datum, profil.datum_format, profil.dezimal, profil.betrag) == ("Buchungstag", "%d.%m.%Y", "komma", "Betrag")
    assert (profil.name, profil.iban, profil.verwendungszweck, profil.wertstellung) == (
        "Auftraggeber/Empfänger", "IBAN", ["Verwendungszweck"], "Wertstellung",
    )

    umsaetze = lese_csv(SPARKASSE_CSV, profil).umsaetze

    assert [u.betrag for u in umsaetze] == [Decimal("1240.00"), Decimal("-49.90"), Decimal("-12.50")]
    assert umsaetze[0].gegenpartei_iban == "DE02120300000000202051"
    assert umsaetze[2].gegenpartei_name == "Bäckerei Süß"


def test_csv_im_revolut_stil_mit_punkt_komma_und_uhrzeit():
    vorschau = vorschau_csv(REVOLUT_CSV)
    profil = vorschau.vorgeschlagenes_profil

    assert vorschau.trennzeichen == ","
    assert (profil.datum, profil.datum_format, profil.dezimal, profil.betrag) == ("Completed Date", "%Y-%m-%d", "punkt", "Amount")

    umsaetze = lese_csv(REVOLUT_CSV, profil).umsaetze

    assert [(u.buchungsdatum.isoformat(), u.betrag) for u in umsaetze] == [
        ("2026-10-02", Decimal("-49.90")), ("2026-10-03", Decimal("1240.00")),
    ]
    assert umsaetze[0].gegenpartei_name == "Nordwind Hosting GmbH"


def test_csv_in_windows_kodierung_wird_erkannt():
    daten = "Datum;Betrag;Name\n02.10.2026;-5,00;Müller & Söhne\n".encode("cp1252")

    vorschau = vorschau_csv(daten)

    assert vorschau.kodierung == "cp1252"
    assert lese_csv(daten, vorschau.vorgeschlagenes_profil).umsaetze[0].gegenpartei_name == "Müller & Söhne"


def test_csv_mit_soll_und_haben_spalten():
    daten = b"Datum;Soll;Haben;Name\n02.10.2026;;100,00;Kunde\n03.10.2026;40,00;;Lieferant\n"

    profil = vorschau_csv(daten).vorgeschlagenes_profil
    umsaetze = lese_csv(daten, profil).umsaetze

    assert (profil.soll, profil.haben, profil.betrag) == ("Soll", "Haben", None)
    assert [u.betrag for u in umsaetze] == [Decimal("100.00"), Decimal("-40.00")]


@pytest.mark.parametrize(
    "wert,erwartet",
    [("1.234,56", "1234.56"), ("-12,5", "-12.50"), ("+7,00", "7.00"), ("(12,50)", "-12.50"), ("12,50 €", "12.50")],
)
def test_csv_zahlenformate_mit_komma(wert, erwartet):
    daten = f"Datum;Betrag\n02.10.2026;{wert}\n".encode()
    profil = CsvProfil(datum="Datum", betrag="Betrag")

    assert lese_csv(daten, profil).umsaetze[0].betrag == Decimal(erwartet)


def test_csv_import_bricht_bei_fehlerhaften_zeilen_ab_statt_still_zu_ueberspringen():
    daten = b"Datum;Betrag\n02.10.2026;5,00\n31.31.2026;7,00\n03.10.2026;abc\n"
    profil = CsvProfil(datum="Datum", betrag="Betrag")

    with pytest.raises(ImportFehler) as fehler:
        lese_csv(daten, profil)

    assert "nicht durchgeführt" in str(fehler.value)
    assert "Zeile 3" in str(fehler.value) and "Zeile 4" in str(fehler.value)


def test_csv_fremdwaehrung_und_fehlende_spalten_werden_abgelehnt():
    with pytest.raises(ImportFehler, match="Euro"):
        lese_csv(b"Datum;Betrag;W\n02.10.2026;5,00;USD\n", CsvProfil(datum="Datum", betrag="Betrag", waehrung="W"))
    with pytest.raises(ImportFehler, match="gibt es in der Datei nicht"):
        lese_csv(b"Datum;Betrag\n02.10.2026;5,00\n", CsvProfil(datum="Buchung", betrag="Betrag"))


# ---------------------------------------------------------------------------
# Zuordnungslogik


def _eingang(zweck="", name="Kunde", betrag="1240.00") -> matching.Umsatz:
    return matching.Umsatz("u1", date(2026, 10, 2), Decimal(betrag), name, zweck)


def _rechnung(id_="r1", nummer="RE-2026-0001", brutto="1240.00", kunde="Beispiel Kunde GmbH", faellig=date(2026, 10, 10)):
    return matching.RechnungKandidat(id_, nummer, Decimal(brutto), kunde, faellig)


def test_betrag_und_rechnungsnummer_ergeben_einen_sicheren_vorschlag():
    vorschlag = matching.vorschlag_fuer_eingang(_eingang("Rechnung RE 2026-0001 danke"), [_rechnung()])

    assert vorschlag.sicher is True
    assert vorschlag.ziel_id == "r1"
    assert "Rechnungsnummer RE-2026-0001 steht im Verwendungszweck" in vorschlag.gruende


def test_betrag_und_name_ohne_nummer_ist_nur_ein_vorschlag():
    vorschlag = matching.vorschlag_fuer_eingang(_eingang("Danke", name="Beispiel Kunde GmbH"), [_rechnung()])

    assert vorschlag.sicher is False
    assert vorschlag.score == 0.65


def test_nur_der_betrag_reicht_nicht():
    assert matching.vorschlag_fuer_eingang(_eingang("Miete", name="Fremder"), [_rechnung()]) is None


def test_rechnungsnummer_mit_abweichendem_betrag_wird_gemeldet_aber_nie_als_sicher():
    vorschlag = matching.vorschlag_fuer_eingang(_eingang("RE-2026-0001", betrag="1000.00"), [_rechnung()])

    assert vorschlag.sicher is False
    assert any("Betrag weicht ab" in grund for grund in vorschlag.gruende)


def test_mehrere_gleich_passende_rechnungen_nehmen_die_aelteste_und_sind_nie_sicher():
    juenger = _rechnung("r2", nummer="RE-2026-0002", faellig=date(2026, 11, 1))
    aelter = _rechnung("r1", nummer="RE-2026-0001", faellig=date(2026, 10, 1))

    vorschlag = matching.vorschlag_fuer_eingang(_eingang("Danke", name="Beispiel Kunde GmbH"), [juenger, aelter])

    assert vorschlag.ziel_id == "r1"
    assert vorschlag.sicher is False
    assert any("2 offene Rechnungen" in grund for grund in vorschlag.gruende)


def test_ausgang_trifft_beleg_ueber_betrag_und_name_oder_datum():
    umsatz = matching.Umsatz("u2", date(2026, 10, 3), Decimal("-49.90"), "NORDWIND HOSTING", "")
    beleg = matching.BelegKandidat("b1", "beleg", Decimal("49.90"), "Nordwind Hosting GmbH", date(2026, 10, 1), None)
    anderer = matching.BelegKandidat("b2", "beleg", Decimal("49.90"), "Ganz Anderer", date(2026, 3, 1), None)
    naher = matching.BelegKandidat("b3", "ausgabe", Decimal("49.90"), "Ganz Anderer", date(2026, 10, 1), date(2026, 10, 3))

    assert matching.vorschlag_fuer_ausgang(umsatz, [beleg, anderer]).ziel_id == "b1"
    assert matching.vorschlag_fuer_ausgang(umsatz, [anderer]) is None
    treffer = matching.vorschlag_fuer_ausgang(umsatz, [naher])
    assert (treffer.typ, treffer.sicher) == ("ausgabe", False)


# ---------------------------------------------------------------------------
# API


def _konto(client: TestClient, headers: dict, *, iban: str | None = KONTO_IBAN, bezeichnung: str = "Geschäftskonto") -> dict:
    antwort = client.post("/bank/konten", headers=headers, json={"bezeichnung": bezeichnung, "iban": iban})
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


def _import(client: TestClient, headers: dict, konto_id: str, daten: bytes, *, name="auszug.xml", profil: dict | None = None):
    return client.post(
        f"/bank/konten/{konto_id}/import", headers=headers,
        files={"file": (name, daten, "application/octet-stream")}, data={"profil": json.dumps(profil)} if profil else {},
    )


def _umsaetze(client: TestClient, headers: dict, status="offen") -> list[dict]:
    return client.get("/bank/umsaetze", headers=headers, params={"status": status}).json()["umsaetze"]


def _finale_rechnung(client: TestClient, headers: dict) -> dict:
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(_kontakt(client, headers))).json()
    return client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()


def _camt_fuer(rechnung: dict) -> bytes:
    return CAMT.replace(b"RE-2026-0001", rechnung["nummer"].encode())


def test_bankimport_steht_jedem_mandanten_ohne_einschraenkung_offen(client: TestClient):
    headers = _mandant(client)

    assert client.get("/bank/konten", headers=headers).status_code == 200
    assert client.get("/bank/umsaetze", headers=headers).status_code == 200


def test_camt_import_legt_umsaetze_an_und_erkennt_einen_zweiten_import_als_doppelt(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers)

    erster = _import(client, headers, konto["id"], CAMT)
    zweiter = _import(client, headers, konto["id"], CAMT)

    assert erster.status_code == 201, erster.text
    assert (erster.json()["neu"], erster.json()["doppelt"], erster.json()["format"]) == (4, 0, "camt")
    assert (erster.json()["zeitraum_von"], erster.json()["zeitraum_bis"]) == ("2026-10-02", "2026-10-04")
    assert (zweiter.json()["neu"], zweiter.json()["doppelt"]) == (0, 4)
    assert len(_umsaetze(client, headers)) == 4
    assert client.get("/bank/konten", headers=headers).json()[0]["anzahl_umsaetze"] == 4


def test_identische_zeilen_in_einer_datei_bleiben_getrennt_und_werden_beim_reimport_erkannt(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban=None)
    daten = b"Datum;Betrag;Name\n02.10.2026;-3,50;Kiosk\n02.10.2026;-3,50;Kiosk\n"
    profil = vorschau_csv(daten).vorgeschlagenes_profil.model_dump()

    erster = _import(client, headers, konto["id"], daten, name="a.csv", profil=profil).json()
    zweiter = _import(client, headers, konto["id"], daten, name="a.csv", profil=profil).json()
    laenger = _import(client, headers, konto["id"], daten + b"02.10.2026;-3,50;Kiosk\n", name="b.csv", profil=profil).json()

    assert (erster["neu"], erster["doppelt"]) == (2, 0)
    assert (zweiter["neu"], zweiter["doppelt"]) == (0, 2)
    assert (laenger["neu"], laenger["doppelt"]) == (1, 2)


def test_csv_import_merkt_das_spaltenprofil_fuer_das_naechste_mal(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban=None)
    vorschau = client.post(
        f"/bank/konten/{konto['id']}/import/vorschau", headers=headers, files={"file": ("a.csv", SPARKASSE_CSV, "text/csv")},
    ).json()
    assert vorschau["format"] == "csv" and vorschau["csv"]["vorgeschlagenes_profil"]["datum"] == "Buchungstag"
    assert vorschau["gespeichertes_profil"] is None

    erster = _import(client, headers, konto["id"], SPARKASSE_CSV, name="a.csv", profil=vorschau["csv"]["vorgeschlagenes_profil"])
    ohne_profil = _import(client, headers, konto["id"], SPARKASSE_CSV, name="b.csv")

    assert erster.status_code == 201 and erster.json()["neu"] == 3
    assert ohne_profil.json()["doppelt"] == 3
    assert client.get("/bank/konten", headers=headers).json()[0]["csv_profil"]["datum"] == "Buchungstag"


def test_csv_ohne_profil_wird_mit_verstaendlicher_meldung_abgelehnt(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban=None)

    antwort = _import(client, headers, konto["id"], SPARKASSE_CSV, name="a.csv")

    assert antwort.status_code == 400
    assert "Spaltenprofil" in antwort.json()["detail"]


def test_camt_einer_anderen_iban_wird_abgelehnt_und_legt_nichts_an(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban="DE02120300000000202051")

    antwort = _import(client, headers, konto["id"], CAMT)

    assert antwort.status_code == 400
    assert "anderen Konto" in antwort.json()["detail"]
    assert _umsaetze(client, headers) == []


def test_konto_ohne_iban_uebernimmt_die_iban_aus_der_camt_datei(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban=None)

    _import(client, headers, konto["id"], CAMT)

    assert client.get("/bank/konten", headers=headers).json()[0]["iban"] == KONTO_IBAN


@pytest.mark.parametrize("daten", [b"%PDF-1.4 kein kontoauszug", b"\x89PNG\r\n\x1a\nbild"])
def test_pdf_und_bilder_sind_kein_kontoauszug(client: TestClient, daten):
    headers = _mandant(client)
    konto = _konto(client, headers)

    antwort = _import(client, headers, konto["id"], daten, name="x.pdf")

    assert antwort.status_code == 400
    assert "CAMT.053" in antwort.json()["detail"]


def test_zu_grosse_importdatei_wird_mit_413_abgelehnt(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "bank_max_bytes", 100)
    headers = _mandant(client)
    konto = _konto(client, headers)

    assert _import(client, headers, konto["id"], CAMT).status_code == 413


def test_importdatei_wird_verschluesselt_abgelegt(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "bank_storage_dir", str(tmp_path))
    headers = _mandant(client)
    konto = _konto(client, headers)

    _import(client, headers, konto["id"], CAMT)

    [datei] = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert datei.suffix == ".xml"
    assert b"Beispiel Kunde GmbH" not in datei.read_bytes()


def test_sicherer_treffer_wird_gesammelt_bestaetigt_und_markiert_die_rechnung_als_bezahlt(client: TestClient):
    headers = _mandant(client)
    rechnung = _finale_rechnung(client, headers)
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], _camt_fuer(rechnung))

    eingang = next(u for u in _umsaetze(client, headers) if Decimal(u["betrag"]) > 0)
    assert eingang["vorschlag"]["typ"] == "rechnung" and eingang["vorschlag"]["sicher"] is True
    assert client.get("/bank/zusammenfassung", headers=headers).json()["sichere_vorschlaege"] == 1

    antwort = client.post("/bank/zuordnungen/bestaetigen", headers=headers, json={"umsatz_ids": [eingang["id"]]})

    assert antwort.json() == {"bestaetigt": 1, "uebersprungen": []}
    bezahlt = client.get(f"/invoices/{rechnung['id']}", headers=headers).json()
    assert bezahlt["bezahlt_am"] == "2026-10-02"
    [zugeordnet] = _umsaetze(client, headers, "zugeordnet")
    assert (zugeordnet["zuordnung_typ"], zugeordnet["zuordnung_id"]) == ("rechnung", rechnung["id"])
    assert client.get("/bank/zusammenfassung", headers=headers).json()["sichere_vorschlaege"] == 0


def test_gesammeltes_bestaetigen_ueberspringt_unsichere_und_fremde_ids(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], CAMT)
    ausgang = next(u for u in _umsaetze(client, headers) if Decimal(u["betrag"]) < 0)

    antwort = client.post(
        "/bank/zuordnungen/bestaetigen", headers=headers, json={"umsatz_ids": [ausgang["id"], "gibt-es-nicht"]},
    ).json()

    assert antwort["bestaetigt"] == 0
    assert {u["grund"] for u in antwort["uebersprungen"]} == {"Kein sicherer Vorschlag.", "Umsatz nicht gefunden."}


def test_manuelle_zuordnung_mit_falschem_betrag_wird_abgelehnt(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers, iban=None)
    daten = b"Datum;Betrag;Name\n02.10.2026;100,00;Kunde\n"
    _import(client, headers, konto["id"], daten, name="a.csv", profil=vorschau_csv(daten).vorgeschlagenes_profil.model_dump())
    rechnung = _finale_rechnung(client, headers)
    [umsatz] = _umsaetze(client, headers)

    antwort = client.post(
        f"/bank/umsaetze/{umsatz['id']}/zuordnen", headers=headers, json={"typ": "rechnung", "ziel_id": rechnung["id"]},
    )

    assert antwort.status_code == 400
    assert "Teilzahlungen" in antwort.json()["detail"]
    assert client.get(f"/invoices/{rechnung['id']}", headers=headers).json()["bezahlt_am"] is None


def test_zuordnung_zu_einer_rechnung_laesst_sich_nicht_aufheben(client: TestClient):
    headers = _mandant(client)
    rechnung = _finale_rechnung(client, headers)
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], _camt_fuer(rechnung))
    eingang = next(u for u in _umsaetze(client, headers) if Decimal(u["betrag"]) > 0)
    client.post(f"/bank/umsaetze/{eingang['id']}/zuordnen", headers=headers, json={"typ": "rechnung", "ziel_id": rechnung["id"]})

    antwort = client.post(f"/bank/umsaetze/{eingang['id']}/zuordnung-aufheben", headers=headers)

    assert antwort.status_code == 400
    assert "nicht zurücknehmen" in antwort.json()["detail"]


def test_zahlung_wird_beleg_zugeordnet_belegt_das_zahlungsdatum_vor_und_folgt_der_buchung(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(
        betrag=("49.90", 0.95), anbieter=("Nordwind Hosting GmbH", 0.9), datum=("2026-10-01", 0.9),
    )))
    beleg = client.post("/belege", headers=headers, files={"file": ("b.png", b"\x89PNG\r\n\x1a\nbank", "image/png")}).json()
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], CAMT)
    ausgang = next(u for u in _umsaetze(client, headers) if u["betrag"] == "-49.90")
    assert (ausgang["vorschlag"]["typ"], ausgang["vorschlag"]["ziel_id"], ausgang["vorschlag"]["sicher"]) == ("beleg", beleg["id"], False)

    client.post(f"/bank/umsaetze/{ausgang['id']}/zuordnen", headers=headers, json={"typ": "beleg", "ziel_id": beleg["id"]})
    assert client.get(f"/belege/{beleg['id']}", headers=headers).json()["zahlungsdatum_vorschlag"] == "2026-10-03"

    ausgabe = client.post(f"/belege/{beleg['id']}/bestaetigen", headers=headers, json={}).json()

    assert ausgabe["zahlungsdatum"] == "2026-10-03"
    [zugeordnet] = _umsaetze(client, headers, "zugeordnet")
    assert (zugeordnet["zuordnung_typ"], zugeordnet["zuordnung_id"]) == ("ausgabe", ausgabe["id"])


def test_geloeschter_beleg_gibt_die_zugeordnete_zahlung_wieder_frei(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(betrag=("49.90", 0.95), anbieter=("Nordwind Hosting GmbH", 0.9))))
    beleg = client.post("/belege", headers=headers, files={"file": ("b.png", b"\x89PNG\r\n\x1a\nbank2", "image/png")}).json()
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], CAMT)
    ausgang = next(u for u in _umsaetze(client, headers) if u["betrag"] == "-49.90")
    client.post(f"/bank/umsaetze/{ausgang['id']}/zuordnen", headers=headers, json={"typ": "beleg", "ziel_id": beleg["id"]})

    assert client.delete(f"/belege/{beleg['id']}", headers=headers).status_code == 204

    assert {u["id"] for u in _umsaetze(client, headers)} >= {ausgang["id"]}
    assert _umsaetze(client, headers, "zugeordnet") == []


def test_einem_beleg_laesst_sich_nur_eine_zahlung_zuordnen(client: TestClient):
    headers = _onboarded_mandant(client)
    _use_extractor(_FakeExtractor(_extraction(betrag=("49.90", 0.95))))
    beleg = client.post("/belege", headers=headers, files={"file": ("b.png", b"\x89PNG\r\n\x1a\nbank3", "image/png")}).json()
    konto = _konto(client, headers, iban=None)
    daten = b"Datum;Betrag;Name\n03.10.2026;-49,90;A\n04.10.2026;-49,90;B\n"
    _import(client, headers, konto["id"], daten, name="a.csv", profil=vorschau_csv(daten).vorgeschlagenes_profil.model_dump())
    erste, zweite = _umsaetze(client, headers)

    assert client.post(f"/bank/umsaetze/{erste['id']}/zuordnen", headers=headers, json={"typ": "beleg", "ziel_id": beleg["id"]}).status_code == 200
    doppelt = client.post(f"/bank/umsaetze/{zweite['id']}/zuordnen", headers=headers, json={"typ": "beleg", "ziel_id": beleg["id"]})

    assert doppelt.status_code == 400


def test_ignorieren_und_aufheben_sowie_der_filter_beleg_fehlt(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], CAMT)
    fehlend = _umsaetze(client, headers, "beleg_fehlt")
    assert len(fehlend) == 3 and all(Decimal(u["betrag"]) < 0 and u["beleg_fehlt"] for u in fehlend)

    ignoriert = client.post(f"/bank/umsaetze/{fehlend[0]['id']}/ignorieren", headers=headers, json={"grund": "Privatentnahme"})
    assert ignoriert.json()["status"] == "ignoriert" and ignoriert.json()["ignoriert_grund"] == "Privatentnahme"
    assert len(_umsaetze(client, headers, "beleg_fehlt")) == 2
    assert client.get("/bank/zusammenfassung", headers=headers).json() == {
        "offen": 3, "beleg_fehlt": 2, "sichere_vorschlaege": 0, "zugeordnet": 0, "ignoriert": 1,
    }

    offen = client.post(f"/bank/umsaetze/{fehlend[0]['id']}/zuordnung-aufheben", headers=headers).json()
    assert offen["status"] == "offen" and offen["ignoriert_grund"] is None


def test_bankdaten_sind_mandantengetrennt(client: TestClient):
    kopf_a = _mandant(client, email="a@example.com")
    kopf_b = _mandant(client, email="b@example.com")
    konto = _konto(client, kopf_a)
    _import(client, kopf_a, konto["id"], CAMT)
    umsatz = _umsaetze(client, kopf_a)[0]

    assert client.get("/bank/konten", headers=kopf_b).json() == []
    assert _umsaetze(client, kopf_b) == []
    assert _import(client, kopf_b, konto["id"], CAMT).status_code == 404
    assert client.post(f"/bank/umsaetze/{umsatz['id']}/ignorieren", headers=kopf_b, json={"grund": "x"}).status_code == 404
    assert client.post(f"/bank/umsaetze/{umsatz['id']}/zuordnung-aufheben", headers=kopf_b).status_code == 404


def test_datenexport_enthaelt_entschluesselte_bankdaten_ohne_interne_hashes(client: TestClient):
    headers = _mandant(client)
    konto = _konto(client, headers)
    _import(client, headers, konto["id"], CAMT)

    export = client.get("/auth/datenexport", headers=headers).json()

    assert export["bankkonten"][0]["iban"] == KONTO_IBAN
    assert {u["gegenpartei_name"] for u in export["bankumsaetze"]} >= {"Beispiel Kunde GmbH", "Nordwind Hosting GmbH"}
    assert Decimal("1240.00") in {Decimal(str(u["betrag"])) for u in export["bankumsaetze"]}
    assert all("dedupe_hash" not in u for u in export["bankumsaetze"])
    assert "iban_hash" not in export["bankkonten"][0]

