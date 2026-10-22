"""Schluesselrotation (scripts/rotate_encryption.py): nach einer Rotation darf der alte Key entbehrlich sein."""
import base64
import os
from types import SimpleNamespace
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.core.crypto import _legacy_fernet
from app.core.key_management import encrypt_text, keyring
from app.db import Base, SessionLocal
from app.receipts.models import Ausgabe, AusgabeSteueranteil, Receipt
from scripts.rotate_encryption import (
    FIELDS, LEGACY_FIELDS, _primaerschluessel, kid_von, pruefe_aktiven_key, rotate_db, verschluesselte_spalten,
)
from tests.test_altrechnungen_auswertung import _aufbau, _zahle
from tests.test_bank import CAMT, KONTO_IBAN, _import, _konto
from tests.test_einnahmen import _payload as _einnahme_payload
from tests.test_invoices import _invoice_payload
from tests.test_produkte import _produkt_payload
from tests.test_quotes import _quote_payload


def test_spalten_kommen_aus_den_modellen_und_enthalten_die_frueher_fehlenden():
    assert FIELDS == verschluesselte_spalten()
    fruehere_luecken = {
        "invoices": {"netto_gesamt", "ust_gesamt", "brutto_gesamt"},
        "invoice_positionen": {"menge", "einzelpreis", "kategorie", "artikelnummer"},
        "quotes": {"brutto_gesamt"},
        "receipts": {"betrag", "kategorie_vorschlag"},
        "ausgaben": {"betrag", "kategorie"},
        "produkte": {"einzelpreis"},
        "kassenbuch_eintraege": {"betrag"},
        "sonstige_einnahmen": {"betrag_brutto"},
        "lohn_monatsentwuerfe": {"grundbrutto", "gesamtbrutto"},
        "auth_sessions": {"user_agent"},
        "email_aenderungen": {"neue_email"},
        "altrechnungen": {"nummer", "brutto", "offen_beim_import", "steueranteile"},
    }
    for tabelle, spalten in fruehere_luecken.items():
        assert spalten <= set(FIELDS[tabelle]), tabelle
    # Jede Tabelle hat einen einfachen Primaerschluessel, nach dem das Skript einzelne Zeilen aktualisiert.
    for tabelle in [*FIELDS, *LEGACY_FIELDS]:
        assert _primaerschluessel(tabelle)
    # Von Hand verschluesselte Spalten (nicht ueber die Typ-Klassen) stehen weiter in LEGACY_FIELDS.
    assert set(LEGACY_FIELDS) == {"users", "mitarbeitende"}


def test_kid_wird_aus_dem_gespeicherten_wert_gelesen():
    assert kid_von(encrypt_text("x", purpose="test.kid")) == settings.data_encryption_active_kid
    assert kid_von("gAAAAABaltesFernetToken") is None
    assert kid_von("einfacher Klartext") is None


@pytest.fixture
def schluesselwechsel(monkeypatch):
    """Fuegt einen zweiten Key hinzu und macht ihn aktiv; stellt danach den Ring wieder her."""
    alter_ring, alter_kid = settings.data_encryption_keys, settings.data_encryption_active_kid
    neuer_eintrag = "neu:" + base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")

    def aktivieren():
        monkeypatch.setattr(settings, "data_encryption_keys", f"{alter_ring},{neuer_eintrag}")
        monkeypatch.setattr(settings, "data_encryption_active_kid", "neu")
        keyring.cache_clear()

    def nur_noch_neuer_key():
        monkeypatch.setattr(settings, "data_encryption_keys", neuer_eintrag)
        keyring.cache_clear()

    wechsel = SimpleNamespace(aktivieren=aktivieren, nur_noch_neuer_key=nur_noch_neuer_key)
    yield wechsel
    monkeypatch.setattr(settings, "data_encryption_keys", alter_ring)
    monkeypatch.setattr(settings, "data_encryption_active_kid", alter_kid)
    keyring.cache_clear()


def _daten_anlegen(client: TestClient) -> tuple[dict, str]:
    """Daten in vielen Tabellen, damit die Rotation moeglichst viele verschluesselte Spalten trifft."""
    headers, ids = _aufbau(client)
    _zahle(client, headers, ids["RE-A1"])  # altrechnung_zahlungen
    kontakt_id = client.get("/kontakte", headers=headers).json()[0]["id"]
    rechnung = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    client.post(f"/invoices/{rechnung['id']}/finalize", headers=headers)
    client.post(f"/invoices/{rechnung['id']}/bezahlt", headers=headers, json={})
    client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id))
    client.post("/produkte", headers=headers, json={**_produkt_payload(bezeichnung="Workshop"), "artikelnummer": "W-1"})
    client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-01", "typ": "einnahme", "betrag": "100.00", "beschreibung": "Bar"})
    client.post("/einnahmen", headers=headers, json=_einnahme_payload())
    mandant_id = client.get("/auth/me", headers=headers).json()["mandant_id"]
    with SessionLocal() as db:
        db.add(Receipt(mandant_id=mandant_id, datei_referenz="x/b.png", datei_hash="b" * 64, status="geprueft",
                       anbieter="Deutsche Bahn", betrag=Decimal("49.90"), kategorie_vorschlag="Reisekosten"))
        ausgabe = Ausgabe(mandant_id=mandant_id, betrag=Decimal("49.90"), datum=date(2026, 9, 1), zahlungsdatum=date(2026, 9, 1),
                          anbieter="Deutsche Bahn", kategorie="Reisekosten", konto="4670")
        ausgabe.steueranteile.append(AusgabeSteueranteil(mandant_id=mandant_id, bruttobetrag=Decimal("49.90"), ust_satz=Decimal("19.00")))
        db.add(ausgabe)
        db.commit()
    konto = _konto(client, headers, iban=KONTO_IBAN)
    assert _import(client, headers, konto["id"], CAMT).status_code == 201  # bankkonten, bankumsaetze
    return headers, kontakt_id


