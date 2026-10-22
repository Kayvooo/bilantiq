"""Phase 5: Nummernkreis fortsetzen, Schutz vor doppelten Rechnungsnummern, Umzugsstatus."""
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.audit_log import AuditLogEintrag
from app.db import SessionLocal
from tests.test_altrechnungen_import import KOPF, ZUORDNUNG, _kunde, _opt, _post
from tests.test_benutzerverwaltung import _register_and_verify
from tests.test_invoices import _invoice_payload, _onboarded_mandant
from tests.test_stammdaten_import import KONTAKTE_CSV
from tests.test_stammdaten_import import ZUORDNUNG as KONTAKT_ZUORDNUNG

JAHR = datetime.now(timezone.utc).year  # der Nummernkreis zaehlt nach UTC-Jahr


def _alt_csv(*nummern: str) -> bytes:
    zeilen = [f"{n};15.03.{JAHR};K-1;Müller GmbH;14.04.{JAHR};100,00;19,00;119,00;offen\n" for n in nummern]
    return (KOPF + "".join(zeilen)).encode()


def _aufbau(client: TestClient, *alt_nummern: str, email="kevin@example.com") -> tuple[dict, str]:
    headers = _onboarded_mandant(client, email=email)
    kontakt_id = _kunde(client, headers, kundennummer="K-1")
    if alt_nummern:
        antwort = _post(client, headers, "/stammdaten/rechnungen/import", _alt_csv(*alt_nummern), _opt())
        assert antwort.status_code == 200, antwort.text
    return headers, kontakt_id


def _kreis(client, headers) -> dict:
    antwort = client.get("/einstellungen/nummernkreis", headers=headers)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


def _finalisieren(client, headers, kontakt_id):
    entwurf = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    return entwurf, client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers)


# ---------------------------------------------------------------------------
# Nummernkreis


def test_leerer_nummernkreis_beginnt_bei_eins(client: TestClient):
    headers, _ = _aufbau(client)
    assert _kreis(client, headers) == {
        "jahr": JAHR, "naechste_nummer": 1, "naechste_rechnungsnummer": f"RE-{JAHR}-0001", "hoechste_bilantiq": 0,
        "hoechste_altsystem": None, "mindestens": 1, "kollision": False, "vorschlag": None,
    }


def test_vergebene_nummern_heben_den_stand_an(client: TestClient):
    headers, kontakt_id = _aufbau(client)
    _finalisieren(client, headers, kontakt_id)
    _finalisieren(client, headers, kontakt_id)
    kreis = _kreis(client, headers)
    assert (kreis["naechste_nummer"], kreis["hoechste_bilantiq"], kreis["mindestens"]) == (3, 2, 3)


def test_hoechste_altnummer_gleichen_formats_wird_erkannt_und_schlaegt_eine_startnummer_vor(client: TestClient):
    headers, _ = _aufbau(client, f"RE-{JAHR}-0150", f"RE {JAHR} 7", f"RE{JAHR}0042", "ALT-9999", f"RE-{JAHR - 1}-0900")
    kreis = _kreis(client, headers)
    assert kreis["hoechste_altsystem"] == 150  # nur das Format RE-<laufendes Jahr>-N, fuehrende Nullen egal
    assert kreis["kollision"] is True and kreis["vorschlag"] == 151 and kreis["mindestens"] == 151


def test_nur_inhaber_setzt_die_naechste_nummer_und_sie_wird_danach_vergeben(client: TestClient):
    headers, kontakt_id = _aufbau(client, f"RE-{JAHR}-0150")
    gesetzt = client.put("/einstellungen/nummernkreis", headers=headers, json={"naechste_nummer": 151})
    assert gesetzt.status_code == 200, gesetzt.text
    assert (gesetzt.json()["naechste_rechnungsnummer"], gesetzt.json()["kollision"]) == (f"RE-{JAHR}-0151", False)

    _, final = _finalisieren(client, headers, kontakt_id)
    assert final.json()["nummer"] == f"RE-{JAHR}-0151"
    assert _kreis(client, headers)["naechste_nummer"] == 152

    with SessionLocal() as db:
        assert db.query(AuditLogEintrag).filter(AuditLogEintrag.aktion == "nummernkreis_gesetzt").count() == 1


