from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.receipts.models import Receipt
from app.suche import service
from tests.test_invoices import _invoice_payload, _onboarded_mandant
from tests.test_produkte import _produkt_payload
from tests.test_quotes import _quote_payload


def _kontakt(client: TestClient, headers: dict, name: str, **weitere) -> str:
    daten = {"name": name, "strasse": "Weg 1", "plz": "12345", "ort": "Musterstadt", "land": "DE", **weitere}
    antwort = client.post("/kontakte", headers=headers, json=daten)
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


def _suche(client: TestClient, headers: dict, q: str, **weitere):
    return client.post("/suche", headers=headers, json={"q": q, **weitere})


def _gruppe(antwort, typ: str) -> dict | None:
    return next((g for g in antwort.json()["gruppen"] if g["typ"] == typ), None)


# ---------------------------------------------------------------------------
# Bewertung


def test_normalisierung_faltet_umlaute_und_scharfes_s():
    assert service.normalisiere("Müller Straße") == "muller strasse"
    assert service.normalisiere("ÉCOLE") == "ecole"


def test_rang_anfang_vor_wortanfang_vor_enthalten():
    tokens = ["mai"]
    anfang = service.bewerte(tokens, [service.text_feld("Maier GmbH")])
    wort = service.bewerte(tokens, [service.text_feld("Haus Maier")])
    mitten = service.bewerte(tokens, [service.text_feld("Hamaiko")])
    assert anfang < wort < mitten
    assert service.bewerte(tokens, [service.text_feld("Schulze")]) is None


def test_alle_suchbegriffe_muessen_vorkommen():
    felder = [service.text_feld("Anna Schmidt"), service.text_feld("Hamburg")]
    assert service.bewerte(["anna", "hamburg"], felder) is not None
    assert service.bewerte(["anna", "berlin"], felder) is None


def test_betraege_zaehlen_nur_vom_anfang_her():
    felder = service.betrag_felder(Decimal("1190.00"))
    assert service.bewerte(["1190"], felder) is not None
    assert service.bewerte(["1.190,00"], felder) is not None
    assert service.bewerte(["1190,0"], felder) is not None
    assert service.bewerte(["190"], felder) is None  # steckt nur mitten in der Zahl


# ---------------------------------------------------------------------------
# API


def test_suche_verlangt_anmeldung_und_nur_post(client: TestClient):
    assert client.post("/suche", json={"q": "abc"}).status_code in (401, 403)
    headers = _onboarded_mandant(client)
    assert client.get("/suche?q=abc", headers=headers).status_code == 405


def test_zu_kurze_oder_zu_lange_eingaben_werden_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)
    assert _suche(client, headers, "a").status_code == 422
    assert _suche(client, headers, "  a ").status_code == 422
    assert _suche(client, headers, "x" * 101).status_code == 422
    assert _suche(client, headers, "ab", limit=11).status_code == 422
    assert _suche(client, headers, "ab", limit=0).status_code == 422


