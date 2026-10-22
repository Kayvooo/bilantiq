"""RLS-/Mandantentrennungs-Nachweis (Release-Plan 3.4): Mandant A sieht und aendert nichts von Mandant B.

Zwei Ebenen, beide Teil dieses Nachweises:

1. API-Ebene (laeuft unter SQLite UND Postgres): Beide Mandanten bekommen ueber die API echte Daten
   (Kontakte, Rechnungen, Angebote, Belege, ...). Dann ruft A jede Route mit Pfadparametern mit den IDs von B auf,
   durchsucht, exportiert und liest Dashboard/Audit-Verlauf. Unter Postgres laeuft die Anwendung dabei als
   Laufzeitrolle ``bilantiq_runtime`` (siehe ``scripts/rls_testlauf.sh``), die Datenbank erzwingt die Trennung also
   zusaetzlich zu den Filtern im Anwendungscode.
2. Datenbank-Ebene (nur Postgres): Direkte SQL-Zugriffe als Laufzeitrolle mit dem Kontext von A sehen keine Zeile
   von B, koennen sie nicht aendern oder loeschen und keine Zeilen fuer B einschleusen. Ausserdem muss jede Tabelle
   mit Mandantenbezug RLS und eine Policy haben (faengt neue Tabellen ohne Policy).
"""
import io
import json
import os
import re
from datetime import date, timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import engine, set_rls_mandant
from app.main import app
from app.receipts.ai_extraction import get_extractor
from tests.test_invoices import _invoice_payload, _onboarded_mandant
from tests.test_mahnwesen import _overdue_invoice_payload
from tests.test_receipts import FAKE_IMAGE, _extraction, _FakeExtractor
from tests.test_altrechnungen_import import LISTE as LISTE_ALT, _opt as _opt_alt, _post as _post_alt
from tests.test_bank import CAMT, _import, _konto, _umsaetze
from tests.test_stammdaten_import import KONTAKTE_CSV, _optionen, _post

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
GEHEIM = "GeheimB"  # Marker, der in keiner Antwort an Mandant A vorkommen darf


def _png() -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (8, 8), (30, 90, 120)).save(puffer, format="PNG")
    return puffer.getvalue()


def _ok(antwort, *erlaubt):
    assert antwort.status_code in (erlaubt or (200, 201, 204)), f"{antwort.request.method} {antwort.request.url}: {antwort.status_code} {antwort.text[:300]}"
    return antwort


