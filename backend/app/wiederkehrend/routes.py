"""Wiederkehrende Rechnungen: eine Vorlage erzeugt beim Faelligwerden einen echten
Invoice-ENTWURF (nie automatisch final) — die Person prueft und finalisiert wie bei
jeder anderen Rechnung auch, kein automatischer Rechnungsversand ohne Kontrolle.

Kein Scheduler/Cron in diesem Projekt: Erzeugung ist deliberately on-demand ueber
POST /wiederkehrende-rechnungen/erzeugen, ausgeloest von der Nutzerin (z.B. beim
Aufruf der Seite) statt durch einen Hintergrundjob. Siehe Annahmen in der Spec."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.core.audit_log import record as record_audit
from app.core.intervall import naechster_termin
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.invoices.models import Invoice, InvoicePosition, Kontakt
from app.invoices.routes import compute_invoice_totals
from app.wiederkehrend.models import WiederkehrendeRechnung, WiederkehrendeRechnungPosition
from app.wiederkehrend.schemas import ErzeugungsErgebnis, WiederkehrendeRechnungCreate, WiederkehrendeRechnungResponse

router = APIRouter(tags=["wiederkehrend"])

NEUE_FAELLIGKEIT_TAGE = 14


def _pruefe_mandant(db: Session, auth: dict) -> None:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")


def _response(vorlage: WiederkehrendeRechnung) -> WiederkehrendeRechnungResponse:
    return WiederkehrendeRechnungResponse(
        id=vorlage.id, kontakt_id=vorlage.kontakt_id, kontakt_name=vorlage.kontakt.name,
        bezeichnung=vorlage.bezeichnung, intervall=vorlage.intervall,
        naechstes_datum=vorlage.naechstes_datum, enddatum=vorlage.enddatum, aktiv=vorlage.aktiv,
        positionen=[
            {"id": p.id, "beschreibung": p.beschreibung, "menge": p.menge, "einzelpreis": p.einzelpreis, "ust_satz": p.ust_satz}
            for p in vorlage.positionen
        ],
    )


@router.post("/wiederkehrende-rechnungen", response_model=WiederkehrendeRechnungResponse, status_code=status.HTTP_201_CREATED)
def create_wiederkehrende_rechnung(
    payload: WiederkehrendeRechnungCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> WiederkehrendeRechnungResponse:
    _pruefe_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    get_scoped_or_404(db, Kontakt, payload.kontakt_id, mandant_id)
    if payload.enddatum and payload.enddatum < payload.naechstes_datum:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enddatum liegt vor dem naechsten Rechnungsdatum.")

    vorlage = WiederkehrendeRechnung(
        mandant_id=mandant_id, kontakt_id=payload.kontakt_id, bezeichnung=payload.bezeichnung,
        intervall=payload.intervall, naechstes_datum=payload.naechstes_datum, enddatum=payload.enddatum,
        positionen=[
            WiederkehrendeRechnungPosition(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz)
            for p in payload.positionen
        ],
    )
    db.add(vorlage)
    db.commit()
    return _response(vorlage)


@router.get("/wiederkehrende-rechnungen", response_model=list[WiederkehrendeRechnungResponse])
def list_wiederkehrende_rechnungen(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[WiederkehrendeRechnungResponse]:
    _pruefe_mandant(db, auth)
    vorlagen = (
        db.query(WiederkehrendeRechnung)
        .filter(WiederkehrendeRechnung.mandant_id == auth["mandant_id"])
        .order_by(WiederkehrendeRechnung.naechstes_datum)
        .all()
    )
    return [_response(v) for v in vorlagen]


@router.post("/wiederkehrende-rechnungen/{vorlage_id}/deaktivieren", response_model=WiederkehrendeRechnungResponse)
def deaktivieren(vorlage_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> WiederkehrendeRechnungResponse:
    _pruefe_mandant(db, auth)
    vorlage = get_scoped_or_404(db, WiederkehrendeRechnung, vorlage_id, auth["mandant_id"])
    vorlage.aktiv = False
    db.commit()
    return _response(vorlage)


@router.post("/wiederkehrende-rechnungen/erzeugen", response_model=ErzeugungsErgebnis)
def erzeuge_faellige_rechnungen(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> ErzeugungsErgebnis:
    _pruefe_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    heute = date.today()
    faellige = (
        db.query(WiederkehrendeRechnung)
        .filter(
            WiederkehrendeRechnung.mandant_id == mandant_id,
            WiederkehrendeRechnung.aktiv.is_(True),
            WiederkehrendeRechnung.naechstes_datum <= heute,
        )
        .all()
    )

    erzeugte_ids = []
    for vorlage in faellige:
        positionen = [
            InvoicePosition(beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz)
            for p in vorlage.positionen
        ]
        netto, ust, brutto = compute_invoice_totals(positionen)
        invoice = Invoice(
            mandant_id=mandant_id, kontakt_id=vorlage.kontakt_id,
            leistungsdatum=vorlage.naechstes_datum,
            faelligkeitsdatum=vorlage.naechstes_datum + timedelta(days=NEUE_FAELLIGKEIT_TAGE),
            waehrung="EUR", netto_gesamt=netto, ust_gesamt=ust, brutto_gesamt=brutto, positionen=positionen,
        )
        db.add(invoice)
        db.flush()  # id fuer die Response, bevor der naechste Termin berechnet wird
        erzeugte_ids.append(invoice.id)

        vorlage.naechstes_datum = naechster_termin(vorlage.naechstes_datum, vorlage.intervall)
        if vorlage.enddatum and vorlage.naechstes_datum > vorlage.enddatum:
            vorlage.aktiv = False

    if erzeugte_ids:
        record_audit(db, aktion="wiederkehrende_rechnungen_erzeugt", mandant_id=mandant_id, user_id=auth["sub"], kontext=str(len(erzeugte_ids)))
    db.commit()
    return ErzeugungsErgebnis(erzeugte_rechnungen=erzeugte_ids, anzahl=len(erzeugte_ids))
