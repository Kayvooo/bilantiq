"""Nummernkreis der Rechnungen ansehen und (nur als Inhaber) fortsetzen."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth, require_owner
from app.db import get_db
from app.nummernkreis import service

router = APIRouter(prefix="/einstellungen/nummernkreis", tags=["nummernkreis"])


class NummernkreisResponse(BaseModel):
    jahr: int
    naechste_nummer: int
    naechste_rechnungsnummer: str
    hoechste_bilantiq: int
    hoechste_altsystem: int | None
    # Kleinster Wert, auf den sich die naechste Nummer setzen laesst.
    mindestens: int
    # True, wenn die naechste Bilantiq-Nummer im alten Programm schon vergeben ist.
    kollision: bool
    vorschlag: int | None  # nur bei Kollision: die erste freie Nummer


class NummernkreisEingabe(BaseModel):
    naechste_nummer: int = Field(ge=1, le=service.MAX_NUMMER)


def _antwort(stand: service.Stand) -> NummernkreisResponse:
    return NummernkreisResponse(
        jahr=stand.jahr, naechste_nummer=stand.naechste_nummer, naechste_rechnungsnummer=stand.naechste_rechnungsnummer,
        hoechste_bilantiq=stand.hoechste_bilantiq, hoechste_altsystem=stand.hoechste_altsystem, mindestens=stand.mindestens,
        kollision=stand.kollision, vorschlag=stand.mindestens if stand.kollision else None,
    )


@router.get("", response_model=NummernkreisResponse)
def lese(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> NummernkreisResponse:
    return _antwort(service.lese_stand(db, auth["mandant_id"]))


@router.put("", response_model=NummernkreisResponse)
def setze(payload: NummernkreisEingabe, auth=Depends(require_owner), db: Session = Depends(get_db)) -> NummernkreisResponse:
    try:
        stand = service.setze_naechste_nummer(db, mandant_id=auth["mandant_id"], user_id=auth["sub"], wert=payload.naechste_nummer)
    except service.NummernkreisFehler as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _antwort(stand)