@pytest.fixture
def zwei_mandanten(client: TestClient):
    """A und B (zwei getrennte Mandanten). B traegt den Marker GeheimB."""
    app.dependency_overrides[get_extractor] = lambda: _FakeExtractor(
        _extraction(anbieter=(f"{GEHEIM} Anbieter", 0.95))
    )
    a = _onboarded_mandant(client, email="a@example.com")
    b = _onboarded_mandant(client, email="b@example.com")
    _ok(client.patch("/auth/mandant", headers=b, json={"firmenname": f"{GEHEIM} GmbH"}))

    # --- Daten von A (damit A nicht "leer" ist und Verwechslungen auffallen)
    a_kontakt = _ok(client.post("/kontakte", headers=a, json={"name": "A Kunde", "plz": "10115", "ort": "Berlin"})).json()["id"]
    _ok(client.post("/invoices", headers=a, json=_invoice_payload(a_kontakt)))

    # --- Daten von B
    ids: dict[str, str] = {}
    ids["kontakt_id"] = _ok(client.post(
        "/kontakte", headers=b,
        json={"name": f"{GEHEIM} Kunde", "plz": "80331", "ort": "Muenchen", "kundennummer": "K-GEHEIM"},
    )).json()["id"]
    kategorie_rechnung = _invoice_payload(ids["kontakt_id"])
    kategorie_rechnung["positionen"][0]["kategorie"] = f"{GEHEIM} Kategorie"
    ids["invoice_id"] = _ok(client.post("/invoices", headers=b, json=kategorie_rechnung)).json()["id"]
    final = _ok(client.post("/invoices", headers=b, json=_invoice_payload(ids["kontakt_id"]))).json()
    _ok(client.post(f"/invoices/{final['id']}/finalize", headers=b))
    ids["final_invoice_id"] = final["id"]

    ueberfaellig = _ok(client.post("/invoices", headers=b, json=_overdue_invoice_payload(ids["kontakt_id"]))).json()
    _ok(client.post(f"/invoices/{ueberfaellig['id']}/finalize", headers=b))
    _ok(client.post(f"/invoices/{ueberfaellig['id']}/mahnung", headers=b))
    ids["mahnung_id"] = _ok(client.get("/mahnungen", headers=b)).json()[0]["id"]

    ids["quote_id"] = _ok(client.post("/angebote", headers=b, json={
        "kontakt_id": ids["kontakt_id"], "gueltig_bis": (date.today() + timedelta(days=14)).isoformat(), "waehrung": "EUR",
        "positionen": [{"beschreibung": f"{GEHEIM} Konzeption", "menge": "2", "einzelpreis": "500.00", "ust_satz": "19.00"}],
    })).json()["id"]
    angenommen = _ok(client.post("/angebote", headers=b, json={
        "kontakt_id": ids["kontakt_id"], "gueltig_bis": (date.today() + timedelta(days=14)).isoformat(), "waehrung": "EUR",
        "positionen": [{"beschreibung": "Workshop", "menge": "1", "einzelpreis": "100.00", "ust_satz": "19.00"}],
    })).json()
    _ok(client.post(f"/angebote/{angenommen['id']}/versenden", headers=b))
    _ok(client.post(f"/angebote/{angenommen['id']}/annehmen", headers=b))
    ab = _ok(client.post("/auftragsbestaetigungen", headers=b, json={"quote_id": angenommen["id"]})).json()
    ids["ab_id"] = ab["id"]
    ids["lieferschein_id"] = _ok(client.post("/lieferscheine", headers=b, json={
        "auftragsbestaetigung_id": ab["id"], "lieferdatum": date.today().isoformat(),
        "positionen": [{"beschreibung": "Workshop", "menge": "1"}],
    })).json()["id"]

    ids["beleg_id"] = _ok(client.post(
        "/belege", headers=b, files={"file": ("beleg.png", FAKE_IMAGE, "image/png")}, data={"force": "false"},
    )).json()["id"]
    ids["produkt_id"] = _ok(client.post("/produkte", headers=b, json={
        "bezeichnung": f"{GEHEIM} Produkt", "einzelpreis": "10.00", "ust_satz": "19.00", "einheit": "Stk", "aktiv": True,
    })).json()["id"]
    ids["einnahme_id"] = _ok(client.post("/einnahmen", headers=b, json={
        "bezeichnung": f"{GEHEIM} Provision", "betrag_brutto": "119.00", "ust_satz": "19.00",
        "datum": f"{date.today().year}-05-10", "verwendungszweck": "x",
    })).json()["id"]
    _ok(client.post("/kassenbuch", headers=b, json={
        "datum": "2026-09-01", "typ": "einnahme", "betrag": "100.00", "beschreibung": f"{GEHEIM} Bar",
    }))
    _ok(client.post("/anlagen", headers=b, json={
        "bezeichnung": f"{GEHEIM} Laptop", "anschaffungsdatum": "2026-06-01", "anschaffungskosten_netto": "1200.00",
        "nutzungsdauer_jahre": 3,
    }))
    ids["mitarbeiter_id"] = _ok(client.post("/lohn/mitarbeitende", headers=b, json={
        "personalnummer": "P-1", "vorname": GEHEIM, "nachname": "Mitarbeiter", "eintrittsdatum": "2026-01-15",
        "austrittsdatum": None, "monatsbrutto": "3200.00",
    })).json()["id"]
    ids["entwurf_id"] = _ok(client.post("/lohn/monatsentwuerfe", headers=b, json={
        "mitarbeiter_id": ids["mitarbeiter_id"], "jahr": 2026, "monat": 2,
    })).json()["id"]
    ids["rechnungs_vorlage_id"] = _ok(client.post("/wiederkehrende-rechnungen", headers=b, json={
        "kontakt_id": ids["kontakt_id"], "bezeichnung": f"{GEHEIM} Abo", "intervall": "monatlich", "naechstes_datum": "2026-12-01",
        "enddatum": None, "positionen": [{"beschreibung": "Hosting", "menge": "1", "einzelpreis": "49.00", "ust_satz": "19.00"}],
    })).json()["id"]
    ids["ausgaben_vorlage_id"] = _ok(client.post("/wiederkehrende-ausgaben", headers=b, json={
        "bezeichnung": f"{GEHEIM} Hosting", "anbieter": f"{GEHEIM} Anbieter", "betrag": "29.99", "ust_satz": "19.00",
        "kategorie": "Software/IT", "intervall": "monatlich", "naechstes_datum": "2026-12-01", "enddatum": None,
    })).json()["id"]
    ids["briefpapier_id"] = _ok(client.post(
        "/auth/briefpapier", headers=b, data={"name": f"{GEHEIM} Papier"}, files={"file": ("p.png", _png(), "image/png")},
    )).json()["id"]
    ids["einladung_id"] = _ok(client.post("/auth/einladungen", headers=b, json={})).json()["id"]
    mitglied = _ok(client.post("/auth/mitglieder", headers=b, json={"email": "mitglied-b@example.com", "rolle": "mitglied"})).json()
    ids["user_id"] = mitglied["user_id"]
    ids["session_id"] = _ok(client.get("/security", headers=b)).json()["sessions"][0]["id"]
    ids["kategorie_id"] = _ok(client.get("/positionskategorien", headers=b)).json()[0]["id"]
    ids["import_id"] = _ok(
        _post(client, b, "/stammdaten/kontakte/import", KONTAKTE_CSV, _optionen(fehlerhafte_auslassen=True))
    ).json()["import_id"]
    ids["konto_id"] = _konto(client, b)["id"]
    _ok(_import(client, b, ids["konto_id"], CAMT), 201)
    ids["umsatz_id"] = _umsaetze(client, b)[0]["id"]
    _ok(_post_alt(client, b, "/stammdaten/rechnungen/import", LISTE_ALT, _opt_alt()))
    ids["altrechnung_id"] = _ok(client.get("/altrechnungen", headers=b)).json()["eintraege"][0]["id"]
    yield {"a": a, "b": b, "ids": ids}
    app.dependency_overrides.pop(get_extractor, None)


