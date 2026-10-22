import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.xml_safe import UngueltigesXml, parse_xml_sicher
from app.db import SessionLocal
from app.receipts.ai_extraction import get_extractor
from app.receipts.models import Receipt
from app.receipts.service import erkenne_dateityp
from tests.test_invoices import _onboarded_mandant
from tests.test_receipts import FAKE_IMAGE, _FakeExtractor
from app.main import app

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 "


@pytest.fixture(autouse=True)
def _fake_extractor():
    from app.receipts.ai_extraction import ExtractedField, ReceiptExtraction

    leer = ExtractedField(wert=None, confidence=0.0)
    app.dependency_overrides[get_extractor] = lambda: _FakeExtractor(
        ReceiptExtraction(betrag=leer, datum=leer, anbieter=leer, ust_satz=leer, kategorie_vorschlag=leer, begruendung="")
    )
    yield
    app.dependency_overrides.pop(get_extractor, None)


@pytest.mark.parametrize(
    "daten,erwartet",
    [
        (PDF_BYTES, "application/pdf"),
        (b"\n\n" + PDF_BYTES, "application/pdf"),
        (JPEG_BYTES, "image/jpeg"),
        (FAKE_IMAGE, "image/png"),
        (WEBP_BYTES, "image/webp"),
        (b'<?xml version="1.0"?><a/>', "application/xml"),
        (b"\xef\xbb\xbf  <Invoice/>", "application/xml"),
        (b"hallo", None),
        (b"", None),
        (b"MZ\x90\x00 ausfuehrbare datei", None),
    ],
)
def test_dateityp_wird_aus_dem_inhalt_erkannt(daten, erwartet):
    assert erkenne_dateityp(daten) == erwartet


def test_falscher_client_header_wird_ignoriert_und_inhalt_entscheidet(client: TestClient):
    headers = _onboarded_mandant(client)

    resp = client.post("/belege", headers=headers, files={"file": ("foto.png", PDF_BYTES, "image/png")})

    assert resp.status_code == 201
    with SessionLocal() as db:
        assert db.query(Receipt).one().datei_referenz.endswith(".pdf")


def test_inhalt_ohne_bekannte_signatur_wird_trotz_gueltigem_header_abgelehnt(client: TestClient):
    headers = _onboarded_mandant(client)

    resp = client.post("/belege", headers=headers, files={"file": ("beleg.pdf", b"das ist kein pdf", "application/pdf")})

    assert resp.status_code == 400
    assert "nicht unterstuetzt" in resp.json()["detail"]
    with SessionLocal() as db:
        assert db.query(Receipt).count() == 0


def test_zu_grosse_datei_wird_mit_413_abgelehnt(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "receipt_max_bytes", 1024)
    headers = _onboarded_mandant(client)

    resp = client.post("/belege", headers=headers, files={"file": ("gross.png", FAKE_IMAGE + b"x" * 2048, "image/png")})

    assert resp.status_code == 413
    assert "zu groß" in resp.json()["detail"]
    with SessionLocal() as db:
        assert db.query(Receipt).count() == 0


def test_datei_genau_am_limit_wird_akzeptiert(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "receipt_max_bytes", len(FAKE_IMAGE))
    headers = _onboarded_mandant(client)

    resp = client.post("/belege", headers=headers, files={"file": ("klein.png", FAKE_IMAGE, "image/png")})

    assert resp.status_code == 201


def test_xml_sicher_liest_normales_xml():
    wurzel = parse_xml_sicher(b'<?xml version="1.0"?><Invoice xmlns="urn:x"><ID>R-1</ID></Invoice>')

    assert wurzel.tag == "{urn:x}Invoice"


def test_xml_sicher_lehnt_doctype_und_entitaeten_ab():
    xxe = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>'
    bomb = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><l>&b;</l>'

    for bosartig in (xxe, bomb):
        with pytest.raises(UngueltigesXml):
            parse_xml_sicher(bosartig)


def test_xml_sicher_gibt_keine_dateiinhalte_preis():
    xxe = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/hostname">]><a>&x;</a>'

    with pytest.raises(UngueltigesXml) as fehler:
        parse_xml_sicher(xxe)

    assert "hostname" not in str(fehler.value)


def test_xml_sicher_lehnt_zu_grosse_und_kaputte_dateien_ab():
    with pytest.raises(UngueltigesXml, match="zu groß"):
        parse_xml_sicher(b"<a>" + b"x" * 2048 + b"</a>", max_bytes=1024)
    with pytest.raises(UngueltigesXml, match="kein gültiges XML"):
        parse_xml_sicher(b"<a><b></a>")


# ---------------------------------------------------------------------------
# Logo und Briefpapier: Inhalt statt Content-Type, Pixelgrenze, begrenztes Lesen


def _bild(format_: str = "PNG", groesse=(16, 16), modus="RGB") -> bytes:
    import io

    from PIL import Image

    puffer = io.BytesIO()
    Image.new(modus, groesse, 1 if modus == "1" else (30, 90, 120)).save(puffer, format=format_)
    return puffer.getvalue()


def _hochladen(client: TestClient, headers: dict, ziel: str, daten: bytes, content_type: str, name: str = "bild.png"):
    if ziel == "logo":
        return client.post("/auth/mandant/logo", headers=headers, files={"file": (name, daten, content_type)})
    return client.post("/auth/briefpapier", headers=headers, data={"name": "Papier"}, files={"file": (name, daten, content_type)})


