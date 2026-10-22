from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.einnahmen.models import SonstigeEinnahme
from app.einnahmen.schemas import (
    SonstigeEinnahmeCreate,
    SonstigeEinnahmeResponse,
    SonstigeEinnahmeUpdate,
)

router = APIRouter(prefix="/einnahmen", tags=["einnahmen"])


def _response(einnahme: SonstigeEinnahme) -> SonstigeEinnahmeResponse:
    return SonstigeEinnahmeResponse(
        id=einnahme.id,
        bezeichnung=einnahme.bezeichnung,
        betrag_brutto=einnahme.betrag_brutto,
        ust_satz=einnahme.ust_satz,
        datum=einnahme.datum,
        verwendungszweck=einnahme.verwendungszweck,
    )


@router.post("", response_model=SonstigeEinnahmeResponse, status_code=status.HTTP_201_CREATED)
def create_einnahme(
    payload: SonstigeEinnahmeCreate,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> SonstigeEinnahmeResponse:
    einnahme = SonstigeEinnahme(mandant_id=auth["mandant_id"], **payload.model_dump())
    db.add(einnahme)
    db.commit()
    return _response(einnahme)


@router.get("", response_model=list[SonstigeEinnahmeResponse])
def list_einnahmen(
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> list[SonstigeEinnahmeResponse]:
    einnahmen = (
        db.query(SonstigeEinnahme)
        .filter(SonstigeEinnahme.mandant_id == auth["mandant_id"])
        .order_by(SonstigeEinnahme.datum.desc())
        .all()
    )
    # Gleiches Datum stabil nach entschluesselter Bezeichnung sortieren.
    einnahmen.sort(key=lambda item: (-item.datum.toordinal(), item.bezeichnung.casefold()))
    return [_response(einnahme) for einnahme in einnahmen]


@router.patch("/{einnahme_id}", response_model=SonstigeEinnahmeResponse)
def update_einnahme(
    einnahme_id: str,
    payload: SonstigeEinnahmeUpdate,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> SonstigeEinnahmeResponse:
    einnahme = get_scoped_or_404(db, SonstigeEinnahme, einnahme_id, auth["mandant_id"])
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(einnahme, field, value)
    db.commit()
    return _response(einnahme)
