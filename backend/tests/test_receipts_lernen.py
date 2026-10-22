import pytest
from fastapi.testclient import TestClient

from app.receipts.lernen import HistorieIndex, normalisiere_anbieter
from tests.test_invoices import _onboarded_mandant as _mandant
from tests.test_receipts import (
    FAKE_IMAGE,
    _clear_extractor_override,  # noqa: F401  (autouse-Fixture)
    _extraction,
    _FakeExtractor,
    _onboarded_mandant,
    _use_extractor,
)

UNKLAR = dict(kategorie_vorschlag=("Sonstiges", 0.3))


def _beleg(client: TestClient, headers: dict, nummer: int, **extraction) -> dict:
    _use_extractor(_FakeExtractor(_extraction(**extraction)))
    antwort = client.post(
        "/belege", headers=headers, files={"file": (f"b{nummer}.png", FAKE_IMAGE + str(nummer).encode(), "image/png")},
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


def _buche(client: TestClient, headers: dict, beleg: dict, **payload) -> dict:
    antwort = client.post(f"/belege/{beleg['id']}/bestaetigen", headers=headers, json=payload)
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


@pytest.mark.parametrize(
    "name,erwartet",
    [
        ("Vodafone GmbH", "vodafone"),
        ("Deutsche Telekom AG.", "deutsche telekom"),
        ("  Müller & Söhne  KG ", "müller söhne"),
        ("", ""),
        (None, ""),
    ],
)
def test_anbieter_werden_vergleichbar_normalisiert(name, erwartet):
    assert normalisiere_anbieter(name) == erwartet


def test_gebuchte_kategorie_wird_beim_naechsten_beleg_desselben_anbieters_vorgeschlagen(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Hosting Müller GmbH", 0.9), **UNKLAR)
    assert erster["kategorie_vorschlag"]["unklar"] is True
    _buche(client, headers, erster, kategorie="Software/IT", konto="6835")

    zweiter = _beleg(client, headers, 2, anbieter=("Hosting Müller GmbH", 0.9), **UNKLAR)

    assert zweiter["kategorie_vorschlag"]["wert"] == "Software/IT"
    assert zweiter["kategorie_vorschlag"]["unklar"] is False
    assert zweiter["buchungskonto_vorschlag"] == "6835"
    assert zweiter["begruendung"] == "Gelernt aus 1 früherer Buchung bei Hosting Müller GmbH."


def test_gelerntes_konto_ersetzt_den_kontenrahmen_standard(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Server AG", 0.9), **UNKLAR)
    _buche(client, headers, erster, kategorie="Software/IT", konto="6300")

    zweiter = _beleg(client, headers, 2, anbieter=("Server AG", 0.9), **UNKLAR)

    assert zweiter["buchungskonto_vorschlag"] == "6300"


def test_vorschlag_gilt_auch_fuer_schon_hochgeladene_offene_belege(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Cloud GmbH", 0.9), **UNKLAR)
    offen = _beleg(client, headers, 2, anbieter=("Cloud GmbH", 0.9), **UNKLAR)
    assert offen["kategorie_vorschlag"]["unklar"] is True

    _buche(client, headers, erster, kategorie="Software/IT", konto="6835")

    liste = {b["id"]: b for b in client.get("/belege", headers=headers).json()}
    assert liste[offen["id"]]["kategorie_vorschlag"]["wert"] == "Software/IT"
    assert client.get(f"/belege/{offen['id']}", headers=headers).json()["kategorie_vorschlag"]["wert"] == "Software/IT"


def test_bestaetigung_ohne_angaben_uebernimmt_gelernte_kategorie_und_konto(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Büro Nord GmbH", 0.9), **UNKLAR)
    _buche(client, headers, erster, kategorie="Buerobedarf", konto="6815")
    zweiter = _beleg(client, headers, 2, anbieter=("Büro Nord GmbH", 0.9), **UNKLAR)

    ausgabe = _buche(client, headers, zweiter)

    assert ausgabe["kategorie"] == "Buerobedarf"
    assert ausgabe["konto"] == "6815"


def test_gewaehlte_andere_kategorie_nimmt_nicht_das_gelernte_konto(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Shop GmbH", 0.9), **UNKLAR)
    _buche(client, headers, erster, kategorie="Buerobedarf", konto="6300")
    zweiter = _beleg(client, headers, 2, anbieter=("Shop GmbH", 0.9), **UNKLAR)

    ausgabe = _buche(client, headers, zweiter, kategorie="Marketing")

    assert ausgabe["konto"] == "6600"


def test_teilname_des_anbieters_trifft_aber_kurze_namen_nicht(client: TestClient):
    headers = _onboarded_mandant(client)
    _buche(client, headers, _beleg(client, headers, 1, anbieter=("Vodafone GmbH", 0.9), **UNKLAR),
           kategorie="Telekommunikation", konto="6805")
    _buche(client, headers, _beleg(client, headers, 2, anbieter=("Bahn GmbH", 0.9), **UNKLAR),
           kategorie="Reisekosten", konto="6663")

    laenger = _beleg(client, headers, 3, anbieter=("Vodafone Deutschland GmbH", 0.9), **UNKLAR)
    andere_bahn = _beleg(client, headers, 4, anbieter=("Deutsche Bahn AG", 0.9), **UNKLAR)
    anderer_anbieter = _beleg(client, headers, 5, anbieter=("Telekom Deutschland GmbH", 0.9), **UNKLAR)

    assert laenger["kategorie_vorschlag"]["wert"] == "Telekommunikation"
    assert andere_bahn["kategorie_vorschlag"]["unklar"] is True
    assert anderer_anbieter["kategorie_vorschlag"]["unklar"] is True


def test_mehrheit_gewinnt_bei_widerspruch_und_gleichstand_gibt_keinen_vorschlag(client: TestClient):
    headers = _onboarded_mandant(client)
    for nummer, kategorie, konto in [(1, "Software/IT", "6835"), (2, "Software/IT", "6835"), (3, "Marketing", "6600")]:
        _buche(client, headers, _beleg(client, headers, nummer, anbieter=("Amazon EU", 0.9), **UNKLAR),
               kategorie=kategorie, konto=konto)

    mehrheit = _beleg(client, headers, 4, anbieter=("Amazon EU", 0.9), **UNKLAR)
    assert mehrheit["kategorie_vorschlag"]["wert"] == "Software/IT"
    assert mehrheit["begruendung"] == "Überwiegend gelernt: 2 von 3 früheren Buchungen bei Amazon EU."

    for nummer, kategorie, konto in [(10, "Software/IT", "6835"), (11, "Marketing", "6600")]:
        _buche(client, headers, _beleg(client, headers, nummer, anbieter=("Zufall GmbH", 0.9), **UNKLAR),
               kategorie=kategorie, konto=konto)
    gleichstand = _beleg(client, headers, 12, anbieter=("Zufall GmbH", 0.9), **UNKLAR)
    assert gleichstand["kategorie_vorschlag"]["unklar"] is True


def test_nach_drei_gleichen_buchungen_steigt_die_konfidenz(client: TestClient):
    headers = _onboarded_mandant(client)
    for nummer in (1, 2, 3):
        _buche(client, headers, _beleg(client, headers, nummer, anbieter=("Stamm GmbH", 0.9), **UNKLAR),
               kategorie="Bewirtung", konto="6644")

    vorschlag = _beleg(client, headers, 4, anbieter=("Stamm GmbH", 0.9), **UNKLAR)

    assert vorschlag["kategorie_vorschlag"]["confidence"] == 0.95
    assert vorschlag["begruendung"] == "Gelernt aus 3 früheren Buchungen bei Stamm GmbH."


def test_ein_unsicher_erkannter_anbieter_loest_kein_lernen_aus(client: TestClient):
    headers = _onboarded_mandant(client)
    _buche(client, headers, _beleg(client, headers, 1, anbieter=("Sicher GmbH", 0.9), **UNKLAR),
           kategorie="Marketing", konto="6600")

    unsicher = _beleg(client, headers, 2, anbieter=("Sicher GmbH", 0.3), **UNKLAR)

    assert unsicher["kategorie_vorschlag"]["unklar"] is True


def test_gelerntes_ueberschreibt_eine_sicherere_ocr_erkennung_nicht(client: TestClient):
    headers = _onboarded_mandant(client)
    _buche(client, headers, _beleg(client, headers, 1, anbieter=("Mix GmbH", 0.9), **UNKLAR),
           kategorie="Marketing", konto="6600")

    sicher_erkannt = _beleg(client, headers, 2, anbieter=("Mix GmbH", 0.9), kategorie_vorschlag=("Reisekosten", 0.95))

    assert sicher_erkannt["kategorie_vorschlag"]["wert"] == "Reisekosten"


def test_gelernter_ust_satz_ersetzt_nur_einen_unklaren_ocr_satz(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Steuer GmbH", 0.9), ust_satz=("7.00", 0.9), **UNKLAR)
    _buche(client, headers, erster, kategorie="Bewirtung", konto="6644")

    ohne_satz = _beleg(client, headers, 2, anbieter=("Steuer GmbH", 0.9), ust_satz=(None, 0.0), **UNKLAR)
    mit_satz = _beleg(client, headers, 3, anbieter=("Steuer GmbH", 0.9), ust_satz=("19.00", 0.9), **UNKLAR)

    assert ohne_satz["ust_satz"]["wert"] == "7.00"
    assert mit_satz["ust_satz"]["wert"] == "19.00"


def test_gemischte_steuersaetze_in_der_historie_ergeben_keinen_ust_vorschlag(client: TestClient):
    headers = _onboarded_mandant(client)
    erster = _beleg(client, headers, 1, anbieter=("Misch GmbH", 0.9), betrag=("30.00", 0.95), **UNKLAR)
    _buche(client, headers, erster, kategorie="Bewirtung", konto="6644", ust_satz=None,
           steueranteile=[{"ust_satz": "7", "bruttobetrag": "10.00"}, {"ust_satz": "19", "bruttobetrag": "20.00"}])

    zweiter = _beleg(client, headers, 2, anbieter=("Misch GmbH", 0.9), ust_satz=(None, 0.0), **UNKLAR)

    assert zweiter["kategorie_vorschlag"]["wert"] == "Bewirtung"
    assert zweiter["ust_satz"]["unklar"] is True


def test_historie_eines_mandanten_leckt_nicht_in_einen_anderen(client: TestClient):
    kopf_a = _onboarded_mandant(client, email="a@example.com")
    kopf_b = _onboarded_mandant(client, email="b@example.com")
    _buche(client, kopf_a, _beleg(client, kopf_a, 1, anbieter=("Geheim GmbH", 0.9), **UNKLAR),
           kategorie="Marketing", konto="6600")

    fremd = _beleg(client, kopf_b, 2, anbieter=("Geheim GmbH", 0.9), **UNKLAR)

    assert fremd["kategorie_vorschlag"]["unklar"] is True
    assert client.get("/belege/vorschlag", headers=kopf_b, params={"anbieter": "Geheim GmbH"}).json() == {
        "gefunden": False, "kategorie": None, "konto": None, "ust_satz": None, "confidence": None, "begruendung": None,
    }


def test_vorschlag_endpunkt_liefert_gelerntes_fuer_das_bestaetigungsformular(client: TestClient):
    headers = _onboarded_mandant(client)
    _buche(client, headers, _beleg(client, headers, 1, anbieter=("Formular GmbH", 0.9), **UNKLAR),
           kategorie="Buerobedarf", konto="6815")

    antwort = client.get("/belege/vorschlag", headers=headers, params={"anbieter": "formular"}).json()

    assert antwort["gefunden"] is True
    assert (antwort["kategorie"], antwort["konto"], antwort["ust_satz"]) == ("Buerobedarf", "6815", "19.00")
    assert antwort["confidence"] == 0.85


def test_lernen_ist_ohne_einschraenkung_verfuegbar(client: TestClient):
    headers = _mandant(client)

    antwort = client.get("/belege/vorschlag", headers=headers, params={"anbieter": "x"})

    assert antwort.status_code == 200
    assert antwort.json()["gefunden"] is False


def test_historie_index_ist_auf_die_letzten_buchungen_begrenzt(client: TestClient):
    headers = _onboarded_mandant(client)
    for nummer in (1, 2, 3):
        _buche(client, headers, _beleg(client, headers, nummer, anbieter=(f"Firma {nummer} GmbH", 0.9), **UNKLAR),
               kategorie="Marketing", konto="6600")
    from app.db import SessionLocal
    from app.receipts.models import Ausgabe

    with SessionLocal() as db:
        mandant_id = db.query(Ausgabe).first().mandant_id
        index = HistorieIndex.laden(db, mandant_id, limit=2)

    assert len(index._eintraege) == 2