@pytest.mark.parametrize("ziel", ["logo", "briefpapier"])
@pytest.mark.parametrize(
    "daten,content_type",
    [
        (b"kein bild, nur text", "image/png"),                       # richtiger Header-Typ, Inhalt kein Bild
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "image/png"),          # PNG-Signatur, aber nicht dekodierbar
        (b"\xff\xd8\xff\xe0" + b"\x00" * 50, "image/jpeg"),          # JPEG-Signatur, nicht dekodierbar
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/png"),  # SVG als PNG getarnt
        (b"%PDF-1.4\n", "image/png"),
        (b"MZ\x90\x00 ausfuehrbar", "image/webp"),
    ],
)
def test_logo_und_briefpapier_lehnen_getarnte_oder_kaputte_dateien_ab(client: TestClient, ziel, daten, content_type):
    headers = _onboarded_mandant(client)

    antwort = _hochladen(client, headers, ziel, daten, content_type)

    assert antwort.status_code == 400, antwort.text


@pytest.mark.parametrize("ziel", ["logo", "briefpapier"])
def test_logo_und_briefpapier_lehnen_dekompressionsbomben_ab(client: TestClient, ziel):
    from app.core.bild_pruefung import MAX_PIXEL

    headers = _onboarded_mandant(client)
    kantenlaenge = int(MAX_PIXEL**0.5) + 100
    bombe = _bild("PNG", (kantenlaenge, kantenlaenge), modus="1")  # wenige KB groß, aber > MAX_PIXEL Pixel
    assert len(bombe) < 1024 * 1024

    antwort = _hochladen(client, headers, ziel, bombe, "image/png")

    assert antwort.status_code == 400
    assert "zu gross" in antwort.json()["detail"]


@pytest.mark.parametrize("ziel", ["logo", "briefpapier"])
def test_der_dateiinhalt_entscheidet_ueber_den_typ_nicht_der_client(client: TestClient, ziel):
    headers = _onboarded_mandant(client)

    antwort = _hochladen(client, headers, ziel, _bild("JPEG"), "image/png", name="falsch.png")  # JPEG als PNG gemeldet

    assert antwort.status_code in (200, 201), antwort.text
    if ziel == "logo":
        gespeichert = client.get("/auth/mandant/logo", headers=headers)
        assert gespeichert.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("ziel,attr", [("logo", "branding_storage"), ("briefpapier", "letterhead_storage")])
def test_zu_grosse_logos_und_briefpapiere_werden_abgelehnt(client: TestClient, monkeypatch, ziel, attr):
    """Das Limit gilt beim Lesen (``read(MAX_BYTES + 1)``), nicht erst nach dem vollstaendigen Einlesen."""
    from app.core import branding_storage, letterhead_storage

    modul = {"branding_storage": branding_storage, "letterhead_storage": letterhead_storage}[attr]
    monkeypatch.setattr(modul, "MAX_BYTES", 1024)
    headers = _onboarded_mandant(client)
    gross = _bild("PNG", (200, 200)) + b"\x00" * 4096  # > 1 KB

    antwort = _hochladen(client, headers, ziel, gross, "image/png")

    assert antwort.status_code == 400 and "zu gross" in antwort.json()["detail"]


def test_gueltiges_logo_und_briefpapier_funktionieren_weiterhin(client: TestClient):
    headers = _onboarded_mandant(client)
    for format_, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
        assert _hochladen(client, headers, "logo", _bild(format_), mime).status_code == 200
        assert _hochladen(client, headers, "briefpapier", _bild(format_), mime).status_code == 201


# ---------------------------------------------------------------------------
# OCR: Seiten- und Pixelgrenzen beim Rendern von PDFs


def test_pdf_wird_nur_begrenzt_gerendert(monkeypatch):
    from app.receipts import ai_extraction

    aufrufe: dict = {}

    def falsches_rendern(daten, **kwargs):
        aufrufe.update(kwargs)
        return []

    monkeypatch.setattr(ai_extraction, "convert_from_bytes", falsches_rendern)
    monkeypatch.setattr(ai_extraction, "_dpi_fuer_pdf", lambda daten: 300)

    with pytest.raises(ai_extraction.ExtractionUnavailable):
        ai_extraction.LocalOcrReceiptExtractor().extract(b"%PDF-1.4", "application/pdf")

    assert aufrufe["last_page"] == ai_extraction.MAX_OCR_SEITEN
    assert aufrufe["timeout"] > 0


@pytest.mark.skipif(__import__("shutil").which("pdfinfo") is None, reason="braucht poppler (pdfinfo)")
def test_dpi_wird_bei_riesigen_seiten_abgesenkt():
    import io

    from reportlab.pdfgen import canvas

    from app.receipts import ai_extraction

    def pdf(breite, hoehe) -> bytes:
        puffer = io.BytesIO()
        seite = canvas.Canvas(puffer, pagesize=(breite, hoehe))
        seite.showPage()
        seite.save()
        return puffer.getvalue()

    assert ai_extraction._dpi_fuer_pdf(pdf(595, 842)) == 300  # A4 unveraendert
    plakat = ai_extraction._dpi_fuer_pdf(pdf(3370, 2384))  # A0 quer
    assert 20 <= plakat < 150
    assert (3370 / 72 * plakat) * (2384 / 72 * plakat) <= ai_extraction.MAX_PIXEL_PRO_SEITE * 1.05
