from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)

FAKE_RECEIPT_BYTES = b"\x89PNG\r\n\x1a\nfake-bytes-for-hashing-only"


def _paid_invoice(client: TestClient, headers: dict, *, netto: str, bezahlt_am: str) -> dict:
    kontakt_id = _kontakt(client, headers)
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id,
            "leistungsdatum": bezahlt_am, "faelligkeitsdatum": bezahlt_am, "waehrung": "EUR",
            "positionen": [{"beschreibung": "Leistung", "menge": "1", "einzelpreis": netto, "ust_satz": "19.00"}],
        },
    ).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
    client.post(f"/invoices/{final['id']}/bezahlt", headers=headers, json={"bezahlt_am": bezahlt_am})
    return final


def _booked_ausgabe(
    client: TestClient, headers: dict, *, brutto: str, ust_satz: str, datum: str, zahlungsdatum: str | None = None
) -> dict:
    upload = client.post(
        "/belege", headers=headers, files={"file": ("beleg.png", FAKE_RECEIPT_BYTES + brutto.encode(), "image/png")},
        data={"force": "false"},
    ).json()
    return client.post(
        f"/belege/{upload['id']}/bestaetigen", headers=headers,
        json={
            "betrag": brutto, "datum": datum, "zahlungsdatum": zahlungsdatum or datum,
            "anbieter": "Lieferant", "ust_satz": ust_satz, "kategorie": "Buerobedarf",
        },
    ).json()


