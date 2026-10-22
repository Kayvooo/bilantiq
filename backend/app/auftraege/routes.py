from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auftraege.models import (
    Auftragsbestaetigung,
    AuftragsbestaetigungPosition,
    Lieferschein,
    LieferscheinPosition,
)
from app.auftraege.numbering import allocate_auftragsbestaetigung_number, allocate_lieferschein_number
from app.auftraege.pdf import render_auftragsbestaetigung_pdf, render_lieferschein_pdf_for
from app.auftraege.schemas import (
    AuftragsbestaetigungCreate,
    AuftragsbestaetigungResponse,
    LieferscheinCreate,
    LieferscheinResponse,
)
from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.quotes.models import Quote

router = APIRouter(tags=["auftraege"])


def _lade_mandant(db: Session, auth: dict) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


def _ab_response(ab: Auftragsbestaetigung) -> AuftragsbestaetigungResponse:
    return AuftragsbestaetigungResponse(
        id=ab.id, quote_id=ab.quote_id, kontakt_id=ab.kontakt_id, nummer=ab.nummer, waehrung=ab.waehrung,
        netto_gesamt=ab.netto_gesamt, ust_gesamt=ab.ust_gesamt, brutto_gesamt=ab.brutto_gesamt,
        erstellt_am=ab.erstellt_am,
        positionen=[
            {"id": p.id, "beschreibung": p.beschreibung, "menge": p.menge, "einzelpreis": p.einzelpreis, "ust_satz": p.ust_satz}
            for p in ab.positionen
        ],
    )


def _lieferschein_response(ls: Lieferschein) -> LieferscheinResponse:
    return LieferscheinResponse(
        id=ls.id, auftragsbestaetigung_id=ls.auftragsbestaetigung_id, kontakt_id=ls.kontakt_id, nummer=ls.nummer,
        lieferdatum=ls.lieferdatum, erstellt_am=ls.erstellt_am,
        positionen=[{"id": p.id, "beschreibung": p.beschreibung, "menge": p.menge} for p in ls.positionen],
    )


@router.post("/auftragsbestaetigungen", response_model=AuftragsbestaetigungResponse, status_code=status.HTTP_201_CREATED)
def create_auftragsbestaetigung(
    payload: AuftragsbestaetigungCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)
) -> AuftragsbestaetigungResponse:
    """Erzeugt eine Auftragsbestaetigung aus einem angenommenen Angebot — kopiert dessen
    Positionen und Summen fest, das Angebot selbst bleibt unveraendert (gleiches Muster
    wie app/quotes/routes.py::convert_to_invoice)."""
    _lade_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    quote = get_scoped_or_404(db, Quote, payload.quote_id, mandant_id)
    if quote.status != "angenommen":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur angenommene Angebote koennen bestaetigt werden.")

    bereits_vorhanden = (
        db.query(Auftragsbestaetigung)
        .filter(Auftragsbestaetigung.mandant_id == mandant_id, Auftragsbestaetigung.quote_id == quote.id)
        .first()
    )
    if bereits_vorhanden is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fuer dieses Angebot besteht bereits eine Auftragsbestaetigung.")

    now = datetime.now(timezone.utc)
    positionen = [
        AuftragsbestaetigungPosition(
            reihenfolge=p.reihenfolge, beschreibung=p.beschreibung, menge=p.menge, einzelpreis=p.einzelpreis, ust_satz=p.ust_satz
        )
        for p in quote.positionen
    ]
    ab = Auftragsbestaetigung(
        mandant_id=mandant_id, quote_id=quote.id, kontakt_id=quote.kontakt_id,
        nummer=allocate_auftragsbestaetigung_number(db, mandant_id=mandant_id, jahr=now.year),
        waehrung=quote.waehrung, netto_gesamt=quote.netto_gesamt, ust_gesamt=quote.ust_gesamt,
        brutto_gesamt=quote.brutto_gesamt, positionen=positionen,
    )
    db.add(ab)
    db.flush()
    record_audit(db, aktion="auftragsbestaetigung_erstellt", mandant_id=mandant_id, user_id=auth["sub"], kontext=ab.nummer)
    db.commit()
    return _ab_response(ab)