def test_nach_der_rotation_liegt_alles_auf_dem_neuen_key_und_der_alte_wird_nicht_mehr_gebraucht(client: TestClient, schluesselwechsel):
    headers, kontakt_id = _daten_anlegen(client)
    erwartet_netto = client.get("/berichte/euer", headers=headers).json()["betriebseinnahmen_netto"]
    rechnungen_vorher = client.get("/invoices", headers=headers).json()

    schluesselwechsel.aktivieren()
    vorher = pruefe_aktiven_key()
    # Vor der Rotation liegen die Werte noch auf dem alten Key, auch die frueher vergessenen Betraege.
    for spalte in ("invoices.brutto_gesamt", "receipts.betrag", "ausgaben.betrag", "produkte.einzelpreis", "kassenbuch_eintraege.betrag",
                   "sonstige_einnahmen.betrag_brutto", "altrechnungen.brutto", "altrechnung_zahlungen.betrag", "bankumsaetze.betrag"):
        assert spalte in vorher, spalte

    assert rotate_db() > 0
    offen = pruefe_aktiven_key()
    # Auf Postgres bleibt das append-only Audit-Log auf dem alten Key, der Rest muss rotiert sein.
    assert set(offen) <= {"audit_log_eintraege.kontext"}, offen
    if not offen:
        schluesselwechsel.nur_noch_neuer_key()  # der alte Key ist jetzt aus dem Ring
    assert client.get("/invoices", headers=headers).json() == rechnungen_vorher
    assert client.get("/berichte/euer", headers=headers).json()["betriebseinnahmen_netto"] == erwartet_netto
    for pfad in ("/kontakte", "/angebote", "/produkte", "/kassenbuch", "/einnahmen", "/altrechnungen", "/bank/umsaetze", "/berichte/dashboard"):
        assert client.get(pfad, headers=headers).status_code == 200, pfad
    assert client.get(f"/kontakte/{kontakt_id}/historie", headers=headers).status_code == 200
    # Neue Werte werden mit dem neuen Key geschrieben.
    assert client.post("/kassenbuch", headers=headers, json={"datum": "2026-09-02", "typ": "ausgabe", "betrag": "5.00", "beschreibung": "Nach Rotation"}).status_code in (200, 201)


def test_altbestand_wird_beim_rotieren_nicht_doppelt_verschluesselt(client: TestClient, schluesselwechsel):
    headers, kontakt_id = _daten_anlegen(client)
    with SessionLocal() as db:
        # Altes Fernet-Token und nie verschluesselter Klartext, wie sie aus sehr frueher Zeit uebrig sein koennten.
        db.execute(text("UPDATE kontakte SET name = :n WHERE id = :i"), {"n": _legacy_fernet.encrypt("Alte Firma GmbH".encode()).decode(), "i": kontakt_id})
        db.execute(text("UPDATE kontakte SET ort = :o WHERE id = :i"), {"o": "Altstadt", "i": kontakt_id})
        db.commit()

    schluesselwechsel.aktivieren()
    rotate_db()
    if not pruefe_aktiven_key():
        schluesselwechsel.nur_noch_neuer_key()

    kontakt = next(k for k in client.get("/kontakte", headers=headers).json() if k["id"] == kontakt_id)
    assert kontakt["name"] == "Alte Firma GmbH" and kontakt["ort"] == "Altstadt"
    assert set(pruefe_aktiven_key()) <= {"audit_log_eintraege.kontext"}


def test_pruefmodus_aendert_nichts_und_nennt_nicht_rotierte_spalten(client: TestClient, schluesselwechsel):
    _daten_anlegen(client)
    schluesselwechsel.aktivieren()
    with SessionLocal() as db:
        vor = db.execute(text("SELECT brutto_gesamt FROM invoices")).scalars().all()
    offen = pruefe_aktiven_key()
    with SessionLocal() as db:
        assert db.execute(text("SELECT brutto_gesamt FROM invoices")).scalars().all() == vor  # nur lesen
    assert offen["invoices.brutto_gesamt"] >= 1