def test_findet_kontakte_nach_name_ort_kundennummer_ansprechpartner_und_email(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(
        client, headers, "Müller Maschinenbau GmbH", ort="Stuttgart", kundennummer="K-4711",
        vorname="Erika", nachname="Beispiel", email="einkauf@mueller-maschinen.example",
    )
    _kontakt(client, headers, "Ganz Anders AG")

    for begriff in ("müller", "muller", "stuttgart", "k-4711", "beispiel", "erika bei", "einkauf@"):
        gruppe = _gruppe(_suche(client, headers, begriff), "kontakte")
        assert gruppe is not None, begriff
        assert [t["id"] for t in gruppe["treffer"]] == [kontakt_id], begriff
        assert gruppe["treffer"][0]["ziel"] == "contacts"
    assert _gruppe(_suche(client, headers, "gibtesnicht"), "kontakte") is None


def test_archivierter_kontakt_wird_gefunden_und_gekennzeichnet(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, "Alte Firma KG")
    assert client.post(f"/kontakte/{kontakt_id}/archivieren", headers=headers).status_code == 200

    treffer = _gruppe(_suche(client, headers, "alte firma"), "kontakte")["treffer"][0]
    assert "archiviert" in treffer["untertitel"]


def test_findet_rechnung_nach_nummer_kunde_und_betrag(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, "Berger Handels GmbH")
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers).json()

    for begriff in (final["nummer"], "berger", "1240", "1.240,00", "berger 1240"):
        gruppe = _gruppe(_suche(client, headers, begriff), "rechnungen")
        assert gruppe is not None, begriff
        assert gruppe["treffer"][0]["id"] == final["id"], begriff
        assert gruppe["treffer"][0]["ziel"] == "invoices"
    assert "Berger Handels GmbH" in gruppe["treffer"][0]["untertitel"]
    assert "1.240,00 €" in gruppe["treffer"][0]["untertitel"]
    assert _gruppe(_suche(client, headers, "240"), "rechnungen") is None  # nur vom Zahlenanfang her


def test_rechnungsstatus_in_der_suche_unterscheidet_ueberfaellig_und_bezahlt(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, "Statuskunde AG")
    heute = date.today()
    ueberfaellig = {**_invoice_payload(kontakt_id), "faelligkeitsdatum": (heute - timedelta(days=3)).isoformat()}
    erste = client.post("/invoices", headers=headers, json=ueberfaellig).json()
    client.post(f"/invoices/{erste['id']}/finalize", headers=headers)
    zweite = client.post("/invoices", headers=headers, json=ueberfaellig).json()
    client.post(f"/invoices/{zweite['id']}/finalize", headers=headers)
    assert client.post(f"/invoices/{zweite['id']}/bezahlt", headers=headers, json={"bezahlt_am": heute.isoformat()}).status_code == 200

    untertitel = {t["id"]: t["untertitel"] for t in _gruppe(_suche(client, headers, "statuskunde"), "rechnungen")["treffer"]}
    assert untertitel[erste["id"]].endswith("überfällig")
    assert untertitel[zweite["id"]].endswith("bezahlt")


def test_rechnungsentwurf_ohne_nummer_ist_ueber_den_kunden_findbar(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, "Entwurfskunde")
    client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id))

    treffer = _gruppe(_suche(client, headers, "entwurfskunde"), "rechnungen")["treffer"][0]
    assert treffer["titel"] == "Rechnungsentwurf"
    assert "Entwurf" in treffer["untertitel"]


def test_findet_angebote_belege_und_produkte(client: TestClient):
    headers = _onboarded_mandant(client)
    mandant_id = client.get("/auth/me", headers=headers).json()["mandant_id"]
    kontakt_id = _kontakt(client, headers, "Angebotskunde SE")
    angebot = client.post("/angebote", headers=headers, json=_quote_payload(kontakt_id)).json()
    produkt = client.post(
        "/produkte", headers=headers, json={**_produkt_payload(bezeichnung="Workshop Premium"), "artikelnummer": "WS-77"},
    ).json()
    with SessionLocal() as db:
        beleg = Receipt(
            mandant_id=mandant_id, datei_referenz="x/beleg.png", datei_hash="a" * 64, status="geprueft",
            anbieter="Deutsche Bahn", betrag=Decimal("49.90"), rechnungsnummer="DB-998877",
            hochgeladen_am=datetime.now(timezone.utc),
        )
        db.add(beleg)
        db.commit()
        beleg_id = beleg.id

    angebote = _gruppe(_suche(client, headers, "angebotskunde"), "angebote")
    assert angebote["treffer"][0]["id"] == angebot["id"] and angebote["treffer"][0]["ziel"] == "quotes"
    assert _gruppe(_suche(client, headers, "952"), "angebote")["treffer"][0]["id"] == angebot["id"]  # 800 + 19 %

    for begriff in ("deutsche bahn", "db-998877", "49,90"):
        beleg_gruppe = _gruppe(_suche(client, headers, begriff), "belege")
        assert beleg_gruppe["treffer"][0]["id"] == beleg_id, begriff
        assert beleg_gruppe["treffer"][0]["ziel"] == "receipts"

    for begriff in ("workshop", "ws-77"):
        produkt_gruppe = _gruppe(_suche(client, headers, begriff), "produkte")
        assert produkt_gruppe["treffer"][0]["id"] == produkt["id"], begriff
        assert produkt_gruppe["treffer"][0]["ziel"] == "produkte"


