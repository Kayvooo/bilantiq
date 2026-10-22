from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.core import mailer, mailversand
from app.core.sperren import sperre_mandant
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.invoices.models import Invoice, InvoicePosition, Kontakt
from app.quotes.models import Quote, QuotePosition
from app.quotes.numbering import allocate_quote_number
from app.quotes.pdf import render_quote_pdf
from app.quotes.schemas import QuoteCreate, QuoteResponse, VersendenRequest

router = APIRouter(prefix="/angebote", tags=["quotes"])

# A quote issued to a customer stays valid for the review action itself for at most
# this long after acceptance/rejection can no longer be recorded — see Annahmen.
STANDARD_ZAHLUNGSZIEL_TAGE = 14


def _anzeige_status(quote: Quote) -> str:
    if quote.status == "versendet" and quote.gueltig_bis < date.today():
        return "abgelaufen"
    return quote.status


def _quote_response(quote: Quote) -> QuoteResponse:
    return QuoteResponse(
        id=quote.id, kontakt_id=quote.kontakt_id, nummer=quote.nummer, status=quote.status,
        anzeige_status=_anzeige_status(quote), gueltig_bis=quote.gueltig_bis, waehrung=quote.waehrung,
        netto_gesamt=quote.netto_gesamt, ust_gesamt=quote.ust_gesamt, brutto_gesamt=quote.brutto_gesamt,
        umgewandelt_in_invoice_id=quote.umgewandelt_in_invoice_id,
        email_versendet_am=quote.email_versendet_am.isoformat() if quote.email_versendet_am else None,
        kontakt_email_vorhanden=bool(quote.kontakt.email),
        positionen=[
            {"id": p.id, "beschreibung": p.beschreibung, "menge": p.menge, "einzelpreis": p.einzelpreis, "ust_satz": p.ust_satz}
            for p in quote.positionen
        ],
    )


def _compute_totals(positionen: list[QuotePosition]) -> tuple[Decimal, Decimal, Decimal]:
    netto = Decimal("0")
    ust = Decimal("0")
    for p in positionen:
        zeilen_netto = (p.menge * p.einzelpreis).quantize(Decimal("0.01"))
        netto += zeilen_netto
        ust += (zeilen_netto * p.ust_satz / Decimal("100")).quantize(Decimal("0.01"))
    return netto, ust, netto + ust


