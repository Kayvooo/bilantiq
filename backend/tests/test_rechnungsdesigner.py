from datetime import date, timedelta
from io import BytesIO

import pikepdf
from fastapi.testclient import TestClient

from tests.test_invoices import _invoice_payload, _kontakt, _onboarded_mandant as _onboarded_mandant_basis


def _onboarded_mandant(client, email="kevin@example.com"):
    return _onboarded_mandant_basis(client, email=email)


def _pdf_seitenzahl(pdf_bytes: bytes) -> int:
    with pikepdf.Pdf.open(BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def _erste_rechnung_pdf(client: TestClient, headers: dict) -> bytes:
    kontakt_id = _kontakt(client, headers)
    draft = client.post("/invoices", headers=headers, json=_invoice_payload(kontakt_id)).json()
    return client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content


def test_sprache_de_und_en_erzeugen_unterschiedliches_pdf(client: TestClient):
    headers = _onboarded_mandant(client)
    pdf_de = _erste_rechnung_pdf(client, headers)

    client.patch("/auth/mandant", headers=headers, json={"sprache": "en"})
    pdf_en = _erste_rechnung_pdf(client, headers)

    assert pdf_de != pdf_en


def test_design_variante_schwarz_und_blau_aendern_pdf(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"rechnungsvorlage": "modern", "akzentfarbe": "#AA3300"})
    pdf_standard = _erste_rechnung_pdf(client, headers)

    client.patch("/auth/mandant", headers=headers, json={"design_variante": "schwarz"})
    pdf_schwarz = _erste_rechnung_pdf(client, headers)
    assert pdf_standard != pdf_schwarz

    client.patch("/auth/mandant", headers=headers, json={"design_variante": "blau"})
    pdf_blau = _erste_rechnung_pdf(client, headers)
    assert pdf_schwarz != pdf_blau

    client.patch("/auth/mandant", headers=headers, json={"design_variante": "einfach"})
    pdf_einfach = _erste_rechnung_pdf(client, headers)
    assert pdf_blau != pdf_einfach


def test_kundennummer_toggle_wirkt_nur_mit_wert_und_aktivem_toggle(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    client.patch(f"/kontakte/{kontakt_id}", headers=headers, json={"kundennummer": "K-4711"})
    draft = client.post(
        "/invoices", headers=headers,
        json={**_invoice_payload(kontakt_id), "kontakt_id": kontakt_id},
    ).json()
    ohne_toggle = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content

    client.patch("/auth/mandant", headers=headers, json={"zeige_kundennummer": True})
    mit_toggle = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content

    assert ohne_toggle != mit_toggle


def test_artikelnummer_und_ust_pro_position_toggles_aendern_pdf(client: TestClient):
    headers = _onboarded_mandant(client)
    kontakt_id = _kontakt(client, headers)
    payload = _invoice_payload(kontakt_id)
    payload["positionen"][0]["artikelnummer"] = "ART-99"
    draft = client.post("/invoices", headers=headers, json=payload).json()
    basis = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content

    client.patch("/auth/mandant", headers=headers, json={"zeige_artikelnummer": True})
    mit_artikelnummer = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content
    assert basis != mit_artikelnummer

    client.patch("/auth/mandant", headers=headers, json={"zeige_ust_pro_position": False})
    ohne_ust = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content
    assert mit_artikelnummer != ohne_ust


def test_absenderzeile_und_fusszeile_toggles_blenden_element_aus(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"fusszeile_text": "Bank Beispiel GmbH"})
    mit_beidem = _erste_rechnung_pdf(client, headers)

    client.patch("/auth/mandant", headers=headers, json={"zeige_fusszeile": False})
    ohne_fusszeile = _erste_rechnung_pdf(client, headers)
    assert mit_beidem != ohne_fusszeile

    client.patch("/auth/mandant", headers=headers, json={"zeige_absenderzeile": False})
    ohne_absender = _erste_rechnung_pdf(client, headers)
    assert ohne_fusszeile != ohne_absender