def test_limit_je_gruppe_und_gesamtzahl(client: TestClient):
    headers = _onboarded_mandant(client)
    for nummer in range(7):
        _kontakt(client, headers, f"Serienkunde {nummer}")

    gruppe = _gruppe(_suche(client, headers, "serienkunde", limit=3), "kontakte")
    assert len(gruppe["treffer"]) == 3
    assert gruppe["gesamt"] == 7
    assert len(_gruppe(_suche(client, headers, "serienkunde"), "kontakte")["treffer"]) == 5  # Standard


def test_besserer_treffer_steht_vorn(client: TestClient):
    headers = _onboarded_mandant(client)
    mitten = _kontakt(client, headers, "Hamaiko GmbH")
    wort = _kontakt(client, headers, "Haus Maier")
    anfang = _kontakt(client, headers, "Maier Bau")

    ids = [t["id"] for t in _gruppe(_suche(client, headers, "mai"), "kontakte")["treffer"]]
    assert ids == [anfang, wort, mitten]


def test_mandanten_sehen_nur_eigene_treffer(client: TestClient):
    kevin = _onboarded_mandant(client, email="kevin@example.com")
    anna = _onboarded_mandant(client, email="anna@example.com")
    kontakt_id = _kontakt(client, kevin, "Geheimkunde GmbH")
    client.post("/invoices", headers=kevin, json=_invoice_payload(kontakt_id))
    client.post("/produkte", headers=kevin, json=_produkt_payload(bezeichnung="Geheimprodukt"))

    assert _suche(client, anna, "geheim").json() == {"gruppen": [], "unvollstaendig": []}
    assert len(_suche(client, kevin, "geheim").json()["gruppen"]) == 3


def test_ueber_der_obergrenze_wird_ehrlich_unvollstaendig_gemeldet(client: TestClient, monkeypatch):
    headers = _onboarded_mandant(client)
    for nummer in range(3):
        _kontakt(client, headers, f"Obergrenze {nummer}")
    monkeypatch.setattr(service, "MAX_ZEILEN_PRO_TYP", 2)

    antwort = _suche(client, headers, "obergrenze").json()
    assert antwort["unvollstaendig"] == ["kontakte"]
    assert _gruppe(_suche(client, headers, "obergrenze"), "kontakte")["gesamt"] == 2


def test_findet_rechnungen_aus_dem_altsystem(client: TestClient):
    from tests.test_altrechnungen import _aufbau

    headers, _ = _aufbau(client)
    for begriff in ("RE-2024-0002", "müller", "595"):
        gruppe = _gruppe(_suche(client, headers, begriff), "altrechnungen")
        assert gruppe is not None, begriff
        assert gruppe["label"] == "Rechnungen aus dem Altsystem" and gruppe["treffer"][0]["ziel"] == "invoices"
    treffer = _gruppe(_suche(client, headers, "RE-2024-0002"), "altrechnungen")["treffer"][0]
    assert "aus dem Altsystem" in treffer["untertitel"] and "595,00 €" in treffer["untertitel"]
    assert _gruppe(_suche(client, headers, "RE-2024-0002"), "rechnungen") is None  # nicht mit Bilantiq-Rechnungen vermischt
