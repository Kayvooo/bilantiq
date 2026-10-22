from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.anlagen.afa import GWG_GRENZE, afa_fuer_jahr, berechne_afa_plan
from app.anlagen.models import Anlage
from app.anlagen.schemas import AnlageCreate, AnlageResponse, AnlagenUebersicht
from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.db import get_db

router = APIRouter(prefix="/anlagen", tags=["anlagen"])

HINWEIS = (
    "Lineare Abschreibung nach §7 EStG, monatsgenau im Anschaffungsjahr. Keine amtlichen "
    "AfA-Tabellen hinterlegt — Nutzungsdauer wird selbst erfasst. GWG-Grenze (800 € netto) "
    "ist eine Annahme zum jetzigen Stand. Die Jahres-AfA fliesst in EÜR/BWA/SuSa/DATEV ein. "
    "Ersetzt keine Steuerberatung."
)


def _pruefe_mandant(db: Session, auth: dict) -> None:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")


def _response(anlage: Anlage) -> AnlageResponse:
    plan = berechne_afa_plan(anlage.anschaffungsdatum, anlage.anschaffungskosten_netto, anlage.nutzungsdauer_jahre)
    return AnlageResponse(
        id=anlage.id, bezeichnung=anlage.bezeichnung, anschaffungsdatum=anlage.anschaffungsdatum,
        anschaffungskosten_netto=anlage.anschaffungskosten_netto, nutzungsdauer_jahre=anlage.nutzungsdauer_jahre,
        kategorie=anlage.kategorie, ist_gwg=anlage.anschaffungskosten_netto <= GWG_GRENZE, afa_plan=plan,
    )


@router.post("", response_model=AnlageResponse, status_code=status.HTTP_201_CREATED)
def create_anlage(payload: AnlageCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> AnlageResponse:
    _pruefe_mandant(db, auth)
    anlage = Anlage(mandant_id=auth["mandant_id"], **payload.model_dump())
    db.add(anlage)
    db.commit()
    return _response(anlage)


@router.get("", response_model=AnlagenUebersicht)
def list_anlagen(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> AnlagenUebersicht:
    _pruefe_mandant(db, auth)
    zieljahr = jahr or date.today().year
    anlagen = db.query(Anlage).filter(Anlage.mandant_id == auth["mandant_id"]).order_by(Anlage.anschaffungsdatum.desc()).all()

    responses = []
    afa_gesamt = Decimal("0.00")
    for anlage in anlagen:
        plan = berechne_afa_plan(anlage.anschaffungsdatum, anlage.anschaffungskosten_netto, anlage.nutzungsdauer_jahre)
        afa_gesamt += afa_fuer_jahr(plan, zieljahr)
        responses.append(AnlageResponse(
            id=anlage.id, bezeichnung=anlage.bezeichnung, anschaffungsdatum=anlage.anschaffungsdatum,
            anschaffungskosten_netto=anlage.anschaffungskosten_netto, nutzungsdauer_jahre=anlage.nutzungsdauer_jahre,
            kategorie=anlage.kategorie, ist_gwg=anlage.anschaffungskosten_netto <= GWG_GRENZE, afa_plan=plan,
        ))
    return AnlagenUebersicht(anlagen=responses, afa_gesamt_jahr=afa_gesamt, jahr=zieljahr, hinweis=HINWEIS)
