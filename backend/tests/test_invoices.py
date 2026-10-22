from datetime import date, timedelta

import pyotp
from fastapi.testclient import TestClient
from lxml import etree


def _onboarded_mandant(client: TestClient, email: str = "kevin@example.com") -> dict:
    """Registers, completes MFA enrollment and sets a USt-IdNr + address on the
    mandant so it is eligible for e-invoicing. Returns headers + access token."""
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery staple", "firmenname": "Kevin GmbH"},
    ).json()
    pre_auth = reg["pre_auth_token"]
    headers_pre = {"Authorization": f"Bearer {pre_auth}"}

    secret = client.post("/auth/mfa/setup", headers=headers_pre).json()["secret"]
    code = pyotp.TOTP(secret).now()
    access_token = client.post("/auth/mfa/verify", headers=headers_pre, json={"code": code}).json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    client.patch(
        "/auth/mandant", headers=headers,
        json={
            "ust_id": "DE123456789", "adresse": "Musterstr. 1, 10115 Berlin", "iban": "DE02120300000000202051",
            "telefon": "+49 30 1234567", "kontakt_email": "rechnung@example.com",
        },
    )
    return headers


def _kontakt(
    client: TestClient, headers: dict, *, land: str = "DE", geschaeftskunde: bool = True, email: str | None = None,
) -> str:
    daten = {
        "name": "Beispiel Kunde GmbH",
        "strasse": "Kundenweg 2",
        "plz": "80331",
        "ort": "Muenchen",
        "land": land,
        "ist_geschaeftskunde": geschaeftskunde,
    }
    if email:
        daten["email"] = email
    resp = client.post("/kontakte", headers=headers, json=daten)
    assert resp.status_code == 201
    return resp.json()["id"]


def _invoice_payload(kontakt_id: str) -> dict:
    today = date.today()
    return {
        "kontakt_id": kontakt_id,
        "leistungsdatum": today.isoformat(),
        "faelligkeitsdatum": (today + timedelta(days=14)).isoformat(),
        "waehrung": "EUR",
        "positionen": [
            {"beschreibung": "Beratung", "menge": "2", "einzelpreis": "500.00", "ust_satz": "19.00"},
            {"beschreibung": "Reisekosten", "menge": "1", "einzelpreis": "50.00", "ust_satz": "0.00"},
        ],
    }


def test_invoice_totals_computed_from_positions(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    resp = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "entwurf"
    assert body["nummer"] is None
    assert body["kontakt_name"] == "Beispiel Kunde GmbH"
    assert float(body["netto_gesamt"]) == 1050.00
    assert float(body["ust_gesamt"]) == 190.00  # 19% only on the 1000.00 beratung line
    assert float(body["brutto_gesamt"]) == 1240.00



def test_invoice_list_shows_kontakt_name_not_just_id(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id))

    resp = client.get("/invoices", headers=headers)
    assert resp.status_code == 200
    [invoice] = resp.json()
    assert invoice["kontakt_name"] == "Beispiel Kunde GmbH"