@router.get("/auftragsbestaetigungen", response_model=list[AuftragsbestaetigungResponse])
def list_auftragsbestaetigungen(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[AuftragsbestaetigungResponse]:
    _lade_mandant(db, auth)
    items = (
        db.query(Auftragsbestaetigung)
        .filter(Auftragsbestaetigung.mandant_id == auth["mandant_id"])
        .order_by(Auftragsbestaetigung.erstellt_am.desc())
        .all()
    )
    return [_ab_response(a) for a in items]


@router.get("/auftragsbestaetigungen/{ab_id}", response_model=AuftragsbestaetigungResponse)
def get_auftragsbestaetigung(ab_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> AuftragsbestaetigungResponse:
    _lade_mandant(db, auth)
    ab = get_scoped_or_404(db, Auftragsbestaetigung, ab_id, auth["mandant_id"])
    return _ab_response(ab)


@router.get("/auftragsbestaetigungen/{ab_id}/pdf")
def get_auftragsbestaetigung_pdf(ab_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    _lade_mandant(db, auth)
    ab = get_scoped_or_404(db, Auftragsbestaetigung, ab_id, auth["mandant_id"])
    mandant = db.get(Mandant, auth["mandant_id"])
    return Response(content=render_auftragsbestaetigung_pdf(mandant, ab), media_type="application/pdf")


@router.post("/lieferscheine", response_model=LieferscheinResponse, status_code=status.HTTP_201_CREATED)
def create_lieferschein(payload: LieferscheinCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> LieferscheinResponse:
    """Lieferscheine tragen eigene Positionen (Menge/Beschreibung, ohne Preis) statt die
    der Auftragsbestaetigung 1:1 zu kopieren, damit Teillieferungen abbildbar sind."""
    _lade_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    ab = get_scoped_or_404(db, Auftragsbestaetigung, payload.auftragsbestaetigung_id, mandant_id)

    now = datetime.now(timezone.utc)
    positionen = [
        LieferscheinPosition(reihenfolge=i, beschreibung=p.beschreibung, menge=p.menge)
        for i, p in enumerate(payload.positionen)
    ]
    lieferschein = Lieferschein(
        mandant_id=mandant_id, auftragsbestaetigung_id=ab.id, kontakt_id=ab.kontakt_id,
        nummer=allocate_lieferschein_number(db, mandant_id=mandant_id, jahr=now.year),
        lieferdatum=payload.lieferdatum, positionen=positionen,
    )
    db.add(lieferschein)
    db.flush()
    record_audit(db, aktion="lieferschein_erstellt", mandant_id=mandant_id, user_id=auth["sub"], kontext=lieferschein.nummer)
    db.commit()
    return _lieferschein_response(lieferschein)


@router.get("/lieferscheine", response_model=list[LieferscheinResponse])
def list_lieferscheine(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[LieferscheinResponse]:
    _lade_mandant(db, auth)
    items = (
        db.query(Lieferschein)
        .filter(Lieferschein.mandant_id == auth["mandant_id"])
        .order_by(Lieferschein.erstellt_am.desc())
        .all()
    )
    return [_lieferschein_response(ls) for ls in items]


@router.get("/lieferscheine/{lieferschein_id}", response_model=LieferscheinResponse)
def get_lieferschein(lieferschein_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> LieferscheinResponse:
    _lade_mandant(db, auth)
    ls = get_scoped_or_404(db, Lieferschein, lieferschein_id, auth["mandant_id"])
    return _lieferschein_response(ls)


@router.get("/lieferscheine/{lieferschein_id}/pdf")
def get_lieferschein_pdf(lieferschein_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    mandant = _lade_mandant(db, auth)
    ls = get_scoped_or_404(db, Lieferschein, lieferschein_id, auth["mandant_id"])
    return Response(content=render_lieferschein_pdf_for(mandant, ls), media_type="application/pdf")