def test_girocode_nur_mit_iban_gerendert(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"zeige_girocode": True})
    ohne_iban = _erste_rechnung_pdf(client, headers)  # kein Fehler trotz fehlender IBAN

    client.patch("/auth/mandant", headers=headers, json={"iban": "DE89370400440532013000", "bic": "COBADEFFXXX"})
    mit_iban = _erste_rechnung_pdf(client, headers)

    assert ohne_iban != mit_iban


def test_viele_positionen_erzeugen_mehrseitiges_pdf_mit_seitenzahl(client: TestClient):
    headers = _onboarded_mandant(client)
    client.patch("/auth/mandant", headers=headers, json={"zeige_seitenzahlen": True})
    kontakt_id = _kontakt(client, headers)
    heute = date.today()
    payload = {
        "kontakt_id": kontakt_id,
        "leistungsdatum": heute.isoformat(),
        "faelligkeitsdatum": (heute + timedelta(days=14)).isoformat(),
        "waehrung": "EUR",
        "positionen": [
            {"beschreibung": f"Position {i}", "menge": "1", "einzelpreis": "10.00", "ust_satz": "19.00"}
            for i in range(60)
        ],
    }
    draft = client.post("/invoices", headers=headers, json=payload).json()
    pdf = client.get(f"/invoices/{draft['id']}/pdf", headers=headers).content
    assert _pdf_seitenzahl(pdf) > 1


def test_wenige_positionen_bleiben_einseitig(client: TestClient):
    headers = _onboarded_mandant(client)
    pdf = _erste_rechnung_pdf(client, headers)
    assert _pdf_seitenzahl(pdf) == 1


def test_logo_groesse_aendert_pdf(client: TestClient):
    headers = _onboarded_mandant(client)
    from io import BytesIO as IO
    from PIL import Image
    buf = IO()
    Image.new("RGB", (100, 50), (18, 61, 58)).save(buf, format="PNG")
    client.post("/auth/mandant/logo", headers=headers, files={"file": ("logo.png", buf.getvalue(), "image/png")})

    pdf_m = _erste_rechnung_pdf(client, headers)
    client.patch("/auth/mandant", headers=headers, json={"logo_groesse": "L"})
    pdf_l = _erste_rechnung_pdf(client, headers)
    assert pdf_m != pdf_l


def test_briefpapier_upload_auswaehlen_und_loeschen(client: TestClient):
    headers = _onboarded_mandant(client)
    from io import BytesIO as IO
    from PIL import Image
    buf = IO()
    Image.new("RGB", (210, 297), (250, 250, 245)).save(buf, format="PNG")

    upload = client.post(
        "/auth/briefpapier", headers=headers,
        data={"name": "Mein Briefpapier"}, files={"file": ("bg.png", buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 201
    briefpapier_id = upload.json()["id"]

    liste = client.get("/auth/briefpapier", headers=headers).json()
    assert len(liste) == 1

    ohne = _erste_rechnung_pdf(client, headers)
    client.patch("/auth/mandant", headers=headers, json={"briefpapier_id": briefpapier_id})
    mit = _erste_rechnung_pdf(client, headers)
    assert ohne != mit

    resp = client.delete(f"/auth/briefpapier/{briefpapier_id}", headers=headers)
    assert resp.status_code == 204
    assert client.get("/auth/briefpapier", headers=headers).json() == []
    assert client.get("/auth/mandant", headers=headers).json()["briefpapier_id"] is None


def test_briefpapier_gehoert_nicht_zu_fremdem_mandanten(client: TestClient):
    kevin_headers = _onboarded_mandant(client, email="kevin-brief@example.com")
    lea_headers = _onboarded_mandant(client, email="lea-brief@example.com")

    from io import BytesIO as IO
    from PIL import Image
    buf = IO()
    Image.new("RGB", (210, 297), (250, 250, 245)).save(buf, format="PNG")
    fremdes = client.post(
        "/auth/briefpapier", headers=kevin_headers, data={"name": "Fremd"}, files={"file": ("bg.png", buf.getvalue(), "image/png")},
    ).json()

    resp = client.patch("/auth/mandant", headers=lea_headers, json={"briefpapier_id": fremdes["id"]})
    assert resp.status_code == 400