@router.post("", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def create_quote(payload: QuoteCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> QuoteResponse:
    mandant_id = auth["mandant_id"]
    get_scoped_or_404(db, Kontakt, payload.kontakt_id, mandant_id)

    positionen = [QuotePosition(**p.model_dump()) for p in payload.positionen]
    netto, ust, brutto = _compute_totals(positionen)

    quote = Quote(
        mandant_id=mandant_id, kontakt_id=payload.kontakt_id, gueltig_bis=payload.gueltig_bis,
        waehrung=payload.waehrung, netto_gesamt=netto, ust_gesamt=ust, brutto_gesamt=brutto, positionen=positionen,
    )
    db.add(quote)
    db.commit()
    return _quote_response(quote)


@router.get("", response_model=list[QuoteResponse])
def list_quotes(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[QuoteResponse]:
    quotes = db.query(Quote).filter(Quote.mandant_id == auth["mandant_id"]).order_by(Quote.erstellt_am.desc()).all()
    return [_quote_response(q) for q in quotes]


@router.get("/{quote_id}", response_model=QuoteResponse)
def get_quote(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> QuoteResponse:
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    return _quote_response(quote)


@router.post("/{quote_id}/versenden", response_model=QuoteResponse)
def send_quote(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> QuoteResponse:
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    if quote.status != "entwurf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Entwuerfe koennen versendet werden.")

    now = datetime.now(timezone.utc)
    quote.nummer = allocate_quote_number(db, mandant_id=auth["mandant_id"], jahr=now.year)
    quote.status = "versendet"
    quote.versendet_am = now
    record_audit(db, aktion="angebot_versendet", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=quote.nummer)
    db.commit()
    return _quote_response(quote)


def _require_versendet_and_not_expired(quote: Quote) -> None:
    if quote.status != "versendet":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur versendete Angebote koennen so behandelt werden.")
    if quote.gueltig_bis < date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Das Angebot ist abgelaufen.")


@router.post("/{quote_id}/annehmen", response_model=QuoteResponse)
def accept_quote(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> QuoteResponse:
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    _require_versendet_and_not_expired(quote)

    quote.status = "angenommen"
    record_audit(db, aktion="angebot_angenommen", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=quote.nummer)
    db.commit()
    return _quote_response(quote)


@router.post("/{quote_id}/ablehnen", response_model=QuoteResponse)
def reject_quote(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> QuoteResponse:
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    _require_versendet_and_not_expired(quote)

    quote.status = "abgelehnt"
    record_audit(db, aktion="angebot_abgelehnt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=quote.nummer)
    db.commit()
    return _quote_response(quote)


@router.post("/{quote_id}/in-rechnung-umwandeln", status_code=status.HTTP_201_CREATED)
def convert_to_invoice(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> dict:
    """Copies the quote's positions into a new draft invoice — the quote itself is
    never modified beyond recording the link, matching how Storno never rewrites an
    original invoice (app/invoices/routes.py)."""
    mandant = sperre_mandant(db, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    if quote.status != "angenommen":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur angenommene Angebote koennen umgewandelt werden.")
    if quote.umgewandelt_in_invoice_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dieses Angebot wurde bereits umgewandelt.")

    today = date.today()
    invoice_positionen = [
        InvoicePosition(reihenfolge=p.reihenfolge, beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz)
        for p in quote.positionen
    ]
    invoice = Invoice(
        mandant_id=auth["mandant_id"], kontakt_id=quote.kontakt_id, leistungsdatum=today,
        faelligkeitsdatum=today + timedelta(days=STANDARD_ZAHLUNGSZIEL_TAGE), waehrung=quote.waehrung,
        netto_gesamt=quote.netto_gesamt, ust_gesamt=quote.ust_gesamt, brutto_gesamt=quote.brutto_gesamt,
        positionen=invoice_positionen,
    )
    db.add(invoice)
    db.flush()

    quote.umgewandelt_in_invoice_id = invoice.id
    record_audit(db, aktion="angebot_umgewandelt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=f"{quote.nummer}->{invoice.id}")
    db.commit()

    return {"invoice_id": invoice.id, "status": invoice.status}


@router.get("/{quote_id}/pdf")
def get_quote_pdf(quote_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    return Response(content=render_quote_pdf(mandant, quote), media_type="application/pdf")


@router.post("/{quote_id}/per-email-senden", response_model=QuoteResponse)
def send_quote_email(
    quote_id: str, payload: VersendenRequest, auth=Depends(require_full_auth), db: Session = Depends(get_db)
) -> QuoteResponse:
    """Verschickt das Angebot als PDF-Anhang per E-Mail an den hinterlegten Kontakt.

    Bewusst ein eigener Routenname statt .../versenden: dieser Pfad ist bereits
    belegt (send_quote oben) und finalisiert dort den Entwurf (vergibt die
    Angebotsnummer, setzt status="versendet") -- lange bevor es ueberhaupt
    E-Mail-Versand gab. Ein Angebot braucht daher zuerst eine Nummer (jeder
    Nicht-Entwurf-Status), bevor es hier per E-Mail verschickt werden kann; dieser
    Aufruf allein aendert status/versendet_am (oben) nicht, sondern nur
    email_versendet_am (siehe app/quotes/models.py)."""
    quote = get_scoped_or_404(db, Quote, quote_id, auth["mandant_id"])
    if quote.status == "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entwuerfe koennen nicht per E-Mail versendet werden -- zuerst 'Versenden' waehlen, um eine Angebotsnummer zu vergeben.",
        )
    if not quote.kontakt.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der Kontakt hat keine E-Mail-Adresse hinterlegt.")

    mailversand.pruefe_versandlimit(db, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    pdf_bytes = render_quote_pdf(mandant, quote)
    text = payload.text or (
        f"Guten Tag,\n\nanbei erhalten Sie unser Angebot {quote.nummer} von {mandant.firmenname} "
        "als PDF-Anhang.\n\nMit freundlichen Gruessen\n" + mandant.firmenname
    )
    mailer.sende_email(
        empfaenger=quote.kontakt.email,
        betreff=f"Angebot {quote.nummer}",
        text=text,
        anhang_bytes=pdf_bytes,
        anhang_dateiname=f"Angebot_{quote.nummer}.pdf",
        absender_name=mandant.firmenname,
        antwort_an=mailversand.antwort_an_adresse(db, auth["sub"]),
    )

    quote.email_versendet_am = datetime.now(timezone.utc)
    record_audit(db, aktion="angebot_versendet_email", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=quote.nummer)
    db.commit()
    return _quote_response(quote)
