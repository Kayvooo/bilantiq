from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant, Mitgliedschaft, User
from app.core import mailer, mailversand
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.core.sperren import sperre_mandant
from app.db import get_db
from app.buchhaltungseinstellungen.models import Buchhaltungseinstellungen
from app.invoices.e_invoice import build_xrechnung_xml, missing_pflichtfelder, runde
from app.invoices.e_invoice_validation import (
    PruefungBlockiert,
    Pruefergebnis,
    pruef_header,
    pruefe_vor_auslieferung,
    validate_xrechnung,
)
from app.invoices.kontakte import kontakt_wird_verwendet, setze_iban
from app.invoices.models import Invoice, InvoicePosition, Kontakt, Positionskategorie
from app.invoices.numbering import allocate_invoice_number
from app.invoices import zahlungen
from app.invoices.pdf import attach_e_invoice_xml, render_invoice_pdf
from app.invoices.schemas import (
    KONTAKT_PFLICHTFELDER,
    BezahltMarkieren,
    InvoiceCreate,
    InvoiceResponse,
    KontaktCreate,
    KontaktResponse,
    KontaktUpdate,
    PositionskategorieResponse,
    VersendenRequest,
)

router = APIRouter(tags=["invoices"])


def _kontakt_response(kontakt: Kontakt) -> KontaktResponse:
    return KontaktResponse(
        id=kontakt.id, name=kontakt.name, strasse=kontakt.strasse, plz=kontakt.plz, ort=kontakt.ort,
        land=kontakt.land, ust_id=kontakt.ust_id, email=kontakt.email,
        ist_geschaeftskunde=kontakt.ist_geschaeftskunde, kundennummer=kontakt.kundennummer,
        typ=kontakt.typ or "kunde", anrede=kontakt.anrede, vorname=kontakt.vorname, nachname=kontakt.nachname,
        telefon=kontakt.telefon, notiz=kontakt.notiz, steuernummer=kontakt.steuernummer, iban=kontakt.iban,
        bic=kontakt.bic, zahlungsziel_tage=kontakt.zahlungsziel_tage, skonto_prozent=kontakt.skonto_prozent,
        skonto_tage=kontakt.skonto_tage, leitweg_id=kontakt.leitweg_id, archiviert=kontakt.archiviert_am is not None,
    )


def _anzeige_status(invoice: Invoice) -> str:
    if invoice.status in ("entwurf", "storniert"):
        return invoice.status
    if invoice.bezahlt_am is not None:
        return "bezahlt"
    if invoice.faelligkeitsdatum < date.today():
        return "ueberfaellig"
    return "final"


def _invoice_response(invoice: Invoice) -> InvoiceResponse:
    hinweis = invoice.kontakt.land == "DE" and invoice.kontakt.ist_geschaeftskunde
    return InvoiceResponse(
        id=invoice.id, kontakt_id=invoice.kontakt_id, kontakt_name=invoice.kontakt.name, nummer=invoice.nummer, status=invoice.status,
        anzeige_status=_anzeige_status(invoice),
        leistungsdatum=invoice.leistungsdatum, faelligkeitsdatum=invoice.faelligkeitsdatum,
        waehrung=invoice.waehrung, netto_gesamt=invoice.netto_gesamt, ust_gesamt=invoice.ust_gesamt,
        brutto_gesamt=invoice.brutto_gesamt, e_invoice_format=invoice.e_invoice_format,
        korrigiert_invoice_id=invoice.korrigiert_invoice_id, bezahlt_am=invoice.bezahlt_am,
        positionen=[
            {
                "id": p.id, "beschreibung": p.beschreibung, "menge": p.menge, "einzelpreis": p.einzelpreis,
                "ust_satz": p.ust_satz, "kategorie": p.kategorie, "artikelnummer": p.artikelnummer,
            }
            for p in invoice.positionen
        ],
        e_rechnung_hinweis=hinweis,
        betreff=invoice.betreff, kopftext=invoice.kopftext, fusstext=invoice.fusstext,
        referenznummer=invoice.referenznummer, kostenstelle=invoice.kostenstelle,
        zahlungsmethode=invoice.zahlungsmethode, skonto_tage=invoice.skonto_tage,
        skonto_prozent=invoice.skonto_prozent, interne_kontaktperson_user_id=invoice.interne_kontaktperson_user_id,
        versendet_am=invoice.versendet_am.isoformat() if invoice.versendet_am else None,
        kontakt_email_vorhanden=bool(invoice.kontakt.email),
    )