# ---------------------------------------------------------------------------
# 1. API-Ebene


def test_a_sieht_in_keiner_liste_etwas_von_b(client: TestClient, zwei_mandanten):
    a = zwei_mandanten["a"]
    gelesen = []
    for route in _alle_routen():
        if "GET" not in route.methods or "{" in route.path or route.path in {"/health", "/openapi.json"}:
            continue
        antwort = client.get(route.path, headers=a)
        if antwort.status_code == 200:
            gelesen.append(route.path)
            assert GEHEIM not in antwort.text, f"Mandant A sieht Daten von B ueber GET {route.path}"
            assert "K-GEHEIM" not in antwort.text
    assert len(gelesen) >= 30, f"zu wenige Listenrouten geprueft: {gelesen}"


def test_suche_findet_nichts_von_b(client: TestClient, zwei_mandanten):
    a, b = zwei_mandanten["a"], zwei_mandanten["b"]
    eigene = client.post("/suche", headers=b, json={"q": GEHEIM})
    assert eigene.status_code == 200 and GEHEIM in eigene.text  # B findet die eigenen Daten (Gegenprobe)
    for begriff in (GEHEIM, "geheimb", "K-GEHEIM", "Muenchen", "mitglied-b@example.com"):
        fremde = client.post("/suche", headers=a, json={"q": begriff})
        assert fremde.status_code == 200
        assert GEHEIM not in fremde.text, begriff


def test_datenexport_von_a_enthaelt_nichts_von_b(client: TestClient, zwei_mandanten):
    a, b = zwei_mandanten["a"], zwei_mandanten["b"]
    export_a = _ok(client.get("/auth/datenexport", headers=a))
    assert GEHEIM not in export_a.text and "mitglied-b@example.com" not in export_a.text and "b@example.com" not in export_a.text
    export_b = json.loads(_ok(client.get("/auth/datenexport", headers=b)).content)
    assert GEHEIM in json.dumps(export_b)  # Gegenprobe: der Export von B enthaelt seine Daten
    mandant_ids_a = {eintrag.get("mandant_id") for eintrag in json.loads(export_a.content).get("audit_log", [])}
    assert len(mandant_ids_a - {None}) <= 1, "Audit-Log im Export von A enthaelt mehrere Mandanten"


