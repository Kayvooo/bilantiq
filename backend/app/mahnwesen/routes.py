from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.core import mailer, mailversand
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.invoices.models import Invoice
from app.mahnwesen.models import Mahnung
from app.mahnwesen.pdf import render_mahnung_pdf
from app.mahnwesen.schemas import STUFE_BEZEICHNUNG, MahnungResponse, MahnungUebersichtResponse, VersendenRequest

router = APIRouter(tags=["mahnwesen"])

# Assumption, not legal advice: 0 EUR for the first friendly reminder, then a fee per
# further stage. Real Mahngebuehren must reflect actual incurred cost to be legally
# enforceable — the operator must confirm these (with tax advice) before charging a real customer.
MAHNGEBUEHR_JE_STUFE = {1: Decimal("0.00"), 2: Decimal("5.00"), 3: Decimal("10.00")}
NEUE_ZAHLUNGSFRIST_TAGE = 10
MAX_STUFE = 3


def _mahnung_response(mahnung: Mahnung, invoice: Invoice) -> MahnungResponse:
    return MahnungResponse(
        id=mahnung.id, invoice_id=mahnung.invoice_id, stufe=mahnung.stufe,
        stufe_bezeichnung=STUFE_BEZEICHNUNG[mahnung.stufe], mahngebuehr=mahnung.mahngebuehr,
        neue_faelligkeit=mahnung.neue_faelligkeit, erstellt_am=mahnung.erstellt_am.isoformat(),
        versendet_am=mahnung.versendet_am.isoformat() if mahnung.versendet_am else None,
        kontakt_email_vorhanden=bool(invoice.kontakt.email),
    )

def _lade_mandant(db: Session, auth: dict) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


@router.post("/invoices/{invoice_id}/mahnung", response_model=MahnungResponse, status_code=status.HTTP_201_CREATED)
def create_mahnung(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> MahnungResponse:
    _lade_mandant(db, auth)
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])
    if invoice.status != "final":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur finale Rechnungen koennen gemahnt werden.")
    if invoice.bezahlt_am is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diese Rechnung ist bereits bezahlt.")
    if invoice.faelligkeitsdatum >= date.today():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diese Rechnung ist noch nicht ueberfaellig.")

    bisherige = db.query(Mahnung).filter(Mahnung.invoice_id == invoice_id).count()
    if bisherige >= MAX_STUFE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximale Mahnstufe ({STUFE_BEZEICHNUNG[MAX_STUFE]}) bereits erreicht — weiteres Vorgehen ist kein Mahnwesen mehr.",
        )

    stufe = bisherige + 1
    mahnung = Mahnung(
        mandant_id=auth["mandant_id"], invoice_id=invoice_id, stufe=stufe,
        mahngebuehr=MAHNGEBUEHR_JE_STUFE[stufe], neue_faelligkeit=date.today() + timedelta(days=NEUE_ZAHLUNGSFRIST_TAGE),
    )
    db.add(mahnung)
    record_audit(db, aktion="mahnung_erstellt", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=f"{invoice.nummer} stufe {stufe}")
    db.commit()
    return _mahnung_response(mahnung, invoice)