def _require_mitglied(db: Session, mandant_id: str, user_id: str) -> None:
    ist_mitglied = (
        db.query(Mitgliedschaft)
        .filter(Mitgliedschaft.mandant_id == mandant_id, Mitgliedschaft.user_id == user_id)
        .first()
        is not None
    )
    if not ist_mitglied:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Interne Kontaktperson gehoert nicht zu diesem Mandanten.")


def _upsert_kategorien(db: Session, mandant_id: str, positionen: list[InvoicePosition]) -> None:
    """Jede neue Positions-Kategorie landet automatisch in der Vorschlagsliste (siehe
    Positionskategorie-Docstring) -- kein separater "Kategorie anlegen"-Schritt noetig."""
    namen = {p.kategorie for p in positionen if p.kategorie}
    if not namen:
        return
    vorhanden = {
        k.name for k in db.query(Positionskategorie).filter(
            Positionskategorie.mandant_id == mandant_id
        ).all()
    }
    for name in namen - vorhanden:
        db.add(Positionskategorie(mandant_id=mandant_id, name=name))


def compute_invoice_totals(positionen: list[InvoicePosition]) -> tuple[Decimal, Decimal, Decimal]:
    """Zeilenbetraege auf Cent runden, die Umsatzsteuer je Steuersatz aus der Summe der Zeilen berechnen und dann
    runden (so verlangen es EN16931/XRechnung, BR-CO-14 und BR-CO-17; Rundung kaufmaennisch)."""
    netto = Decimal("0")
    je_satz: dict[Decimal, Decimal] = {}
    for p in positionen:
        zeilen_netto = runde(p.menge * p.einzelpreis)
        netto += zeilen_netto
        satz = runde(p.ust_satz)
        je_satz[satz] = je_satz.get(satz, Decimal("0")) + zeilen_netto
    ust = sum((runde(basis * satz / Decimal("100")) for satz, basis in je_satz.items()), Decimal("0"))
    return netto, ust, netto + ust


def _invoice_for_update_or_404(db: Session, invoice_id: str, mandant_id: str) -> Invoice:
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.mandant_id == mandant_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden.")
    return invoice