def test_audit_log_und_dashboard_von_a_zeigen_keine_ereignisse_von_b(client: TestClient, zwei_mandanten):
    a, b = zwei_mandanten["a"], zwei_mandanten["b"]
    mandant_b = _ok(client.get("/auth/me", headers=b)).json()["mandant_id"]
    export_a = json.loads(_ok(client.get("/auth/datenexport", headers=a)).content)
    assert export_a["audit_log"], "A hat eigene Audit-Eintraege erwartet"
    assert all(e["mandant_id"] != mandant_b for e in export_a["audit_log"])
    dashboard = _ok(client.get("/berichte/dashboard", headers=a))
    assert mandant_b not in dashboard.text and GEHEIM not in dashboard.text


# Minimale gueltige Anfragekoerper fuer Routen mit Pflichtfeldern; alle anderen schicken ``{}``.
_KOERPER = {
    ("POST", "/bank/umsaetze/{umsatz_id}/ignorieren"): {"grund": "test"},
    ("POST", "/bank/umsaetze/{umsatz_id}/zuordnen"): {"typ": "rechnung", "ziel_id": "{invoice_id}"},
    ("POST", "/produkte/{produkt_id}/lagerbewegungen"): {"datum": "2026-09-01", "typ": "zugang", "menge": "1", "grund": "x"},
}
# Routen, deren Pfadparameter nicht aus Seed-Daten kommen (oeffentlich/ohne Mandantenobjekt).
_OHNE_FREMDE_ID = {"/stammdaten/{ziel}/export", "/stammdaten/{ziel}/vorlage",
                   "/stammdaten/{ziel}/import", "/stammdaten/{ziel}/import/fehlerliste",
                   "/stammdaten/{ziel}/import/pruefen", "/stammdaten/{ziel}/import/vorschau",
                   "/lohn/monate/{jahr}/{monat}/export"}
_PARAM_ZU_SEED = {
    "invoice_id": "invoice_id", "quote_id": "quote_id", "kontakt_id": "kontakt_id", "beleg_id": "beleg_id",
    "ab_id": "ab_id", "lieferschein_id": "lieferschein_id", "produkt_id": "produkt_id", "einnahme_id": "einnahme_id",
    "mitarbeiter_id": "mitarbeiter_id", "entwurf_id": "entwurf_id", "briefpapier_id": "briefpapier_id",
    "einladung_id": "einladung_id", "user_id": "user_id", "session_id": "session_id", "kategorie_id": "kategorie_id",
    "mahnung_id": "mahnung_id", "import_id": "import_id", "konto_id": "konto_id", "umsatz_id": "umsatz_id",
    "altrechnung_id": "altrechnung_id",
}
# Routen mit Datei-Upload (multipart): (Methode, Pfad) -> Datei
_DATEIEN = {
    ("POST", "/altrechnungen/{altrechnung_id}/pdf"): ("x.pdf", b"%PDF-1.4\n% test\n", "application/pdf"),
    ("POST", "/bank/konten/{konto_id}/import"): ("a.xml", CAMT, "application/xml"),
    ("POST", "/bank/konten/{konto_id}/import/vorschau"): ("a.xml", CAMT, "application/xml"),
}


def _alle_routen() -> list[APIRoute]:
    def laufe(routen):
        for r in routen:
            if type(r).__name__ == "_IncludedRouter":
                yield from laufe(r.original_router.routes)
            elif isinstance(r, APIRoute):
                yield r

    return list(laufe(app.routes))


