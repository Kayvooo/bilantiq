import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.altrechnungen.models import Altrechnung
from app.altrechnungen.zuordnung import Kandidat, Zuordner
from app.config import settings
from app.db import SessionLocal
from tests.test_altrechnungen_import import KOPF, ZUORDNUNG, _kunde, _opt, _post
from tests.test_invoices import _invoice_payload, _onboarded_mandant

D = Decimal
HEUTE = date.today()


def _liste_csv() -> bytes:
    """Eine bezahlte, eine ueberfaellige, eine nicht faellige Altrechnung (alle Kunde K-1)."""
    vor = lambda tage: (HEUTE - timedelta(days=tage)).strftime("%d.%m.%Y")  # noqa: E731
    nach = lambda tage: (HEUTE + timedelta(days=tage)).strftime("%d.%m.%Y")  # noqa: E731
    return (
        KOPF
        + f"RE-2024-0001;{vor(400)};K-1;Müller GmbH;{vor(370)};1000,00;190,00;1190,00;bezahlt\n"
        + f"RE-2024-0002;{vor(60)};K-1;Müller GmbH;{vor(30)};500,00;95,00;595,00;offen\n"
        + f"RE-2024-0010;{vor(5)};K-1;Müller GmbH;{nach(25)};100,00;7,00;107,00;offen\n"
    ).encode()


def _aufbau(client: TestClient, email="kevin@example.com") -> tuple[dict, str]:
    headers = _onboarded_mandant(client, email=email)
    kontakt_id = _kunde(client, headers, kundennummer="K-1")
    antwort = _post(client, headers, "/stammdaten/rechnungen/import", _liste_csv(), _opt())
    assert antwort.status_code == 200, antwort.text
    return headers, kontakt_id


def _alle(client, headers, **params) -> dict:
    return client.get("/altrechnungen", headers=headers, params=params).json()


def _nach_nummer(client, headers) -> dict:
    return {e["nummer"]: e for e in _alle(client, headers)["eintraege"]}


def _pdf(inhalt: str = "x") -> bytes:
    return f"%PDF-1.4\n% Testdatei {inhalt}\n".encode()


# ---------------------------------------------------------------------------
# Liste und Status


def test_liste_zeigt_status_offene_betraege_und_filter(client: TestClient):
    headers, kontakt_id = _aufbau(client)
    liste = _alle(client, headers)
    assert liste["gesamt"] == 3
    daten = {e["nummer"]: e for e in liste["eintraege"]}
    assert (daten["RE-2024-0001"]["status"], daten["RE-2024-0001"]["offen"], daten["RE-2024-0001"]["bezahlt_im_altsystem"]) == ("bezahlt", "0.00", True)
    assert (daten["RE-2024-0002"]["status"], daten["RE-2024-0002"]["offen"]) == ("ueberfaellig", "595.00")
    assert (daten["RE-2024-0010"]["status"], daten["RE-2024-0010"]["offen"]) == ("offen", "107.00")
    assert daten["RE-2024-0002"]["kontakt_name"] == "Müller GmbH"
    # neueste zuerst
    assert [e["nummer"] for e in liste["eintraege"]] == ["RE-2024-0010", "RE-2024-0002", "RE-2024-0001"]

    assert [e["nummer"] for e in _alle(client, headers, status="offen")["eintraege"]] == ["RE-2024-0010", "RE-2024-0002"]
    assert [e["nummer"] for e in _alle(client, headers, status="bezahlt")["eintraege"]] == ["RE-2024-0001"]
    assert _alle(client, headers, kontakt_id="gibtesnicht")["gesamt"] == 0
    begrenzt = _alle(client, headers, limit=1)
    assert begrenzt["gesamt"] == 3 and len(begrenzt["eintraege"]) == 1


def test_fremder_mandant_sieht_keine_altrechnungen(client: TestClient):
    headers, _ = _aufbau(client)
    anna = _onboarded_mandant(client, email="anna@example.com")
    assert _alle(client, anna)["gesamt"] == 0
    rechnung_id = _alle(client, headers)["eintraege"][0]["id"]
    assert client.post(f"/altrechnungen/{rechnung_id}/zahlung", headers=anna, json={}).status_code == 404
    assert client.get(f"/altrechnungen/{rechnung_id}/pdf", headers=anna).status_code == 404


# ---------------------------------------------------------------------------
# Zahlungen