@router.post("/kontakte", response_model=KontaktResponse, status_code=status.HTTP_201_CREATED)
def create_kontakt(payload: KontaktCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> KontaktResponse:
    daten = payload.model_dump()
    iban = daten.pop("iban")
    kontakt = Kontakt(mandant_id=auth["mandant_id"], **daten)
    setze_iban(kontakt, iban)
    db.add(kontakt)
    db.commit()
    return _kontakt_response(kontakt)


@router.get("/kontakte", response_model=list[KontaktResponse])
def list_kontakte(
    typ: Literal["kunde", "lieferant"] | None = None,
    archiviert: bool = False,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> list[KontaktResponse]:
    """Standard: alle aktiven Kontakte. `typ=kunde` liefert Kunden und "beide",
    `typ=lieferant` Lieferanten und "beide". `archiviert=true` liefert nur das Archiv."""
    abfrage = db.query(Kontakt).filter(Kontakt.mandant_id == auth["mandant_id"])
    abfrage = abfrage.filter(Kontakt.archiviert_am.is_not(None) if archiviert else Kontakt.archiviert_am.is_(None))
    if typ is not None:
        abfrage = abfrage.filter(Kontakt.typ.in_((typ, "beide")))
    kontakte = abfrage.all()
    kontakte.sort(key=lambda kontakt: kontakt.name.casefold())
    return [_kontakt_response(k) for k in kontakte]


@router.patch("/kontakte/{kontakt_id}", response_model=KontaktResponse)
def update_kontakt(kontakt_id: str, payload: KontaktUpdate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> KontaktResponse:
    kontakt = get_scoped_or_404(db, Kontakt, kontakt_id, auth["mandant_id"])
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None and field in KONTAKT_PFLICHTFELDER:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Das Feld {field} darf nicht leer sein.")
        if field == "iban":
            setze_iban(kontakt, value)
        else:
            setattr(kontakt, field, value)
    db.commit()
    return _kontakt_response(kontakt)


@router.post("/kontakte/{kontakt_id}/archivieren", response_model=KontaktResponse)
def archiviere_kontakt(kontakt_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> KontaktResponse:
    kontakt = get_scoped_or_404(db, Kontakt, kontakt_id, auth["mandant_id"])
    if kontakt.archiviert_am is None:
        kontakt.archiviert_am = datetime.now(timezone.utc)
        db.commit()
    return _kontakt_response(kontakt)


@router.post("/kontakte/{kontakt_id}/wiederherstellen", response_model=KontaktResponse)
def stelle_kontakt_wieder_her(kontakt_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> KontaktResponse:
    kontakt = get_scoped_or_404(db, Kontakt, kontakt_id, auth["mandant_id"])
    kontakt.archiviert_am = None
    db.commit()
    return _kontakt_response(kontakt)


@router.delete("/kontakte/{kontakt_id}", status_code=status.HTTP_204_NO_CONTENT)
def loesche_kontakt(kontakt_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    kontakt = get_scoped_or_404(db, Kontakt, kontakt_id, auth["mandant_id"])
    if kontakt_wird_verwendet(db, kontakt.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der Kontakt wird in Rechnungen oder anderen Dokumenten verwendet. Bitte archivieren statt löschen.",
        )
    db.delete(kontakt)
    record_audit(db, aktion="kontakt_geloescht", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=kontakt.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> InvoiceResponse:
    mandant_id = auth["mandant_id"]
    mandant = sperre_mandant(db, mandant_id)
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    get_scoped_or_404(db, Kontakt, payload.kontakt_id, mandant_id)  # 404 instead of leaking cross-mandant existence
    if payload.interne_kontaktperson_user_id:
        _require_mitglied(db, mandant_id, payload.interne_kontaktperson_user_id)

    positionen = [InvoicePosition(**p.model_dump()) for p in payload.positionen]
    netto, ust, brutto = compute_invoice_totals(positionen)

    invoice = Invoice(
        mandant_id=mandant_id,
        kontakt_id=payload.kontakt_id,
        leistungsdatum=payload.leistungsdatum,
        faelligkeitsdatum=payload.faelligkeitsdatum,
        waehrung=payload.waehrung,
        netto_gesamt=netto,
        ust_gesamt=ust,
        brutto_gesamt=brutto,
        positionen=positionen,
        betreff=payload.betreff, kopftext=payload.kopftext, fusstext=payload.fusstext,
        referenznummer=payload.referenznummer, kostenstelle=payload.kostenstelle,
        zahlungsmethode=payload.zahlungsmethode, skonto_tage=payload.skonto_tage,
        skonto_prozent=payload.skonto_prozent, interne_kontaktperson_user_id=payload.interne_kontaktperson_user_id,
    )
    db.add(invoice)
    _upsert_kategorien(db, mandant_id, positionen)
    db.commit()
    return _invoice_response(invoice)


@router.get("/positionskategorien", response_model=list[PositionskategorieResponse])
def list_positionskategorien(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[PositionskategorieResponse]:
    kategorien = (
        db.query(Positionskategorie)
        .filter(Positionskategorie.mandant_id == auth["mandant_id"])
        .all()
    )
    kategorien.sort(key=lambda kategorie: kategorie.name.casefold())
    return [PositionskategorieResponse(id=k.id, name=k.name) for k in kategorien]


@router.delete("/positionskategorien/{kategorie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_positionskategorie(kategorie_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    kategorie = get_scoped_or_404(db, Positionskategorie, kategorie_id, auth["mandant_id"])
    db.delete(kategorie)
    db.commit()


@router.post("/invoices/vorschau")
def preview_invoice(payload: InvoiceCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    """Live-Vorschau fuer den Editor waehrend der Eingabe -- rendert ein echtes PDF aus
    dem aktuellen (noch ungespeicherten) Formularstand. Bewusst kein db.add()/commit():
    weder die Rechnung noch neue Positionskategorien duerfen durch eine Vorschau
    entstehen."""
    mandant_id = auth["mandant_id"]
    kontakt = get_scoped_or_404(db, Kontakt, payload.kontakt_id, mandant_id)
    mandant = db.get(Mandant, mandant_id)

    positionen = [InvoicePosition(**p.model_dump()) for p in payload.positionen]
    netto, ust, brutto = compute_invoice_totals(positionen)
    invoice = Invoice(
        mandant_id=mandant_id, kontakt_id=payload.kontakt_id, status="entwurf",
        leistungsdatum=payload.leistungsdatum, faelligkeitsdatum=payload.faelligkeitsdatum,
        waehrung=payload.waehrung, netto_gesamt=netto, ust_gesamt=ust, brutto_gesamt=brutto,
        positionen=positionen, betreff=payload.betreff, kopftext=payload.kopftext, fusstext=payload.fusstext,
    )
    invoice.kontakt = kontakt
    if payload.interne_kontaktperson_user_id:
        _require_mitglied(db, mandant_id, payload.interne_kontaktperson_user_id)
        invoice.interne_kontaktperson = db.get(User, payload.interne_kontaktperson_user_id)
    return Response(content=render_invoice_pdf(mandant, invoice), media_type="application/pdf")


@router.get("/invoices", response_model=list[InvoiceResponse])
def list_invoices(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[InvoiceResponse]:
    invoices = (
        db.query(Invoice).filter(Invoice.mandant_id == auth["mandant_id"]).order_by(Invoice.erstellt_am.desc()).all()
    )
    return [_invoice_response(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> InvoiceResponse:
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    return _invoice_response(invoice)


@router.post("/invoices/{invoice_id}/finalize", response_model=InvoiceResponse)
def finalize_invoice(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> InvoiceResponse:
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    if invoice.status != "entwurf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Entwuerfe koennen finalisiert werden.")

    now = datetime.now(timezone.utc)
    invoice.nummer = allocate_invoice_number(db, mandant_id=auth["mandant_id"], jahr=now.year)
    invoice.status = "final"
    invoice.finalisiert_am = now
    record_audit(db, aktion="rechnung_finalisiert", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=invoice.nummer)
    db.commit()
    return _invoice_response(invoice)


@router.post("/invoices/{invoice_id}/storno", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def storno_invoice(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> InvoiceResponse:
    """Creates a Stornorechnung (credit note) with negated line items. The original
    invoice's content is never touched — only its status flips to "storniert" so the
    UI reflects reality. GoBD unveraenderlichkeit is about the booked content, not the
    lifecycle status of a since-cancelled document."""
    original = _invoice_for_update_or_404(db, invoice_id, auth["mandant_id"])
    if original.status != "final":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen storniert werden.")

    storno_positionen = [
        InvoicePosition(
            reihenfolge=p.reihenfolge, beschreibung=f"Storno: {p.beschreibung}",
            menge=p.menge, einzelpreis=-p.einzelpreis, ust_satz=p.ust_satz,
        )
        for p in original.positionen
    ]
    netto, ust, brutto = compute_invoice_totals(storno_positionen)

    now = datetime.now(timezone.utc)
    storno = Invoice(
        mandant_id=auth["mandant_id"], kontakt_id=original.kontakt_id,
        leistungsdatum=original.leistungsdatum, faelligkeitsdatum=now.date(),
        waehrung=original.waehrung, netto_gesamt=netto, ust_gesamt=ust, brutto_gesamt=brutto,
        positionen=storno_positionen, korrigiert_invoice_id=original.id,
        nummer=allocate_invoice_number(db, mandant_id=auth["mandant_id"], jahr=now.year),
        status="final", finalisiert_am=now,
    )
    original.status = "storniert"
    db.add(storno)
    record_audit(db, aktion="rechnung_storniert", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=original.nummer)
    db.commit()
    return _invoice_response(storno)


@router.post("/invoices/{invoice_id}/bezahlt", response_model=InvoiceResponse)
def mark_invoice_paid(
    invoice_id: str, payload: BezahltMarkieren, auth=Depends(require_full_auth), db: Session = Depends(get_db)
) -> InvoiceResponse:
    """Manual for now — see Invoice.bezahlt_am. Once a bank feed exists this becomes
    automatic reconciliation instead of a button; this endpoint keeps working either way."""
    invoice = _invoice_for_update_or_404(db, invoice_id, auth["mandant_id"])
    try:
        zahlungen.markiere_rechnung_bezahlt(
            db,
            invoice,
            bezahlt_am=payload.bezahlt_am or date.today(),
            user_id=auth["sub"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _invoice_response(invoice)


@router.get("/invoices/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    pdf_bytes = render_invoice_pdf(mandant, invoice)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/invoices/{invoice_id}/versenden", response_model=InvoiceResponse)
def send_invoice_email(
    invoice_id: str,
    payload: VersendenRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    """Verschickt die Rechnung als PDF-Anhang per E-Mail an den hinterlegten Kontakt --
    unabhaengig vom Finalisieren (POST .../finalize, das nur die Nummer vergibt). Kann
    mehrfach aufgerufen werden (z.B. erneuter Versand nach Rueckfrage); jeder Aufruf
    ueberschreibt versendet_am mit dem aktuellen Zeitpunkt."""
    invoice = _invoice_for_update_or_404(db, invoice_id, auth["mandant_id"])
    if invoice.status != "final":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen per E-Mail versendet werden.")
    if not invoice.kontakt.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der Kontakt hat keine E-Mail-Adresse hinterlegt.")

    mailversand.pruefe_versandlimit(db, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    pdf_bytes = render_invoice_pdf(mandant, invoice)
    if payload.text is None:
        text = (
            f"Guten Tag,\n\nanbei erhalten Sie die Rechnung {invoice.nummer} von {mandant.firmenname} "
            "als PDF-Anhang."
        )
        text += "\n\nMit freundlichen Gruessen\n" + mandant.firmenname
    else:
        text = payload.text
    mailer.sende_email(
        empfaenger=invoice.kontakt.email,
        betreff=f"Rechnung {invoice.nummer}",
        text=text,
        anhang_bytes=pdf_bytes,
        anhang_dateiname=f"Rechnung_{invoice.nummer}.pdf",
        absender_name=mandant.firmenname,
        antwort_an=mailversand.antwort_an_adresse(db, auth["sub"]),
    )

    invoice.versendet_am = datetime.now(timezone.utc)
    record_audit(db, aktion="rechnung_versendet", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=invoice.nummer)
    db.commit()
    return _invoice_response(invoice)


@router.get("/invoices/{invoice_id}/e-rechnung-pruefung")
def check_e_rechnung(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> dict:
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    return {"fehlende_felder": missing_pflichtfelder(mandant, invoice)}


def _xrechnung_bauen(db: Session, mandant: Mandant, invoice: Invoice) -> bytes:
    """Baut das XRechnung-XML (ValueError bei fehlenden Pflichtfeldern). Kleinunternehmer-Einstellung und die Nummer der
    stornierten Rechnung kommen aus der Datenbank, nicht aus dem Generator."""
    einstellungen = db.get(Buchhaltungseinstellungen, mandant.id)
    ursprung_nummer = None
    if invoice.korrigiert_invoice_id:
        ursprung = db.get(Invoice, invoice.korrigiert_invoice_id)
        if ursprung is not None and ursprung.mandant_id == mandant.id:
            ursprung_nummer = ursprung.nummer
    return build_xrechnung_xml(
        mandant, invoice, kleinunternehmer=bool(einstellungen and einstellungen.kleinunternehmer),
        korrigierte_rechnungsnummer=ursprung_nummer,
    )


def _xrechnung_pruefen(xml_bytes: bytes, invoice: Invoice) -> Pruefergebnis | None:
    """Wendet XRECHNUNG_PRUEFUNG an: ungueltige XML wird im Modus "blockieren" nicht ausgeliefert (HTTP 422), im Modus
    "warnen" geht sie mit Pruef-Headern raus (X-Xrechnung-Pruefung)."""
    try:
        return pruefe_vor_auslieferung(xml_bytes)
    except PruefungBlockiert as blockiert:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Die XRechnung wird nicht ausgeliefert, weil sie die Pruefung nicht besteht: {blockiert}. "
                f"Alle Meldungen: GET /invoices/{invoice.id}/e-rechnung-validierung"
            ),
        ) from blockiert


@router.get("/invoices/{invoice_id}/e-rechnung-validierung")
def validate_e_rechnung(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> dict:
    """Baut die XRechnung und prueft sie gegen XSD und Schematron (EN16931 und XRechnung-CIUS). Laeuft auch bei
    XRECHNUNG_PRUEFUNG=aus, weil es eine ausdrueckliche Anfrage ist. Liefert das XML nicht aus und aendert nichts.
    Das Ergebnis nennt die Version der Regeln und ist keine Zertifizierung (siehe docs/xrechnung-validierung.md)."""
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    if invoice.status not in ("final", "storniert"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen geprueft werden.")
    mandant = db.get(Mandant, auth["mandant_id"])
    try:
        xml_bytes = _xrechnung_bauen(db, mandant, invoice)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"rechnungsnummer": invoice.nummer, **validate_xrechnung(xml_bytes).als_dict()}


@router.post("/invoices/{invoice_id}/e-rechnung")
def create_e_rechnung(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    if invoice.status != "final":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen als E-Rechnung exportiert werden.")

    mandant = db.get(Mandant, auth["mandant_id"])
    try:
        xml_bytes = _xrechnung_bauen(db, mandant, invoice)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ergebnis = _xrechnung_pruefen(xml_bytes, invoice)

    invoice.e_invoice_format = "xrechnung"
    record_audit(db, aktion="e_rechnung_erzeugt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=invoice.nummer)
    db.commit()
    return Response(content=xml_bytes, media_type="application/xml", headers=pruef_header(ergebnis))


@router.post("/invoices/{invoice_id}/zugferd-pdf")
def create_zugferd_pdf(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    """Best-effort hybrid: real PDF + the XRechnung XML attached. Not a certified
    ZUGFeRD/Factur-X file — see app/invoices/pdf.py for why. Das angehaengte XML wird wie beim XML-Export geprueft
    (nur das XML, nicht das PDF-Format)."""
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    if invoice.status != "final":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen exportiert werden.")

    mandant = db.get(Mandant, auth["mandant_id"])
    try:
        xml_bytes = _xrechnung_bauen(db, mandant, invoice)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    ergebnis = _xrechnung_pruefen(xml_bytes, invoice)

    pdf_bytes = render_invoice_pdf(mandant, invoice)
    hybrid = attach_e_invoice_xml(pdf_bytes, xml_bytes=xml_bytes)

    invoice.e_invoice_format = "zugferd"
    record_audit(db, aktion="zugferd_pdf_erzeugt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=invoice.nummer)
    db.commit()
    return Response(content=hybrid, media_type="application/pdf", headers=pruef_header(ergebnis))