def test_a_kann_fremde_objekte_von_b_weder_lesen_noch_aendern(client: TestClient, zwei_mandanten):
    """Jede Route mit Pfadparameter, aufgerufen von A mit der ID eines Objekts von B, darf nie Erfolg melden."""
    a, ids = zwei_mandanten["a"], zwei_mandanten["ids"]
    nicht_404: list[str] = []
    geprueft = 0
    for route in _alle_routen():
        if "{" not in route.path or route.path in _OHNE_FREMDE_ID:
            continue
        parameter = re.findall(r"{(\w+)}", route.path)
        kandidaten: list[dict] = []
        if parameter == ["vorlage_id"]:
            kandidaten = [{"vorlage_id": ids["rechnungs_vorlage_id"] if "rechnungen" in route.path else ids["ausgaben_vorlage_id"]}]
        else:
            kandidaten = [{p: ids[_PARAM_ZU_SEED[p]] for p in parameter}]
        for methode in sorted(route.methods - {"HEAD", "OPTIONS"}):
            pfad = route.path
            koerper = _KOERPER.get((methode, pfad), {})
            koerper = {k: ids.get(v.strip("{}"), v) if isinstance(v, str) and v.startswith("{") else v for k, v in koerper.items()}
            url = pfad.format(**kandidaten[0])
            if (methode, pfad) in _DATEIEN:
                antwort = client.request(methode, url, headers=a, files={"file": _DATEIEN[(methode, pfad)]})
            else:
                antwort = client.request(methode, url, headers=a, json=koerper if methode in {"POST", "PATCH", "PUT"} else None)
            geprueft += 1
            assert antwort.status_code < 200 or antwort.status_code >= 300, f"{methode} {url} meldete Erfolg: {antwort.text[:200]}"
            assert antwort.status_code < 500, f"{methode} {url}: {antwort.status_code}"
            assert GEHEIM not in antwort.text, f"{methode} {url} gibt Daten von B preis"
            if antwort.status_code != 404:
                nicht_404.append(f"{methode} {pfad} -> {antwort.status_code}")
    assert geprueft >= 55
    # Erlaubt sind nur Ablehnungen, die ebenfalls verhindern, dass A etwas bewirkt: 403 (Rolle), 422/400 (Eingabe).
    # 404 ist der Normalfall (Objekt aus Sicht von A nicht vorhanden). Die Liste unten dokumentiert die Ausnahmen.
    unerwartet = [e for e in nicht_404 if not re.search(r"-> (400|403|409|422)$", e)]
    assert not unerwartet, unerwartet


def test_b_daten_bleiben_nach_den_angriffen_von_a_unveraendert(client: TestClient, zwei_mandanten):
    """Nach dem Durchlauf mit Schreibversuchen von A ist bei B nichts veraendert oder geloescht."""
    test_a_kann_fremde_objekte_von_b_weder_lesen_noch_aendern(client, zwei_mandanten)
    b, ids = zwei_mandanten["b"], zwei_mandanten["ids"]
    assert _ok(client.get(f"/kontakte/{ids['kontakt_id']}/historie", headers=b), 200, 404) is not None
    kontakte = _ok(client.get("/kontakte", headers=b)).json()
    assert any(k["id"] == ids["kontakt_id"] and k["name"] == f"{GEHEIM} Kunde" for k in kontakte)
    assert _ok(client.get(f"/invoices/{ids['invoice_id']}", headers=b)).json()["status"] == "entwurf"
    assert _ok(client.get(f"/invoices/{ids['final_invoice_id']}", headers=b)).json()["status"] == "final"
    assert _ok(client.get(f"/belege/{ids['beleg_id']}", headers=b))
    assert _ok(client.get(f"/angebote/{ids['quote_id']}", headers=b)).json()["status"] == "entwurf"
    assert any(p["id"] == ids["produkt_id"] for p in _ok(client.get("/produkte", headers=b)).json())
    assert any(m["user_id"] == ids["user_id"] for m in _ok(client.get("/auth/mitglieder", headers=b)).json())


# ---------------------------------------------------------------------------
# 2. Datenbank-Ebene (Postgres, Laufzeitrolle)

postgres = pytest.mark.skipif(not ADMIN_URL, reason="braucht Postgres mit RLS (scripts/rls_testlauf.sh)")

# Tabellen ohne eigene Mandantenisolation, jeweils mit Begruendung:
OHNE_RLS = {
    "alembic_version": "Migrationsstand, gehoert dem Administrator (Laufzeitrolle hat keine Rechte)",
    "users": "Nutzerkonten sind mandantenuebergreifend; Zugriff nur ueber Mitgliedschaft (RLS) und Lookup-Hash",
}