def test_naechste_nummer_laesst_sich_nur_erhoehen_und_nicht_unter_vergebene_oder_alte_nummern_setzen(client: TestClient):
    headers, kontakt_id = _aufbau(client, f"RE-{JAHR}-0150")
    url = "/einstellungen/nummernkreis"
    assert client.put(url, headers=headers, json={"naechste_nummer": 150}).status_code == 400
    zu_niedrig = client.put(url, headers=headers, json={"naechste_nummer": 100})
    assert zu_niedrig.status_code == 400 and f"RE-{JAHR}-0150" in zu_niedrig.json()["detail"] and f"RE-{JAHR}-0151" in zu_niedrig.json()["detail"]
    assert client.put(url, headers=headers, json={"naechste_nummer": 200}).status_code == 200
    senken = client.put(url, headers=headers, json={"naechste_nummer": 160})
    assert senken.status_code == 400 and "nur erhöhen" in senken.json()["detail"]
    assert client.put(url, headers=headers, json={"naechste_nummer": 0}).status_code == 422
    assert client.put(url, headers=headers, json={"naechste_nummer": 1_000_000}).status_code == 422
    # gleicher Wert wie jetzt ist erlaubt (nichts aendert sich)
    assert client.put(url, headers=headers, json={"naechste_nummer": 200}).status_code == 200


def test_mitglied_darf_den_nummernkreis_sehen_aber_nicht_aendern(client: TestClient):
    headers, _ = _aufbau(client)
    code = client.post("/auth/einladungen", headers=headers, json={"rolle": "mitglied"}).json()["code"]
    mitglied = _register_and_verify(client, "mitglied@example.com", einladungscode=code)
    assert client.get("/einstellungen/nummernkreis", headers=mitglied).status_code == 200
    assert client.put("/einstellungen/nummernkreis", headers=mitglied, json={"naechste_nummer": 50}).status_code == 403
    assert client.get("/einstellungen/nummernkreis").status_code == 401


def test_nummernkreise_zweier_mandanten_sind_getrennt(client: TestClient):
    kevin, _ = _aufbau(client, f"RE-{JAHR}-0150")
    anna, _ = _aufbau(client, email="anna@example.com")
    assert _kreis(client, anna)["hoechste_altsystem"] is None and not _kreis(client, anna)["kollision"]
    assert client.put("/einstellungen/nummernkreis", headers=kevin, json={"naechste_nummer": 151}).status_code == 200
    assert _kreis(client, anna)["naechste_nummer"] == 1


# ---------------------------------------------------------------------------
# Schutz vor doppelten Nummern


def test_finalisieren_vergibt_keine_nummer_die_es_im_altsystem_gibt(client: TestClient):
    headers, kontakt_id = _aufbau(client, f"RE-{JAHR}-0001")  # genau die Nummer, die Bilantiq als naechste vergeben wuerde
    entwurf, antwort = _finalisieren(client, headers, kontakt_id)
    assert antwort.status_code == 409
    assert f"RE-{JAHR}-0001" in antwort.json()["detail"] and "Nummernkreis fortsetzen" in antwort.json()["detail"]
    # Nichts wurde vergeben: Entwurf bleibt Entwurf, der Zaehler steht unveraendert.
    assert client.get(f"/invoices/{entwurf['id']}", headers=headers).json()["status"] == "entwurf"
    assert _kreis(client, headers)["naechste_nummer"] == 1

    assert client.put("/einstellungen/nummernkreis", headers=headers, json={"naechste_nummer": 2}).status_code == 200
    ok = client.post(f"/invoices/{entwurf['id']}/finalize", headers=headers)
    assert ok.status_code == 200 and ok.json()["nummer"] == f"RE-{JAHR}-0002"


def test_auch_die_stornorechnung_bekommt_keine_doppelte_nummer(client: TestClient):
    headers, kontakt_id = _aufbau(client)
    _, final = _finalisieren(client, headers, kontakt_id)
    assert final.json()["nummer"] == f"RE-{JAHR}-0001"
    assert _post(client, headers, "/stammdaten/rechnungen/import", _alt_csv(f"RE-{JAHR}-0002"), _opt()).status_code == 200

    storno = client.post(f"/invoices/{final.json()['id']}/storno", headers=headers)
    assert storno.status_code == 409
    assert client.get(f"/invoices/{final.json()['id']}", headers=headers).json()["status"] == "final"  # Original unveraendert
    assert _kreis(client, headers)["naechste_nummer"] == 2


def test_andere_schreibweise_derselben_nummer_kollidiert_ebenfalls(client: TestClient):
    headers, kontakt_id = _aufbau(client, f"re {JAHR} 0001")
    assert _finalisieren(client, headers, kontakt_id)[1].status_code == 409


def test_nummer_eines_anderen_mandanten_blockiert_nicht(client: TestClient):
    _aufbau(client, f"RE-{JAHR}-0001")
    headers, kontakt_id = _aufbau(client, email="anna@example.com")
    assert _finalisieren(client, headers, kontakt_id)[1].json()["nummer"] == f"RE-{JAHR}-0001"


# ---------------------------------------------------------------------------
# Umzugsstatus


