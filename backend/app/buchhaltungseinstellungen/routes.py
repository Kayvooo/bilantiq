from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.buchhaltungseinstellungen.models import Buchhaltungseinstellungen
from app.buchhaltungseinstellungen.schemas import (
    BuchhaltungseinstellungenPayload,
    BuchhaltungseinstellungenResponse,
)
from app.db import get_db

router = APIRouter(prefix="/buchhaltungseinstellungen", tags=["buchhaltungseinstellungen"])

DEFAULTS = BuchhaltungseinstellungenResponse(
    standard_zahlungsziel_tage=14,
    standard_ust_satz=Decimal("19.00"),
    kleinunternehmer=False,
)


def _response(einstellungen: Buchhaltungseinstellungen) -> BuchhaltungseinstellungenResponse:
    return BuchhaltungseinstellungenResponse(
        standard_zahlungsziel_tage=einstellungen.standard_zahlungsziel_tage,
        standard_ust_satz=einstellungen.standard_ust_satz,
        kleinunternehmer=einstellungen.kleinunternehmer,
    )


@router.get("", response_model=BuchhaltungseinstellungenResponse)
def get_einstellungen(
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> BuchhaltungseinstellungenResponse:
    einstellungen = db.get(Buchhaltungseinstellungen, auth["mandant_id"])
    return _response(einstellungen) if einstellungen is not None else DEFAULTS


@router.put("", response_model=BuchhaltungseinstellungenResponse)
def put_einstellungen(
    payload: BuchhaltungseinstellungenPayload,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> BuchhaltungseinstellungenResponse:
    einstellungen = db.get(Buchhaltungseinstellungen, auth["mandant_id"])
    if einstellungen is None:
        einstellungen = Buchhaltungseinstellungen(
            mandant_id=auth["mandant_id"],
            **payload.model_dump(),
        )
        db.add(einstellungen)
    else:
        for field, value in payload.model_dump().items():
            setattr(einstellungen, field, value)
    db.commit()
    return _response(einstellungen)