def test_finalize_assigns_gapless_sequential_numbers(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    numbers = []
    for _ in range(3):
        draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
        final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()
        assert final["status"] == "final"
        numbers.append(final["nummer"])

    year = date.today().year
    assert numbers == [f"RE-{year}-0001", f"RE-{year}-0002", f"RE-{year}-0003"]


def test_cannot_finalize_twice(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    client.post(f"/invoices/{draft['id']}/finalize", headers=headers)

    second = client.post(f"/invoices/{draft['id']}/finalize", headers=headers)
    assert second.status_code == 400


def test_e_rechnung_blocked_with_specific_missing_fields(client: TestClient):
    # Fresh mandant WITHOUT ust_id/steuernummer/adresse set.
    reg = client.post(
        "/auth/register",
        json={"email": "unvollstaendig@example.com", "password": "correct horse battery staple", "firmenname": "Luecke GmbH"},
    ).json()
    headers_pre = {"Authorization": f"Bearer {reg['pre_auth_token']}"}
    secret = client.post("/auth/mfa/setup", headers=headers_pre).json()["secret"]
    access_token = client.post(
        "/auth/mfa/verify", headers=headers_pre, json={"code": pyotp.TOTP(secret).now()}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    client.post(f"/invoices/{draft['id']}/finalize", headers=headers)

    check = client.get(f"/invoices/{draft['id']}/e-rechnung-pruefung", headers=headers)
    assert "USt-IdNr. oder Steuernummer (Verkaeufer)" in check.json()["fehlende_felder"]
    assert "Anschrift (Verkaeufer)" in check.json()["fehlende_felder"]

    export = client.post(f"/invoices/{draft['id']}/e-rechnung", headers=headers)
    assert export.status_code == 400
    assert "USt-IdNr" in export.json()["detail"]


def test_e_rechnung_xml_well_formed_and_matches_totals(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers, email="einkauf@kunde.example")
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()

    resp = client.post(f"/invoices/{final['id']}/e-rechnung", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")

    root = etree.fromstring(resp.content)
    ns = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
    assert root.find("cbc:ID", ns).text == final["nummer"]
    assert root.find("cbc:DocumentCurrencyCode", ns).text == "EUR"

    ns_cac = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2", **ns}
    payable = root.find(".//cac:LegalMonetaryTotal/cbc:PayableAmount", ns_cac)
    assert float(payable.text) == float(final["brutto_gesamt"])


def test_e_rechnung_requires_finalized_invoice(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()

    resp = client.post(f"/invoices/{draft['id']}/e-rechnung", headers=headers)
    assert resp.status_code == 400


def test_b2b_germany_flags_e_rechnung_hinweis(client: TestClient):
    headers = _onboarded_mandant(client)
    de_kontakt = _kontakt(client, headers, land="DE", geschaeftskunde=True)
    us_kontakt = _kontakt(client, headers, land="US", geschaeftskunde=True)
    private_kontakt = _kontakt(client, headers, land="DE", geschaeftskunde=False)

    de_invoice = client.post("/invoices", headers=headers, json=_invoice_payload(de_kontakt)).json()
    us_invoice = client.post("/invoices", headers=headers, json=_invoice_payload(us_kontakt)).json()
    private_invoice = client.post("/invoices", headers=headers, json=_invoice_payload(private_kontakt)).json()

    assert de_invoice["e_rechnung_hinweis"] is True
    assert us_invoice["e_rechnung_hinweis"] is False
    assert private_invoice["e_rechnung_hinweis"] is False


def test_storno_creates_negative_credit_note_and_marks_original(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    final = client.post(f"/invoices/{draft['id']}/finalize", headers=headers).json()

    storno = client.post(f"/invoices/{final['id']}/storno", headers=headers)
    assert storno.status_code == 201
    storno_body = storno.json()
    assert storno_body["korrigiert_invoice_id"] == final["id"]
    assert float(storno_body["brutto_gesamt"]) == -float(final["brutto_gesamt"])
    assert storno_body["nummer"] != final["nummer"]

    original_after = client.get(f"/invoices/{final['id']}", headers=headers).json()
    assert original_after["status"] == "storniert"
    # The original's own figures never change — only its lifecycle status does.
    assert original_after["brutto_gesamt"] == final["brutto_gesamt"]


def test_cannot_storno_a_draft(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()

    resp = client.post(f"/invoices/{draft['id']}/storno", headers=headers)
    assert resp.status_code == 400


def test_pdf_endpoint_returns_pdf_bytes(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()

    resp = client.get(f"/invoices/{draft['id']}/pdf", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_pdf_reflects_gewaehlte_rechnungsvorlage(client: TestClient):
    """Die Vorlage lebt am Mandanten (app/auth/models.py), nicht an der Rechnung — ein
    einziges PATCH /auth/mandant muss also reichen, damit das naechste Rechnungs-PDF
    sichtbar anders aussieht (siehe app/core/document_pdf.py::_stil_fuer)."""
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    klassisch_pdf = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content

    client.patch("/auth/mandant", headers=headers, json={"rechnungsvorlage": "modern", "akzentfarbe": "#AA3300"})
    modern_pdf = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content

    assert klassisch_pdf != modern_pdf


def test_editor_zusatzfelder_werden_gespeichert_und_zurueckgegeben(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _invoice_payload(kontakt_id)
    payload["positionen"][0]["kategorie"] = "Beratung"
    payload.update({
        "betreff": "Rechnung für Projekt Nordlicht",
        "kopftext": "Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihren Auftrag.",
        "fusstext": "Zahlbar bis zum [%ZAHLUNGSZIEL%]. Ansprechpartner: [%KONTAKTPERSON%]",
        "referenznummer": "PO-4711",
        "kostenstelle": "Marketing",
        "zahlungsmethode": "sepa_ueberweisung",
        "skonto_tage": 7,
        "skonto_prozent": "2.00",
    })
    resp = client.post("/invoices", headers=headers, json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["betreff"] == "Rechnung für Projekt Nordlicht"
    assert body["referenznummer"] == "PO-4711"
    assert body["kostenstelle"] == "Marketing"
    assert body["zahlungsmethode"] == "sepa_ueberweisung"
    assert body["skonto_tage"] == 7
    assert float(body["skonto_prozent"]) == 2.00
    assert body["positionen"][0]["kategorie"] == "Beratung"

    kategorien = client.get("/positionskategorien", headers=headers).json()
    assert {k["name"] for k in kategorien} == {"Beratung"}


def test_interne_kontaktperson_muss_zum_mandanten_gehoeren(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _invoice_payload(kontakt_id)
    payload["interne_kontaktperson_user_id"] = "nicht-vorhanden"
    resp = client.post("/invoices", headers=headers, json=payload)
    assert resp.status_code == 400


def test_positionskategorie_kann_geloescht_werden(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _invoice_payload(kontakt_id)
    payload["positionen"][0]["kategorie"] = "Workshop"
    client.post("/invoices", headers=headers, json=payload)

    kategorie = client.get("/positionskategorien", headers=headers).json()[0]
    resp = client.delete(f"/positionskategorien/{kategorie['id']}", headers=headers)
    assert resp.status_code == 204
    assert client.get("/positionskategorien", headers=headers).json() == []


def test_pdf_reflects_betreff_und_fusstext_override(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    ohne_override = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    ohne_pdf = client.get(f"/invoices/{ohne_override['id']}/pdf", headers=headers).content

    payload = _invoice_payload(kontakt_id)
    payload["betreff"] = "Sonderrechnung Projekt X"
    payload["fusstext"] = "Zahlbar bis [%ZAHLUNGSZIEL%]."
    mit_override = client.post("/invoices", headers=headers, json=payload).json()
    mit_pdf = client.get(f"/invoices/{mit_override['id']}/pdf", headers=headers).content

    assert ohne_pdf != mit_pdf


def test_vorschau_rendert_pdf_ohne_zu_speichern(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _invoice_payload(kontakt_id)
    payload["betreff"] = "Vorschau-Test"
    payload["positionen"][0]["kategorie"] = "Sollte nicht gespeichert werden"

    resp = client.post("/invoices/vorschau", headers=headers, json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"

    assert client.get("/invoices", headers=headers).json() == []
    assert client.get("/positionskategorien", headers=headers).json() == []


def test_cross_mandant_invoice_access_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_kontakt = _kontakt(client, kevin_headers)
    kevin_invoice = client.post("/invoices", headers=kevin_headers, json=_invoice_payload(kevin_kontakt)).json()

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.get(f"/invoices/{kevin_invoice['id']}", headers=lea_headers)
    assert resp.status_code == 404


def test_update_kontakt_changes_only_given_fields(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)

    resp = client.patch(f"/kontakte/{kontakt_id}", headers=headers, json={"email": "neu@example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "neu@example.com"
    assert body["name"] == "Beispiel Kunde GmbH"  # unset fields stay unchanged

    reread = client.get("/kontakte", headers=headers).json()
    assert reread[0]["email"] == "neu@example.com"


def test_cross_mandant_kontakt_update_is_404(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin@example.com")
    kevin_kontakt = _kontakt(client, kevin_headers)

    lea_headers = _onboarded_mandant(client, email="lea@example.com")
    resp = client.patch(f"/kontakte/{kevin_kontakt}", headers=lea_headers, json={"name": "Uebernommen"})
    assert resp.status_code == 404
