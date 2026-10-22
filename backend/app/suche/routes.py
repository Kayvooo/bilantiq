"""Globale Suche. POST statt GET, damit Suchbegriffe (Kundennamen, Betraege) nicht in Zugriffs-
und Proxy-Logs landen. Suchanfragen werden bewusst nicht protokolliert."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.db import get_db
from app.suche import service
from app.suche.schemas import GruppeResponse, SucheAnfrage, SucheResponse, TrefferResponse

router = APIRouter(prefix="/suche", tags=["suche"])


@router.post("", response_model=SucheResponse)
def suche(payload: SucheAnfrage, auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> SucheResponse:
    gruppen, unvollstaendig = service.suche(db, auth["mandant_id"], payload.q, payload.limit)
    return SucheResponse(
        gruppen=[
            GruppeResponse(
                typ=g.typ, label=g.label, gesamt=g.gesamt,
                treffer=[TrefferResponse(id=t.id, titel=t.titel, untertitel=t.untertitel, ziel=t.ziel) for t in g.treffer],
            )
            for g in gruppen
        ],
        unvollstaendig=unvollstaendig,
    )