def test_zahlung_ohne_angaben_zahlt_den_ganzen_offenen_betrag_heute(client: TestClient):
    headers, _ = _aufbau(client)
    rechnung = _nach_nummer(client, headers)["RE-2024-0002"]
    antwort = client.post(f"/altrechnungen/{rechnung['id']}/zahlung", headers=headers, json={})
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    assert (body["status"], body["offen"]) == ("bezahlt", "0.00")
    assert body["zahlungen"][0]["datum"] == HEUTE.isoformat() and body["zahlungen"][0]["betrag"] == "595.00"
    assert body["zahlungen"][0]["quelle"] == "manuell"
    assert body["bezahlt_im_altsystem"] is False  # in Bilantiq bezahlt, nicht im Altsystem


def test_teilzahlung_laesst_den_rest_offen_und_zu_viel_wird_abgelehnt(client: TestClient):
    headers, _ = _aufbau(client)
    rechnung = _nach_nummer(client, headers)["RE-2024-0002"]
    url = f"/altrechnungen/{rechnung['id']}/zahlung"
    erste = client.post(url, headers=headers, json={"betrag": "200.00", "datum": (HEUTE - timedelta(days=2)).isoformat()}).json()
    assert (erste["offen"], erste["status"]) == ("395.00", "ueberfaellig")
    zu_viel = client.post(url, headers=headers, json={"betrag": "400.00"})
    assert zu_viel.status_code == 400 and "höher als der offene Betrag" in zu_viel.json()["detail"]
    rest = client.post(url, headers=headers, json={"betrag": "395.00"}).json()
    assert (rest["offen"], rest["status"], len(rest["zahlungen"])) == ("0.00", "bezahlt", 2)
    nochmal = client.post(url, headers=headers, json={})
    assert nochmal.status_code == 400 and "schon vollständig bezahlt" in nochmal.json()["detail"]


def test_zahlung_ablehnungen_zukunft_null_und_im_altsystem_bezahlt(client: TestClient):
    headers, _ = _aufbau(client)
    daten = _nach_nummer(client, headers)
    url = f"/altrechnungen/{daten['RE-2024-0010']['id']}/zahlung"
    zukunft = client.post(url, headers=headers, json={"datum": (HEUTE + timedelta(days=1)).isoformat()})
    assert zukunft.status_code == 400 and "Zukunft" in zukunft.json()["detail"]
    assert client.post(url, headers=headers, json={"betrag": "0"}).status_code == 422
    alt = client.post(f"/altrechnungen/{daten['RE-2024-0001']['id']}/zahlung", headers=headers, json={})
    assert alt.status_code == 400 and "schon vollständig bezahlt" in alt.json()["detail"]


# ---------------------------------------------------------------------------
# PDF-Archiv


def test_zuordner_regeln_grenzen_der_nummer_trennzeichen_und_mehrdeutigkeit():
    zuordner = Zuordner([Kandidat("a", "RE-2024-1"), Kandidat("b", "RE-2024-10"), Kandidat("c", "RE-2024-0001"), Kandidat("d", "12"), Kandidat("e", "RE 7000")])
    art, treffer = zuordner.finde("RE-2024-10.pdf")
    assert (art, [k.id for k in treffer]) == ("eindeutig", ["b"])  # RE-2024-1 steckt nicht in ...-10
    assert zuordner.finde("Rechnung RE 2024 1 Müller.PDF") == ("eindeutig", [Kandidat("a", "RE-2024-1")])
    assert zuordner.finde("re20240001.pdf")[0] == "eindeutig"
    assert zuordner.finde("RE-7000_final.pdf")[1][0].id == "e"  # Trennzeichen egal
    assert zuordner.finde("12.pdf")[0] == "eindeutig"  # kurze Nummer: nur als ganzer Name
    assert zuordner.finde("Scan 12 vom Montag.pdf")[0] == "keine"
    art, treffer = zuordner.finde("RE-2024-1 und RE-2024-10 zusammen.pdf")
    assert art == "eindeutig" and treffer[0].id == "b"  # die laengere Nummer gewinnt
    gleich = Zuordner([Kandidat("x", "AB-100"), Kandidat("y", "CD-100")]).finde("AB-100 CD-100.pdf")
    assert gleich[0] == "unklar" and len(gleich[1]) == 2


