"""Gemeinsamer Erfassungsweg fuer Belege.

Der HTTP-Upload ruft ihn heute auf; Kamera-Upload und E-Mail-Eingang nutzen spaeter
denselben Weg, damit Limit-Pruefung, Dateityp-Erkennung, Duplikat-Schutz, Extraktion und
Audit ueberall gleich greifen."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.auth.models import Mandant
from app.core.sperren import sperre_mandant
from app.config import settings
from app.core.audit_log import record as record_audit
from app.receipts import storage
from app.receipts.ai_extraction import ExtractionUnavailable, ReceiptExtraction, ReceiptExtractor
from app.receipts.e_rechnung import (
    EInvoiceDaten,
    EInvoiceFehler,
    baue_extraktion,
    dedupe_key,
    extrahiere_xml_aus_pdf,
    lese_e_rechnung,
    zusatzdaten_json,
)
from app.receipts.models import Receipt

_AUDIT_AKTION = {"upload": "beleg_hochgeladen"}


class ErfassungsFehler(Exception):
    """Die Datei kann nicht erfasst werden. Trägt Status und Meldung fuer die Antwort."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class Erfassung:
    receipt: Receipt
    mandant: Mandant
    duplikat: bool = False


def ist_unklar(confidence: float | None) -> bool:
    return confidence is None or confidence < settings.receipt_confidence_threshold


def erkenne_dateityp(daten: bytes) -> str | None:
    """Bestimmt den Dateityp aus dem Inhalt. Der vom Client gemeldete Typ ist nur
    eine Behauptung und wird nicht verwendet."""
    if b"%PDF-" in daten[:1024]:
        return "application/pdf"
    if daten.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if daten.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if daten[:4] == b"RIFF" and daten[8:12] == b"WEBP":
        return "image/webp"
    anfang = daten[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if anfang.startswith(b"<?xml") or (anfang.startswith(b"<") and anfang[1:2].isalpha()):
        return "application/xml"
    return None


def parse_decimal(wert: str | None) -> Decimal | None:
    if wert is None:
        return None
    try:
        return Decimal(wert)
    except InvalidOperation:
        return None


def parse_datum(wert: str | None) -> date | None:
    if wert is None:
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError:
        return None


def uebernehme_extraktion(receipt: Receipt, extraction: ReceiptExtraction) -> None:
    receipt.betrag = parse_decimal(extraction.betrag.wert)
    receipt.betrag_confidence = extraction.betrag.confidence
    receipt.datum = parse_datum(extraction.datum.wert)
    receipt.datum_confidence = extraction.datum.confidence
    receipt.anbieter = extraction.anbieter.wert
    receipt.anbieter_confidence = extraction.anbieter.confidence
    receipt.ust_satz = parse_decimal(extraction.ust_satz.wert)
    receipt.ust_satz_confidence = extraction.ust_satz.confidence
    receipt.kategorie_vorschlag = extraction.kategorie_vorschlag.wert
    receipt.kategorie_vorschlag_confidence = extraction.kategorie_vorschlag.confidence
    receipt.begruendung = extraction.begruendung

    # Betrag is the one field a receipt cannot do without: everything else can be
    # filled in by hand at confirmation time, but no betrag means "Pruefung noetig".
    receipt.status = "unklar" if receipt.betrag is None or ist_unklar(receipt.betrag_confidence) else "geprueft"


def _lese_e_rechnung_falls_vorhanden(daten: bytes, mime_type: str) -> tuple[EInvoiceDaten | None, str]:
    """XML-Datei: muss eine lesbare E-Rechnung sein. PDF: ein eingebetteter Rechnungs-
    datensatz (ZUGFeRD/Factur-X) wird bevorzugt, sonst bleibt es bei der Texterkennung."""
    if mime_type == "application/xml":
        try:
            return lese_e_rechnung(daten), "xrechnung"
        except EInvoiceFehler as exc:
            raise ErfassungsFehler(400, str(exc)) from exc
    if mime_type == "application/pdf":
        eingebettet = extrahiere_xml_aus_pdf(daten)
        if eingebettet is not None:
            try:
                return lese_e_rechnung(eingebettet), "zugferd"
            except EInvoiceFehler:
                return None, "ocr"
    return None, "ocr"


def erfasse_beleg(
    db: Session,
    *,
    mandant_id: str,
    daten: bytes,
    deklarierter_typ: str | None,
    user_id: str | None,
    extractor: ReceiptExtractor,
    quelle: str = "upload",
    force: bool = False,
) -> Erfassung:
    mandant = sperre_mandant(db, mandant_id)
    if mandant is None:
        raise ErfassungsFehler(404, "Mandant nicht gefunden.")

    mime_type = erkenne_dateityp(daten)
    if mime_type is None or mime_type not in storage.ALLOWED_MIME_TYPES:
        raise ErfassungsFehler(
            400,
            f"Dateityp {deklarierter_typ or 'unbekannt'} wird nicht unterstuetzt "
            "(erlaubt: JPEG, PNG, WebP, PDF, XML-E-Rechnung).",
        )

    e_daten, beleg_typ = _lese_e_rechnung_falls_vorhanden(daten, mime_type)
    schluessel = dedupe_key(mandant_id, e_daten) if e_daten is not None else None

    file_hash = storage.hash_bytes(daten)
    if not force:
        existing = db.query(Receipt).filter(Receipt.mandant_id == mandant_id, Receipt.datei_hash == file_hash).first()
        if existing is None and schluessel is not None:
            # Dieselbe Rechnung kann als XML und als PDF-Kopie eintreffen.
            existing = db.query(Receipt).filter(Receipt.mandant_id == mandant_id, Receipt.dedupe_key == schluessel).first()
        if existing is not None:
            return Erfassung(receipt=existing, mandant=mandant, duplikat=True)

    relative_path = storage.save(mandant_id, file_hash, mime_type, daten)
    receipt = Receipt(
        mandant_id=mandant_id, datei_referenz=relative_path, datei_hash=file_hash, status="neu",
        beleg_typ=beleg_typ, dedupe_key=schluessel,
    )
    db.add(receipt)
    db.flush()

    if e_daten is not None:
        uebernehme_extraktion(receipt, baue_extraktion(e_daten))
        receipt.rechnungsnummer = e_daten.rechnungsnummer
        receipt.faelligkeit = e_daten.faelligkeit
        receipt.iban = e_daten.iban
        receipt.e_rechnung_daten = zusatzdaten_json(e_daten)
    else:
        try:
            uebernehme_extraktion(receipt, extractor.extract(daten, mime_type))
        except ExtractionUnavailable:
            # Original is already saved and referenced: nothing lost, just needs a human.
            receipt.status = "unklar"

    record_audit(
        db, aktion=_AUDIT_AKTION.get(quelle, f"beleg_{quelle}"), mandant_id=mandant_id, user_id=user_id, kontext=receipt.id,
    )
    db.commit()
    return Erfassung(receipt=receipt, mandant=mandant)