@postgres
def test_jede_tabelle_hat_rls_und_policy_ausser_den_begruendeten():
    admin = create_engine(ADMIN_URL)
    try:
        with admin.connect() as c:
            zeilen = c.execute(text(
                "SELECT c.relname, c.relrowsecurity, (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )).all()
    finally:
        admin.dispose()
    ungeschuetzt = sorted(name for name, rls, policies in zeilen if name not in OHNE_RLS and not (rls and policies))
    assert not ungeschuetzt, f"Tabellen ohne RLS/Policy (Migration ergaenzen oder in OHNE_RLS begruenden): {ungeschuetzt}"
    unnoetig = sorted(name for name, rls, policies in zeilen if name in OHNE_RLS and rls)
    assert not unnoetig, f"In OHNE_RLS gelistet, hat aber RLS: {unnoetig}"


@postgres
def test_laufzeitrolle_sieht_ohne_kontext_keine_mandantendaten_und_mit_kontext_nur_eigene(zwei_mandanten, client: TestClient):
    a_id = client.get("/auth/me", headers=zwei_mandanten["a"]).json()["mandant_id"]
    b_id = client.get("/auth/me", headers=zwei_mandanten["b"]).json()["mandant_id"]
    admin = create_engine(ADMIN_URL)
    try:
        with admin.connect() as c:
            tabellen = [r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='mandant_id' "
                "AND table_name NOT IN (SELECT table_name FROM information_schema.views)"
            ))]
            b_zeilen = {t: c.execute(text(f'SELECT count(*) FROM "{t}" WHERE mandant_id = :m'), {"m": b_id}).scalar() for t in tabellen}
    finally:
        admin.dispose()
    assert sum(1 for n in b_zeilen.values() if n) >= 15, f"Seed von B zu klein: {b_zeilen}"

    with Session(engine) as db:
        assert db.execute(text("SELECT current_user")).scalar() == "bilantiq_runtime"
        for tabelle in tabellen:  # ohne Kontext: nichts sichtbar
            assert db.execute(text(f'SELECT count(*) FROM "{tabelle}"')).scalar() == 0, tabelle
        set_rls_mandant(db, a_id)
        for tabelle in tabellen:  # Kontext A: keine Zeile eines anderen Mandanten
            fremd = db.execute(text(f'SELECT count(*) FROM "{tabelle}" WHERE mandant_id IS NOT NULL AND mandant_id <> :a'), {"a": a_id}).scalar()
            assert fremd == 0, f"{tabelle}: Kontext A sieht {fremd} Zeilen anderer Mandanten"
        # Schreiben: Aendern/Loeschen fremder Zeilen trifft nichts, Einschleusen scheitert.
        for tabelle in ("kontakte", "invoices", "receipts", "produkte", "audit_log_eintraege"):
            if tabelle == "audit_log_eintraege":
                continue  # Laufzeitrolle hat dort ohnehin kein UPDATE/DELETE (append-only), siehe naechster Test
            assert db.execute(text(f'UPDATE "{tabelle}" SET mandant_id = mandant_id WHERE mandant_id = :b'), {"b": b_id}).rowcount == 0
            assert db.execute(text(f'DELETE FROM "{tabelle}" WHERE mandant_id = :b'), {"b": b_id}).rowcount == 0
        db.rollback()


@postgres
def test_audit_log_ist_fuer_die_laufzeitrolle_append_only_und_mandantengetrennt(zwei_mandanten, client: TestClient):
    from sqlalchemy.exc import ProgrammingError

    a_id = client.get("/auth/me", headers=zwei_mandanten["a"]).json()["mandant_id"]
    b_id = client.get("/auth/me", headers=zwei_mandanten["b"]).json()["mandant_id"]
    with Session(engine) as db:
        set_rls_mandant(db, a_id)
        sichtbar = db.execute(text("SELECT DISTINCT mandant_id FROM audit_log_eintraege")).scalars().all()
        assert b_id not in sichtbar
        with pytest.raises(ProgrammingError):
            db.execute(text("UPDATE audit_log_eintraege SET aktion = 'x'"))
        db.rollback()
        set_rls_mandant(db, a_id)
        with pytest.raises(ProgrammingError):
            db.execute(text("DELETE FROM audit_log_eintraege"))
        db.rollback()
        set_rls_mandant(db, a_id)
        with pytest.raises(Exception):  # fremden Mandanten im Audit-Log vortaeuschen
            db.execute(text(
                "INSERT INTO audit_log_eintraege (id, mandant_id, aktion, kontext, zeitpunkt) VALUES ('x', :b, 'fake', '', now())"
            ), {"b": b_id})
            db.flush()
        db.rollback()