def test_pdfs_werden_zugeordnet_verschluesselt_gespeichert_und_wieder_ausgeliefert(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers, _ = _aufbau(client)
    dateien = [
        ("files", ("RE-2024-0002.pdf", _pdf("zwei"), "application/pdf")),
        ("files", ("Rechnung RE 2024 0010 Müller.pdf", _pdf("zehn"), "application/pdf")),
        ("files", ("scan0815.pdf", _pdf("unbekannt"), "application/pdf")),
        ("files", ("RE-2024-0001.pdf", b"das ist kein pdf", "application/pdf")),
    ]
    antwort = client.post("/altrechnungen/pdfs", headers=headers, files=dateien)
    assert antwort.status_code == 200, antwort.text
    ergebnis = {e["dateiname"]: e for e in antwort.json()["ergebnisse"]}
    assert ergebnis["RE-2024-0002.pdf"]["status"] == "zugeordnet" and ergebnis["RE-2024-0002.pdf"]["nummer"] == "RE-2024-0002"
    assert ergebnis["Rechnung RE 2024 0010 Müller.pdf"]["nummer"] == "RE-2024-0010"
    assert ergebnis["scan0815.pdf"]["status"] == "keine"
    assert ergebnis["RE-2024-0001.pdf"]["status"] == "abgelehnt" and "keine PDF-Datei" in ergebnis["RE-2024-0001.pdf"]["grund"]

    daten = _nach_nummer(client, headers)
    assert daten["RE-2024-0002"]["hat_pdf"] and daten["RE-2024-0010"]["hat_pdf"] and not daten["RE-2024-0001"]["hat_pdf"]
    ohne = _alle(client, headers, ohne_pdf="true")
    assert [e["nummer"] for e in ohne["eintraege"]] == ["RE-2024-0001"]

    geladen = client.get(f"/altrechnungen/{daten['RE-2024-0002']['id']}/pdf", headers=headers)
    assert geladen.status_code == 200 and geladen.content == _pdf("zwei")
    assert geladen.headers["content-type"] == "application/pdf" and geladen.headers["cache-control"] == "no-store"
    auf_platte = [p for p in tmp_path.rglob("*.pdf") if p.is_file()]
    assert len(auf_platte) == 2 and all(b"Testdatei" not in p.read_bytes() for p in auf_platte)  # Ciphertext
    assert client.get(f"/altrechnungen/{daten['RE-2024-0001']['id']}/pdf", headers=headers).status_code == 404


def test_pdf_archiv_ist_unveraenderbar_und_erkennt_dubletten(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers, _ = _aufbau(client)
    daten = _nach_nummer(client, headers)
    erste = client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0002.pdf", _pdf("a"), "application/pdf"))])
    assert erste.json()["ergebnisse"][0]["status"] == "zugeordnet"

    anderes = client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0002.pdf", _pdf("b"), "application/pdf"))]).json()["ergebnisse"][0]
    assert anderes["status"] == "abgelehnt" and "hat schon ein PDF" in anderes["grund"]
    gleich = client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0010.pdf", _pdf("a"), "application/pdf"))]).json()["ergebnisse"][0]
    assert gleich["status"] == "abgelehnt" and "liegt schon bei Rechnung RE-2024-0002" in gleich["grund"]

    # Hand-Zuordnung: nur fuer Rechnungen ohne PDF, nur echte PDFs, keine Dubletten
    ziel = daten["RE-2024-0010"]["id"]
    assert client.post(f"/altrechnungen/{daten['RE-2024-0002']['id']}/pdf", headers=headers, files={"file": ("x.pdf", _pdf("c"), "application/pdf")}).status_code == 409
    assert client.post(f"/altrechnungen/{ziel}/pdf", headers=headers, files={"file": ("x.pdf", b"kein pdf", "application/pdf")}).status_code == 400
    assert client.post(f"/altrechnungen/{ziel}/pdf", headers=headers, files={"file": ("x.pdf", _pdf("a"), "application/pdf")}).status_code == 409
    ok = client.post(f"/altrechnungen/{ziel}/pdf", headers=headers, files={"file": ("scan.pdf", _pdf("neu"), "application/pdf")})
    assert ok.status_code == 200 and ok.json()["hat_pdf"] is True
    # Es gibt keinen Weg, ein PDF zu loeschen oder zu ersetzen.
    assert client.delete(f"/altrechnungen/{ziel}/pdf", headers=headers).status_code == 405


def test_pdf_ablage_steht_allen_offen_und_dateizahl_ist_begrenzt(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers, _ = _aufbau(client)
    rechnung = _nach_nummer(client, headers)["RE-2024-0002"]
    abgelegt = client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0002.pdf", _pdf(), "application/pdf"))])
    assert abgelegt.status_code == 200 and abgelegt.json()["ergebnisse"][0]["status"] == "zugeordnet"
    assert client.post(f"/altrechnungen/{rechnung['id']}/zahlung", headers=headers, json={}).status_code == 200

    pro, _ = _aufbau(client, email="pro@example.com")
    zu_viele = [("files", (f"datei{i}.pdf", _pdf(str(i)), "application/pdf")) for i in range(settings.altrechnung_pdf_max_dateien + 1)]
    antwort = client.post("/altrechnungen/pdfs", headers=pro, files=zu_viele)
    assert antwort.status_code == 400 and "höchstens 20 Dateien" in antwort.json()["detail"]


def test_zu_grosse_pdfs_werden_abgelehnt(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "altrechnung_pdf_max_bytes", 200)
    headers, _ = _aufbau(client)
    gross = b"%PDF-1.4\n" + b"x" * 500
    ergebnis = client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0002.pdf", gross, "application/pdf"))]).json()["ergebnisse"][0]
    assert ergebnis["status"] == "abgelehnt" and "zu groß" in ergebnis["grund"]


# ---------------------------------------------------------------------------
# Kontakt, Historie, Rueckgaengig


def test_kontakt_historie_fasst_bilantiq_und_altrechnungen_zusammen(client: TestClient):
    headers, kontakt_id = _aufbau(client)
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()
    historie = client.get(f"/kontakte/{kontakt_id}/historie", headers=headers)
    assert historie.status_code == 200, historie.text
    body = historie.json()
    assert {e["art"] for e in body["eintraege"]} == {"bilantiq", "altsystem"} and len(body["eintraege"]) == 4
    assert D(body["umsatz_brutto_altsystem"]) == D("1892.00")  # 1190 + 595 + 107
    assert D(body["umsatz_brutto_bilantiq"]) == D(final["brutto_gesamt"])
    assert D(body["offen_brutto"]) == D("702.00") + D(final["brutto_gesamt"])  # 595 + 107 offen im Altsystem
    assert client.get(f"/kontakte/{kontakt_id}/historie", headers=_onboarded_mandant(client, email="anna@example.com")).status_code == 404


def test_kontakt_mit_altrechnungen_laesst_sich_nur_archivieren(client: TestClient):
    headers, kontakt_id = _aufbau(client)
    loeschen = client.delete(f"/kontakte/{kontakt_id}", headers=headers)
    assert loeschen.status_code == 409 and "archivieren" in loeschen.json()["detail"]
    assert client.post(f"/kontakte/{kontakt_id}/archivieren", headers=headers).status_code == 200


def test_rueckgaengig_behaelt_altrechnungen_mit_zahlung_oder_pdf(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "altrechnung_storage_dir", str(tmp_path))
    headers = _onboarded_mandant(client)
    _kunde(client, headers, kundennummer="K-1")
    import_id = _post(client, headers, "/stammdaten/rechnungen/import", _liste_csv(), _opt()).json()["import_id"]
    daten = _nach_nummer(client, headers)
    client.post(f"/altrechnungen/{daten['RE-2024-0002']['id']}/zahlung", headers=headers, json={})
    client.post("/altrechnungen/pdfs", headers=headers, files=[("files", ("RE-2024-0010.pdf", _pdf(), "application/pdf"))])

    zurueck = client.post(f"/stammdaten/importe/{import_id}/rueckgaengig", headers=headers)
    assert zurueck.status_code == 200, zurueck.text
    assert zurueck.json() == {"geloescht": 1, "behalten": 2}
    uebrig = set(_nach_nummer(client, headers))
    assert uebrig == {"RE-2024-0002", "RE-2024-0010"}
    # Die Quelldatei bleibt, solange noch Rechnungen aus dem Import existieren.
    assert any(p.name.startswith("import-") for p in tmp_path.rglob("*"))


def test_dsgvo_export_enthaelt_altrechnungen_und_zahlungen_ohne_interne_hashes(client: TestClient):
    headers, ids = _aufbau(client)
    assert client.post(f"/altrechnungen/{ids_nach_nummer(client, headers)['RE-2024-0002']}/zahlung", headers=headers, json={}).status_code == 200
    export = client.get("/auth/datenexport", headers=headers)
    assert export.status_code == 200
    daten = json.loads(export.content)
    assert {a["nummer"] for a in daten["altrechnungen"]} == {"RE-2024-0001", "RE-2024-0002", "RE-2024-0010"}
    assert all("nummer_hash" not in a for a in daten["altrechnungen"])
    assert len(daten["altrechnung_zahlungen"]) == 1 and daten["altrechnung_zahlungen"][0]["betrag"] == "595.00"


def ids_nach_nummer(client, headers) -> dict:
    return {e["nummer"]: e["id"] for e in client.get("/altrechnungen", headers=headers).json()["eintraege"]}