def _schritte(client, headers) -> dict:
    antwort = client.get("/umzug", headers=headers)
    assert antwort.status_code == 200, antwort.text
    return {s["id"]: s for s in antwort.json()["schritte"]} | {"_summe": antwort.json()}


def test_neuer_mandant_hat_noch_nichts_uebernommen(client: TestClient):
    headers, _ = _aufbau(client)
    schritte = _schritte(client, headers)
    assert [k for k in schritte if k != "_summe"] == ["export", "kontakte", "produkte", "rechnungen", "nummernkreis", "offene_posten", "kontoauszug", "steuerberater"]
    assert {k: v["status"] for k, v in schritte.items() if k != "_summe"} == {
        "export": "offen", "kontakte": "offen", "produkte": "offen", "rechnungen": "offen", "nummernkreis": "nicht_noetig",
        "offene_posten": "nicht_noetig", "kontoauszug": "offen", "steuerberater": "offen",
    }
    assert (schritte["_summe"]["erledigt"], schritte["_summe"]["gesamt"]) == (0, 6)  # ohne "nicht noetig"
    assert schritte["kontoauszug"]["hinweis"] is None
    assert schritte["export"]["ziel"] is None and "zehn Jahre" in schritte["export"]["beschreibung"]
    assert schritte["kontakte"]["nur_inhaber"] and schritte["kontakte"]["ziel"] == "contacts" and schritte["kontakte"]["aktion"] == "import"
    assert schritte["rechnungen"]["ansicht"] == "altsystem"
    assert client.get("/umzug").status_code == 401


def test_status_folgt_den_importen_dem_nummernkreis_der_bank_und_dem_steuerberater(client: TestClient):
    headers, _ = _aufbau(client)
    kontakte = _post(client, headers, "/stammdaten/kontakte/import", KONTAKTE_CSV, {"zuordnung": KONTAKT_ZUORDNUNG, "fehlerhafte_auslassen": True})
    assert kontakte.status_code == 200, kontakte.text
    schritte = _schritte(client, headers)
    assert schritte["kontakte"]["status"] == "erledigt" and "2 Kontakte übernommen" in schritte["kontakte"]["detail"]  # K-1 gab es schon
    assert schritte["export"]["status"] == "erledigt"  # wer importiert hat, hat exportiert

    importiert = _post(client, headers, "/stammdaten/rechnungen/import", _alt_csv(f"RE-{JAHR}-0150", f"RE-{JAHR}-0151"), _opt()).json()
    schritte = _schritte(client, headers)
    assert schritte["rechnungen"]["status"] == "erledigt" and "2 Rechnungen übernommen" in schritte["rechnungen"]["detail"] and "2 offen" in schritte["rechnungen"]["detail"]
    assert schritte["nummernkreis"]["status"] == "offen"
    assert f"RE-{JAHR}-0001" in schritte["nummernkreis"]["detail"] and f"RE-{JAHR}-0151" in schritte["nummernkreis"]["detail"]
    assert schritte["offene_posten"]["status"] == "info" and "2 offene Rechnungen über 238,00 €" in schritte["offene_posten"]["detail"]

    assert client.put("/einstellungen/nummernkreis", headers=headers, json={"naechste_nummer": 152}).status_code == 200
    assert _schritte(client, headers)["nummernkreis"]["status"] == "erledigt"

    client.post("/bank/konten", headers=headers, json={"bezeichnung": "Konto"})
    client.patch("/auth/mandant", headers=headers, json={"steuerberater_name": "Kanzlei Beispiel"})
    schritte = _schritte(client, headers)
    assert schritte["kontoauszug"]["status"] == "erledigt" and schritte["steuerberater"]["status"] == "erledigt"

    # Ein zurueckgenommener Import zaehlt nicht mehr.
    client.post(f"/stammdaten/importe/{importiert['import_id']}/rueckgaengig", headers=headers)
    schritte = _schritte(client, headers)
    assert schritte["rechnungen"]["status"] == "offen" and schritte["nummernkreis"]["status"] == "nicht_noetig"
    assert schritte["offene_posten"]["status"] == "nicht_noetig"


def test_bezahlte_altrechnungen_fallen_aus_den_offenen_posten(client: TestClient):
    headers, _ = _aufbau(client, f"RE-{JAHR}-0150")
    rechnung_id = client.get("/altrechnungen", headers=headers).json()["eintraege"][0]["id"]
    assert client.post(f"/altrechnungen/{rechnung_id}/zahlung", headers=headers, json={}).status_code == 200
    schritte = _schritte(client, headers)
    assert schritte["offene_posten"]["status"] == "nicht_noetig"
    assert schritte["rechnungen"]["detail"].endswith("0 offen")
