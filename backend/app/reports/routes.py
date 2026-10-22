from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.db import get_db
from app.reports.cashflow import compute_cashflow
from app.reports.dashboard import compute_dashboard
from app.reports.datev import build_datev_export
from app.reports.euer import compute_euer
from app.reports.bwa import compute_bwa
from app.reports.schemas import BwaResponse, CashflowResponse, DashboardResponse, EuerResponse, SusaResponse, UstvaResponse
from app.reports.susa import compute_susa
from app.reports.ustva import compute_ustva

router = APIRouter(prefix="/berichte", tags=["reports"])


def _lade_mandant(db: Session, auth: dict) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> DashboardResponse:
    zieljahr = jahr or date.today().year
    return DashboardResponse(**compute_dashboard(db, mandant_id=auth["mandant_id"], jahr=zieljahr))


@router.get("/euer", response_model=EuerResponse)
def get_euer(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> EuerResponse:
    zieljahr = jahr or date.today().year
    return EuerResponse(**compute_euer(db, mandant_id=auth["mandant_id"], jahr=zieljahr))


@router.get("/cashflow", response_model=CashflowResponse)
def get_cashflow(wochen: int = 8, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> CashflowResponse:
    _lade_mandant(db, auth)
    horizont = max(1, min(wochen, 26))  # sane bounds — a year-plus forecast from a flat average would be noise
    return CashflowResponse(**compute_cashflow(db, mandant_id=auth["mandant_id"], wochen=horizont))


@router.get("/ustva", response_model=UstvaResponse)
def get_ustva(
    jahr: int | None = None, zeitraum_typ: str = "monat", periode: int | None = None,
    auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> UstvaResponse:
    heute = date.today()
    zieljahr = jahr or heute.year
    if periode is None:
        periode = heute.month if zeitraum_typ == "monat" else (heute.month - 1) // 3 + 1

    try:
        daten = compute_ustva(db, mandant_id=auth["mandant_id"], jahr=zieljahr, zeitraum_typ=zeitraum_typ, periode=periode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UstvaResponse(**daten)


@router.get("/susa", response_model=SusaResponse)
def get_susa(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> SusaResponse:
    _lade_mandant(db, auth)
    zieljahr = jahr or date.today().year
    return SusaResponse(**compute_susa(db, mandant_id=auth["mandant_id"], jahr=zieljahr))


@router.get("/bwa", response_model=BwaResponse)
def get_bwa(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> BwaResponse:
    _lade_mandant(db, auth)
    zieljahr = jahr or date.today().year
    return BwaResponse(**compute_bwa(db, mandant_id=auth["mandant_id"], jahr=zieljahr))


@router.get("/datev-export")
def get_datev_export(jahr: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    mandant = _lade_mandant(db, auth)
    zieljahr = jahr or date.today().year
    csv_bytes = build_datev_export(db, mandant=mandant, jahr=zieljahr)
    return Response(
        content=csv_bytes, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="EXTF_Buchungsstapel_{zieljahr}.csv"'},
    )
