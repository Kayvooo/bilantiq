import csv
import io
from datetime import date

from fastapi.testclient import TestClient

from tests.test_invoices import _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _rows(csv_bytes: bytes) -> list[list[str]]:
    text = csv_bytes.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def _paid_invoice(client: TestClient, headers: dict, *, netto: str, ust_satz: str, bezahlt_am: str) -> dict:
    kontakt_id = _kontakt(client, headers)
    draft = client.post(
        "/invoices", headers=headers,
        json={
            "kontakt_id": kontakt_id, "leistungsdatum": bezahlt_am, "faelligkeitsdatum": bezahlt_am, "waehrung": "EUR",
            "positionen": [{"beschreibung": "Leistung", "menge": "1", "einzelpreis": netto, "ust_satz": ust_satz}],
        },
    ).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
    client.post(f"/invoices/{final['id']}/bezahlt", headers=headers, json={"bezahlt_am": bezahlt_am})
    return final


def _booked_ausgabe(
    client: TestClient, headers: dict, *, brutto: str, ust_satz: str, kategorie: str,
    datum: str, zahlungsdatum: str | None = None,
) -> dict:
    upload = client.post(
        "/belege", headers=headers, files={"file": ("beleg.png", b"\x89PNG\r\n\x1a\n" + brutto.encode(), "image/png")},
        data={"force": "false"},
    ).json()
    return client.post(
        f"/belege/{upload['id']}/bestaetigen", headers=headers,
        json={
            "betrag": brutto, "datum": datum, "zahlungsdatum": zahlungsdatum or datum,
            "anbieter": "Lieferant", "ust_satz": ust_satz, "kategorie": kategorie,
        },
    ).json()


def test_datev_header_row_has_buchungsstapel_category(client: TestClient):
    headers = _onboarded_mandant(client)
    resp = client.get("/berichte/datev-export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")

    rows = _rows(resp.content)
    header = rows[0]
    assert header[0] == "EXTF"
    assert header[2] == "21"  # Kategorie: Buchungsstapel
    assert header[3] == "Buchungsstapel"
    assert rows[1] == [
        "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs", "Basis-Umsatz",
        "WKZ Basis-Umsatz", "Konto", "Gegenkonto (ohne BU-Schluessel)", "BU-Schluessel", "Belegdatum",
        "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext",
    ]


def test_datev_export_includes_paid_invoice_as_erloes_buchung(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    invoice = _paid_invoice(client, headers, netto="1000.00", ust_satz="19.00", bezahlt_am=f"{this_year}-03-10")

    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=headers).content)
    booking_rows = rows[2:]
    assert len(booking_rows) == 1
    row = booking_rows[0]
    assert row[0] == "1190,00"  # brutto
    assert row[1] == "S"
    assert row[6] == "1200"  # Bank
    assert row[7] == "8400"  # SKR03 Erloese 19%
    assert row[8] == "3"  # BU-Schluessel 19% Erloes
    assert row[10] == invoice["nummer"]


def test_datev_export_includes_ausgabe_as_aufwand_buchung(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _booked_ausgabe(client, headers, brutto="119.00", ust_satz="19.00", kategorie="Software/IT", datum=f"{this_year}-04-01")

    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=headers).content)
    booking_rows = rows[2:]
    assert len(booking_rows) == 1
    row = booking_rows[0]
    assert row[0] == "119,00"
    assert row[1] == "S"
    assert row[6] == "6835"  # SKR03 Software/IT
    assert row[7] == "1200"  # Bank
    assert row[8] == "9"  # BU-Schluessel 19% Vorsteuer



def test_datev_splits_mixed_vat_expense_into_two_rows(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    upload = client.post(
        "/belege",
        headers=headers,
        files={"file": ("mixed.png", b"\x89PNG\r\n\x1a\n" + b"datev-mixed", "image/png")},
        data={"force": "false"},
    ).json()
    response = client.post(
        f"/belege/{upload['id']}/bestaetigen",
        headers=headers,
        json={
            "betrag": "226.00",
            "datum": f"{this_year}-04-01",
            "zahlungsdatum": f"{this_year}-04-10",
            "anbieter": "Restaurant",
            "steueranteile": [
                {"ust_satz": "7.00", "bruttobetrag": "107.00"},
                {"ust_satz": "19.00", "bruttobetrag": "119.00"},
            ],
            "kategorie": "Bewirtung",
            "konto": "6644",
        },
    )
    assert response.status_code == 201

    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=headers).content)[2:]
    assert len(rows) == 2
    assert {row[0] for row in rows} == {"107,00", "119,00"}
    assert {row[8] for row in rows} == {"8", "9"}
    assert {row[9] for row in rows} == {"1004"}

def test_datev_belegdatum_keeps_leading_zero(client: TestClient):
    """Regression: int(strftime("%d%m")) silently turned "0509" into 509 — a single-day
    or single-month date must keep its four-digit TTMM shape."""
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    invoice = _paid_invoice(client, headers, netto="100.00", ust_satz="19.00", bezahlt_am=f"{this_year}-01-05")

    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=headers).content)
    assert rows[2][9] == "0501"
    assert invoice["nummer"] is not None


def test_datev_export_excludes_bookings_outside_the_year(client: TestClient):
    headers = _onboarded_mandant(client)
    this_year = date.today().year
    _paid_invoice(client, headers, netto="500.00", ust_satz="19.00", bezahlt_am=f"{this_year - 1}-12-15")

    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=headers).content)
    assert len(rows) == 2  # only the two header rows, no bookings


def test_datev_export_uses_configured_berater_und_mandantennummer(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"datev_beraternummer": "42", "datev_mandantennummer": "777"})

    rows = _rows(client.get("/berichte/datev-export", headers=headers).content)
    header = rows[0]
    assert header[10] == "42"
    assert header[11] == "777"


def test_datev_export_is_isolated_per_mandant(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    this_year = date.today().year
    _paid_invoice(client, kevin_headers, netto="5000.00", ust_satz="19.00", bezahlt_am=f"{this_year}-02-01")

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    rows = _rows(client.get(f"/berichte/datev-export?jahr={this_year}", headers=lea_headers).content)
    assert len(rows) == 2
