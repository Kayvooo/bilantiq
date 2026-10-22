from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.produkte.models import Lagerbewegung, Produkt
from app.produkte.schemas import (
    LagerbewegungCreate,
    LagerbewegungResponse,
    ProduktCreate,
    ProduktResponse,
    ProduktUpdate,
)

router = APIRouter(prefix="/produkte", tags=["produkte"])


def _lagerbestand(db: Session, produkt: Produkt) -> Decimal:
    """Summiert alle Lagerbewegungen eines Produkts frisch auf (zugang positiv,
    abgang negativ), statt einen laufenden Zaehler zu speichern -- vermeidet die
    klassische Cache-Drift zwischen einem gespeicherten Bestand und dem Ledger."""
    bewegungen = (
        db.query(Lagerbewegung)
        .filter(Lagerbewegung.produkt_id == produkt.id, Lagerbewegung.mandant_id == produkt.mandant_id)
        .all()
    )
    bestand = Decimal("0")
    for bewegung in bewegungen:
        bestand += bewegung.menge if bewegung.typ == "zugang" else -bewegung.menge
    return bestand


def _response(produkt: Produkt, db: Session) -> ProduktResponse:
    return ProduktResponse(
        id=produkt.id,
        bezeichnung=produkt.bezeichnung,
        beschreibung=produkt.beschreibung,
        einzelpreis=produkt.einzelpreis,
        ust_satz=produkt.ust_satz,
        einheit=produkt.einheit,
        aktiv=produkt.aktiv,
        lagerbestand_aktiv=produkt.lagerbestand_aktiv,
        artikelnummer=produkt.artikelnummer,
        lagerbestand=_lagerbestand(db, produkt) if produkt.lagerbestand_aktiv else None,
    )


def _bewegung_response(bewegung: Lagerbewegung) -> LagerbewegungResponse:
    return LagerbewegungResponse(
        id=bewegung.id,
        produkt_id=bewegung.produkt_id,
        datum=bewegung.datum,
        typ=bewegung.typ,
        menge=bewegung.menge,
        grund=bewegung.grund,
    )


@router.post("", response_model=ProduktResponse, status_code=status.HTTP_201_CREATED)
def create_produkt(
    payload: ProduktCreate,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> ProduktResponse:
    produkt = Produkt(mandant_id=auth["mandant_id"], **payload.model_dump())
    db.add(produkt)
    db.commit()
    return _response(produkt, db)


@router.get("", response_model=list[ProduktResponse])
def list_produkte(
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> list[ProduktResponse]:
    produkte = db.query(Produkt).filter(Produkt.mandant_id == auth["mandant_id"]).all()
    produkte.sort(key=lambda produkt: produkt.bezeichnung.casefold())
    return [_response(produkt, db) for produkt in produkte]


@router.patch("/{produkt_id}", response_model=ProduktResponse)
def update_produkt(
    produkt_id: str,
    payload: ProduktUpdate,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> ProduktResponse:
    produkt = get_scoped_or_404(db, Produkt, produkt_id, auth["mandant_id"])
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(produkt, field, value)
    db.commit()
    return _response(produkt, db)


@router.post(
    "/{produkt_id}/lagerbewegungen",
    response_model=LagerbewegungResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lagerbewegung(
    produkt_id: str,
    payload: LagerbewegungCreate,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> LagerbewegungResponse:
    produkt = get_scoped_or_404(db, Produkt, produkt_id, auth["mandant_id"])

    if payload.typ == "abgang":
        bestand = _lagerbestand(db, produkt)
        if payload.menge > bestand:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nicht genug Bestand für diesen Warenausgang.",
            )

    bewegung = Lagerbewegung(mandant_id=auth["mandant_id"], produkt_id=produkt.id, **payload.model_dump())
    db.add(bewegung)
    record_audit(
        db, aktion="lagerbewegung_buchung", mandant_id=auth["mandant_id"], user_id=auth["sub"],
        kontext=f"{bewegung.typ} {bewegung.menge} ({produkt.bezeichnung})",
    )
    db.commit()
    return _bewegung_response(bewegung)


@router.get("/{produkt_id}/lagerbewegungen", response_model=list[LagerbewegungResponse])
def list_lagerbewegungen(
    produkt_id: str,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> list[LagerbewegungResponse]:
    produkt = get_scoped_or_404(db, Produkt, produkt_id, auth["mandant_id"])
    bewegungen = (
        db.query(Lagerbewegung)
        .filter(Lagerbewegung.produkt_id == produkt.id, Lagerbewegung.mandant_id == auth["mandant_id"])
        .order_by(Lagerbewegung.datum.desc(), Lagerbewegung.erstellt_am.desc())
        .all()
    )
    return [_bewegung_response(bewegung) for bewegung in bewegungen]
