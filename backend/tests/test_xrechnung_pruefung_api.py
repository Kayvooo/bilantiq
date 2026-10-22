"""Die Pruefung der XRechnung in den Endpunkten: Modus aus/warnen/blockieren, Pruef-Endpunkt, Mandantentrennung, Storno.

Tests mit dem Zusatz ``braucht_regeln`` brauchen die per scripts/kosit_regeln_holen.py geholten Regeln und werden sonst mit
Meldung uebersprungen. Die Modus-Tests mit leerem Regelordner laufen immer."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pikepdf
import pytest
from fastapi.testclient import TestClient
from lxml import etree
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.invoices.models import Invoice
from tests.test_e_invoice_validation import braucht_regeln
from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant

CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"


def _finale_rechnung(client: TestClient, headers: dict, payload: dict | None = None) -> dict:
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    entwurf = client.post("/invoices", headers=headers, json=payload or _invoice_payload(kontakt_id)).json()
    return client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()


def _format_in_db(rechnung_id: str) -> str | None:
    with SessionLocal() as db:
        return db.scalars(select(Invoice.e_invoice_format).where(Invoice.id == rechnung_id)).one()


@pytest.fixture
def ohne_regeln(tmp_path: Path, monkeypatch) -> Path:
    leer = tmp_path / "keine-regeln"
    monkeypatch.setattr(settings, "xrechnung_regeln_dir", str(leer))
    return leer


@pytest.fixture
def kaputtes_xml(monkeypatch):
    """Der Generator liefert XML, das die Regeln ablehnen (BuyerReference fehlt)."""
    from app.invoices import routes

    echt = routes.build_xrechnung_xml

    def kaputt(*args, **kwargs):
        xml = echt(*args, **kwargs)
        baum = etree.fromstring(xml)
        for knoten in baum.findall(f"{CBC}BuyerReference"):
            baum.remove(knoten)
        return etree.tostring(baum, xml_declaration=True, encoding="UTF-8")

    monkeypatch.setattr(routes, "build_xrechnung_xml", kaputt)


# --- Modi ---------------------------------------------------------------------------------------------------------

def test_modus_warnen_ohne_regeln_liefert_aus_und_sagt_nicht_geprueft(client: TestClient, ohne_regeln, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "warnen")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200
    assert antwort.headers["X-Xrechnung-Pruefung"] == "nicht_geprueft"
    assert _format_in_db(rechnung["id"]) == "xrechnung"


def test_modus_blockieren_ohne_regeln_liefert_nichts_aus(client: TestClient, ohne_regeln, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 422
    assert "kosit_regeln_holen" in antwort.json()["detail"]
    assert antwort.headers["content-type"].startswith("application/json")  # kein XML
    assert _format_in_db(rechnung["id"]) is None


def test_modus_aus_prueft_nicht(client: TestClient, ohne_regeln, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "aus")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200
    assert antwort.headers["X-Xrechnung-Pruefung"] == "aus"


@braucht_regeln
def test_gueltige_xrechnung_wird_im_modus_blockieren_ausgeliefert(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200, antwort.text
    assert antwort.headers["X-Xrechnung-Pruefung"] == "bestanden"
    assert antwort.headers["X-Xrechnung-Fehler"] == "0"
    assert "Saxon" in antwort.headers["X-Xrechnung-Regeln"]
    assert "2026-08-31" in antwort.headers["X-Xrechnung-Regeln"]
    assert _format_in_db(rechnung["id"]) == "xrechnung"


@braucht_regeln
def test_ungueltige_xml_wird_im_modus_blockieren_nicht_ausgeliefert(client: TestClient, kaputtes_xml, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 422
    assert "BR-DE-15" in antwort.json()["detail"]
    assert f"/invoices/{rechnung['id']}/e-rechnung-validierung" in antwort.json()["detail"]
    assert _format_in_db(rechnung["id"]) is None  # nicht als "erzeugt" vermerkt


@braucht_regeln
def test_ungueltige_xml_geht_im_modus_warnen_nur_mit_kennzeichnung_raus(client: TestClient, kaputtes_xml, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "warnen")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200
    assert antwort.headers["X-Xrechnung-Pruefung"] == "nicht_bestanden"
    assert int(antwort.headers["X-Xrechnung-Fehler"]) >= 1


@braucht_regeln
def test_zugferd_pdf_wird_im_modus_blockieren_ebenfalls_geprueft(client: TestClient, kaputtes_xml, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/zugferd-pdf", headers=headers)

    assert antwort.status_code == 422
    assert _format_in_db(rechnung["id"]) is None


@braucht_regeln
def test_zugferd_pdf_gueltig_enthaelt_das_gepruefte_xml(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.post(f"/invoices/{rechnung['id']}/zugferd-pdf", headers=headers)

    assert antwort.status_code == 200, antwort.text
    assert antwort.headers["X-Xrechnung-Pruefung"] == "bestanden"
    with pikepdf.Pdf.open(BytesIO(antwort.content)) as pdf:
        assert "xrechnung.xml" in pdf.attachments


# --- Pruef-Endpunkt -----------------------------------------------------------------------------------------------

@braucht_regeln
def test_pruefendpunkt_liefert_ergebnis_mit_regelversion(client: TestClient):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    antwort = client.get(f"/invoices/{rechnung['id']}/e-rechnung-validierung", headers=headers)

    assert antwort.status_code == 200
    ergebnis = antwort.json()
    assert ergebnis["status"] == "bestanden"
    assert ergebnis["rechnungsnummer"] == rechnung["nummer"]
    assert ergebnis["regeln"]["xrechnung_version"] == "3.0.2"
    assert ergebnis["regeln"]["kosit_konfiguration"] == "2026-08-31"
    assert "nicht das KoSIT-Validator-Programm" in ergebnis["hinweis"]


def test_pruefendpunkt_ohne_regeln_sagt_nicht_geprueft(client: TestClient, ohne_regeln):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    ergebnis = client.get(f"/invoices/{rechnung['id']}/e-rechnung-validierung", headers=headers).json()

    assert ergebnis["status"] == "nicht_geprueft"
    assert ergebnis["bestanden"] is False


@braucht_regeln
def test_pruefendpunkt_meldet_regelverstoesse_mit_id(client: TestClient, kaputtes_xml):
    headers = _onboarded_mandant(client)
    rechnung = _finale_rechnung(client, headers)

    ergebnis = client.get(f"/invoices/{rechnung['id']}/e-rechnung-validierung", headers=headers).json()

    assert ergebnis["status"] == "nicht_bestanden"
    assert "BR-DE-15" in {b["regel_id"] for b in ergebnis["befunde"] if b["stufe"] == "fehler"}


def test_pruefendpunkt_verlangt_anmeldung_finale_rechnung_und_vollstaendige_daten(client: TestClient):
    assert client.get("/invoices/gibt-es-nicht/e-rechnung-validierung").status_code in (401, 403)

    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    assert client.get(f"/invoices/{entwurf['id']}/e-rechnung-validierung", headers=headers).status_code == 400

    client.patch("/auth/mandant", headers=headers, json={"telefon": ""})
    final = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()
    antwort = client.get(f"/invoices/{final['id']}/e-rechnung-validierung", headers=headers)
    assert antwort.status_code == 400
    assert "Telefonnummer" in antwort.json()["detail"]


def test_pruefendpunkt_zeigt_fremde_rechnungen_nicht(client: TestClient):
    kevin = _onboarded_mandant(client)
    lea = _onboarded_mandant(client, email="lea@example.com")
    rechnung = _finale_rechnung(client, kevin)

    assert client.get(f"/invoices/{rechnung['id']}/e-rechnung-validierung", headers=lea).status_code == 404
    assert client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=lea).status_code == 404


# --- Inhalte ueber die Endpunkte ----------------------------------------------------------------------------------

@braucht_regeln
def test_storno_ueber_die_api_ergibt_gueltige_gutschrift(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    original = _finale_rechnung(client, headers)
    storno = client.post(f"/invoices/{original['id']}/storno", headers=headers).json()

    antwort = client.post(f"/invoices/{storno['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200, antwort.text
    baum = etree.fromstring(antwort.content)
    assert etree.QName(baum).localname == "CreditNote"
    assert baum.findtext(f"{CBC}CreditNoteTypeCode") == "381"
    referenz = baum.find(".//{*}BillingReference/{*}InvoiceDocumentReference/{*}ID")
    assert referenz.text == original["nummer"]
    summe = baum.find(".//{*}LegalMonetaryTotal/{*}PayableAmount")
    assert Decimal(summe.text) == Decimal(original["brutto_gesamt"])


@braucht_regeln
def test_kleinunternehmer_einstellung_wirkt_auf_die_steuerkategorie(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    client.put(
        "/buchhaltungseinstellungen", headers=headers,
        json={"standard_zahlungsziel_tage": 14, "standard_ust_satz": "0.00", "kleinunternehmer": True},
    )
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    payload = _invoice_payload(kontakt_id)
    payload["positionen"] = [{"beschreibung": "Webdesign", "menge": "10", "einzelpreis": "65.00", "ust_satz": "0.00"}]
    rechnung = _finale_rechnung(client, headers, payload)

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200, antwort.text
    baum = etree.fromstring(antwort.content)
    assert baum.find(".//{*}TaxSubtotal/{*}TaxCategory/{*}ID").text == "E"
    assert "§ 19 UStG" in baum.find(".//{*}TaxSubtotal/{*}TaxCategory/{*}TaxExemptionReason").text


@braucht_regeln
def test_rechnung_ueber_die_api_mit_gemischten_saetzen_und_rundung(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "xrechnung_pruefung", "blockieren")
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    payload = _invoice_payload(kontakt_id)
    payload["positionen"] = [
        {"beschreibung": "Kleinteil", "menge": "1", "einzelpreis": "0.99", "ust_satz": "19.00"},
        {"beschreibung": "Kleinteil", "menge": "1", "einzelpreis": "0.99", "ust_satz": "19.00"},
        {"beschreibung": "Kleinteil", "menge": "1", "einzelpreis": "0.99", "ust_satz": "19.00"},
        {"beschreibung": "Fachbuch", "menge": "2", "einzelpreis": "24.90", "ust_satz": "7.00"},
    ]
    rechnung = _finale_rechnung(client, headers, payload)
    # 0,56 auf 2,97 netto plus 3,49 auf 49,80 netto; je Zeile gerundet waeren es 4,06
    assert Decimal(rechnung["ust_gesamt"]) == Decimal("4.05")

    antwort = client.post(f"/invoices/{rechnung['id']}/e-rechnung", headers=headers)

    assert antwort.status_code == 200, antwort.text
    assert antwort.headers["X-Xrechnung-Pruefung"] == "bestanden"


# --- Mandant: neue Pflichtfelder -----------------------------------------------------------------------------------

def test_mandant_telefon_und_kontakt_email_lassen_sich_speichern(client: TestClient):
    headers = _onboarded_mandant(client)

    mandant = client.get("/auth/mandant", headers=headers).json()

    assert mandant["telefon"] == "+49 30 1234567"
    assert mandant["kontakt_email"] == "rechnung@example.com"


def test_e_rechnung_pruefung_nennt_fehlende_angaben_zu_telefon_iban_und_kaeufer_email(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"telefon": "", "kontakt_email": "", "iban": ""})
    kontakt = client.post(
        "/kontakte", headers=headers,
        json={"name": "Ohne Mail GmbH", "strasse": "Weg 1", "plz": "80331", "ort": "München", "land": "DE"},
    ).json()
    payload = _invoice_payload(kontakt["id"])
    entwurf = client.post("/invoices", headers=headers, json=payload).json()
    final = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()

    fehlt = client.get(f"/invoices/{final['id']}/e-rechnung-pruefung", headers=headers).json()["fehlende_felder"]

    assert "IBAN (Verkaeufer)" in fehlt
    assert "Telefonnummer (Verkaeufer)" in fehlt
    assert "E-Mail-Adresse fuer Rueckfragen (Verkaeufer)" in fehlt
    assert "E-Mail-Adresse (Kaeufer)" in fehlt


def test_migration_0040_legt_telefon_und_kontakt_email_an_und_laesst_sich_zuruecknehmen(tmp_path: Path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    url = f"sqlite:///{(tmp_path / 'm0040.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(url)
    spalten = {c["name"]: c for c in inspect(engine).get_columns("mandanten")}
    assert spalten["telefon"]["nullable"] and spalten["kontakt_email"]["nullable"]
    engine.dispose()

    command.downgrade(config, "0039")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {"telefon", "kontakt_email"} <= {c["name"] for c in inspect(engine).get_columns("mandanten")}
    engine.dispose()