def test_euer_counts_only_invoices_paid_within_the_year(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-03-15")
    _paid_invoice(client, headers, netto="500.00", bezahlt_am=f"{this_year - 1}-11-01")  # last year — excluded

    resp = client.get(f"/berichte/euer?jahr={this_year}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["anzahl_einnahmen"] == 1
    assert float(body["betriebseinnahmen_netto"]) == 1000.00


def test_euer_excludes_unpaid_but_counts_offene_forderungen(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": date.today().isoformat(),
            "faelligkeitsdatum": (date.today() + timedelta(days=14)).isoformat(), "waehrung": "EUR",
            "positionen": [{"beschreibung": "Unbezahlt", "menge": "1", "einzelpreis": "200.00", "ust_satz": "19.00"}],
        },
    ).json()
    client.post(f"/invoices/{draft['id']}/finalize", headers=headers)

    resp = client.get("/berichte/euer", headers=headers).json()
    assert resp["anzahl_einnahmen"] == 0
    assert float(resp["offene_forderungen_brutto"]) == 238.00


def test_euer_subtracts_expenses_netto(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-06-01")
    _booked_ausgabe(client, headers, brutto="119.00", ust_satz="19.00", datum=f"{this_year}-06-02")  # netto 100.00

    resp = client.get(f"/berichte/euer?jahr={this_year}", headers=headers).json()
    assert resp["anzahl_ausgaben"] == 1
    assert abs(float(resp["betriebsausgaben_netto"]) - 100.00) < 0.01
    assert abs(float(resp["ueberschuss_netto"]) - 900.00) < 0.01



def test_euer_uses_payment_date_not_receipt_date(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _booked_ausgabe(
        client,
        headers,
        brutto="119.00",
        ust_satz="19.00",
        datum=f"{this_year - 1}-12-20",
        zahlungsdatum=f"{this_year}-01-05",
    )

    current = client.get(f"/berichte/euer?jahr={this_year}", headers=headers).json()
    previous = client.get(f"/berichte/euer?jahr={this_year - 1}", headers=headers).json()

    assert abs(float(current["betriebsausgaben_netto"]) - 100.00) < 0.01
    assert float(previous["betriebsausgaben_netto"]) == 0.0

def test_euer_defaults_to_current_year(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/euer", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["jahr"] == date.today().year


def test_euer_is_isolated_per_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="5000.00", bezahlt_am=f"{this_year}-01-10")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/berichte/euer?jahr={this_year}", headers=lea_headers).json()
    assert resp["anzahl_einnahmen"] == 0
    assert float(resp["betriebseinnahmen_netto"]) == 0.0


def test_dashboard_aggregiert_monatswerte_offene_posten_und_top_listen(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-03-15")
    _booked_ausgabe(client, headers, brutto="238.00", ust_satz="19.00", datum=f"{this_year}-03-20")

    kontakt_id = _kontakt(client, headers)
    offen = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": date.today().isoformat(),
            "faelligkeitsdatum": (date.today() - timedelta(days=5)).isoformat(), "waehrung": "EUR",
            "positionen": [{"beschreibung": "Ueberfaellig", "menge": "1", "einzelpreis": "300.00", "ust_satz": "19.00"}],
        },
    ).json()
    client.post(f"/invoices/{offen['id']}/finalize", headers=headers)

    resp = client.get(f"/berichte/dashboard?jahr={this_year}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["monatswerte"]) == 12
    maerz = next(m for m in body["monatswerte"] if m["monat"] == 3)
    assert float(maerz["einnahmen"]) == 1000.00
    assert float(maerz["ausgaben"]) == 200.00  # 238 brutto / 1.19

    assert body["faellige_rechnungen"]["anzahl"] == 1
    assert float(body["faellige_rechnungen"]["betrag"]) == 357.00  # 300 + 19%

    assert len(body["top_kunden"]) == 1
    assert float(body["top_kunden"][0]["betrag"]) == 1190.00  # 1000 + 19%

    assert len(body["top_ausgaben_kategorien"]) == 1
    assert body["top_ausgaben_kategorien"][0]["name"] == "Buerobedarf"

    assert len(body["verlauf"]) > 0


def test_dashboard_ist_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="5000.00", bezahlt_am=f"{this_year}-01-10")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/berichte/dashboard?jahr={this_year}", headers=lea_headers).json()
    assert float(resp["einnahmen"]) == 0.0
    assert resp["top_kunden"] == []


def test_susa_soll_und_haben_summen_sind_immer_gleich(client: TestClient):
    """Grundeigenschaft doppelter Buchfuehrung: jede Buchungszeile bebucht eine Seite
    von Konto und die Gegenseite von Gegenkonto mit demselben Betrag, also muss die
    Gesamtsumme Soll ueber alle Konten immer der Gesamtsumme Haben entsprechen."""
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-03-15")
    _booked_ausgabe(client, headers, brutto="119.00", ust_satz="19.00", datum=f"{this_year}-03-16")

    resp = client.get(f"/berichte/susa?jahr={this_year}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["summe_soll"]) == float(body["summe_haben"])
    assert float(body["summe_soll"]) > 0


def test_susa_zeigt_bank_und_erloeskonto_nach_bezahlter_rechnung(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-03-15")

    body = client.get(f"/berichte/susa?jahr={this_year}", headers=headers).json()
    konten = {k["konto"]: k for k in body["konten"]}
    assert "1200" in konten and "8400" in konten
    assert float(konten["1200"]["soll"]) == 1190.00  # brutto bei 19% USt
    assert float(konten["8400"]["haben"]) == 1190.00
    assert float(konten["8400"]["saldo"]) == -1190.00  # Erloeskonto ist ein Haben-Konto


def test_susa_ist_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="1000.00", bezahlt_am=f"{this_year}-01-10")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/berichte/susa?jahr={this_year}", headers=lea_headers).json()
    assert resp["konten"] == []
    assert float(resp["summe_soll"]) == 0.0


def test_bwa_trennt_erloese_und_kosten_und_rechnet_ergebnis(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="1000.00", bezahlt_am=f"{this_year}-03-15")
    _booked_ausgabe(client, headers, brutto="119.00", ust_satz="19.00", datum=f"{this_year}-03-16")  # netto 100.00

    resp = client.get(f"/berichte/bwa?jahr={this_year}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["erloese_gesamt"]) == 1190.00  # BWA rechnet mit Brutto-Kontobewegungen, wie SuSa/DATEV
    assert float(body["kosten_gesamt"]) == 119.00
    assert abs(float(body["vorlaeufiges_ergebnis"]) - 1071.00) < 0.01
    assert body["erloes_posten"][0]["konto"] == "8400"
    assert body["kosten_posten"][0]["konto"] == "6815"  # Buerobedarf


def test_bwa_ohne_buchungen_ist_ausgeglichen_null(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/bwa", headers=headers).json()
    assert resp["erloes_posten"] == []
    assert resp["kosten_posten"] == []
    assert float(resp["vorlaeufiges_ergebnis"]) == 0.0


def test_bwa_ist_isoliert_pro_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="1000.00", bezahlt_am=f"{this_year}-01-10")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/berichte/bwa?jahr={this_year}", headers=lea_headers).json()
    assert resp["erloes_posten"] == []