@router.get("/invoices/{invoice_id}/mahnungen", response_model=list[MahnungResponse])
def list_mahnungen(invoice_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[MahnungResponse]:
    _lade_mandant(db, auth)
    invoice = get_scoped_or_404(db, Invoice, invoice_id, auth["mandant_id"])  # 404 if the invoice itself isn't this mandant's
    mahnungen = db.query(Mahnung).filter(Mahnung.invoice_id == invoice_id).order_by(Mahnung.stufe).all()
    return [_mahnung_response(m, invoice) for m in mahnungen]


@router.get("/mahnungen", response_model=list[MahnungUebersichtResponse])
def list_alle_mahnungen(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[MahnungUebersichtResponse]:
    """Uebergreifende Sicht ueber alle Mahnstufen des Mandanten, quer durch alle
    Rechnungen — im Unterschied zu list_mahnungen, das an eine einzelne Rechnung
    gebunden ist. Nutzt Invoice.kontakt (Relationship) fuer den Anzeigenamen."""
    _lade_mandant(db, auth)
    mahnungen = (
        db.query(Mahnung)
        .filter(Mahnung.mandant_id == auth["mandant_id"])
        .order_by(Mahnung.erstellt_am.desc())
        .all()
    )
    result = []
    for mahnung in mahnungen:
        invoice = db.get(Invoice, mahnung.invoice_id)
        result.append(MahnungUebersichtResponse(
            id=mahnung.id, invoice_id=mahnung.invoice_id, stufe=mahnung.stufe,
            stufe_bezeichnung=STUFE_BEZEICHNUNG[mahnung.stufe], mahngebuehr=mahnung.mahngebuehr,
            neue_faelligkeit=mahnung.neue_faelligkeit, erstellt_am=mahnung.erstellt_am.isoformat(),
            versendet_am=mahnung.versendet_am.isoformat() if mahnung.versendet_am else None,
            kontakt_email_vorhanden=bool(invoice.kontakt.email),
            rechnung_nummer=invoice.nummer or "", kontakt_name=invoice.kontakt.name, rechnung_brutto=invoice.brutto_gesamt,
        ))
    return result


@router.get("/mahnungen/{mahnung_id}/pdf")
def get_mahnung_pdf(mahnung_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    mandant = _lade_mandant(db, auth)
    mahnung = get_scoped_or_404(db, Mahnung, mahnung_id, auth["mandant_id"])
    invoice = db.get(Invoice, mahnung.invoice_id)
    return Response(content=render_mahnung_pdf(mandant, invoice, mahnung), media_type="application/pdf")


@router.post("/mahnungen/{mahnung_id}/versenden", response_model=MahnungResponse)
def send_mahnung_email(
    mahnung_id: str, payload: VersendenRequest, auth=Depends(require_full_auth), db: Session = Depends(get_db)
) -> MahnungResponse:
    """Verschickt die Mahnung als PDF-Anhang per E-Mail an den Kontakt der zugrunde
    liegenden Rechnung. Kein Entwurfs-/Finalisierungs-Check noetig -- eine Mahnung ist
    laut Docstring in app/mahnwesen/models.py immer sofort final, sobald sie existiert."""
    mandant = _lade_mandant(db, auth)
    mahnung = get_scoped_or_404(db, Mahnung, mahnung_id, auth["mandant_id"])
    invoice = get_scoped_or_404(db, Invoice, mahnung.invoice_id, auth["mandant_id"])
    if not invoice.kontakt.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der Kontakt hat keine E-Mail-Adresse hinterlegt.")

    mailversand.pruefe_versandlimit(db, auth["mandant_id"])
    pdf_bytes = render_mahnung_pdf(mandant, invoice, mahnung)
    stufe_bezeichnung = STUFE_BEZEICHNUNG[mahnung.stufe]
    text = payload.text or (
        f"Guten Tag,\n\nanbei erhalten Sie {stufe_bezeichnung} zur Rechnung {invoice.nummer} von {mandant.firmenname} "
        f"als PDF-Anhang. Bitte begleichen Sie den offenen Betrag bis zum {mahnung.neue_faelligkeit.strftime('%d.%m.%Y')}."
        "\n\nMit freundlichen Gruessen\n" + mandant.firmenname
    )
    mailer.sende_email(
        empfaenger=invoice.kontakt.email,
        betreff=f"{stufe_bezeichnung} zu Rechnung {invoice.nummer}",
        text=text,
        anhang_bytes=pdf_bytes,
        anhang_dateiname=f"Mahnung_{invoice.nummer}_Stufe{mahnung.stufe}.pdf",
        absender_name=mandant.firmenname,
        antwort_an=mailversand.antwort_an_adresse(db, auth["sub"]),
    )

    mahnung.versendet_am = datetime.now(timezone.utc)
    record_audit(
        db, aktion="mahnung_versendet", mandant_id=auth["mandant_id"], user_id=auth["sub"],
        kontext=f"{invoice.nummer} stufe {mahnung.stufe}",
    )
    db.commit()
    return _mahnung_response(mahnung, invoice)
