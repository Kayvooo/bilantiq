"""Wiederkehrende Ausgaben: eine Vorlage erzeugt beim Faelligwerden direkt eine
gebuchte Ausgabe OHNE Beleg (Ausgabe.receipt_id bleibt None) — siehe Annahmen in
app/wiederkehrend/models.py::WiederkehrendeAusgabe. Kein Scheduler/Cron: Erzeugung
ist on-demand ueber POST .../erzeugen, analog zu wiederkehrenden Rechnungen."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.core.audit_log import record as record_audit
from app.core.intervall import naechster_termin
from app.core.kontenrahmen import ausgaben_konto
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.receipts.models import Ausgabe
from app.receipts.schemas import AusgabeResponse
from app.wiederkehrend.ausgaben_schemas import (
    AusgabenErzeugungsErgebnis,
    WiederkehrendeAusgabeCreate,
    WiederkehrendeAusgabeResponse,
)
from app.wiederkehrend.models import WiederkehrendeAusgabe

router = APIRouter(tags=["wiederkehrend-ausgaben"])


@router.get("/ausgaben", response_model=list[AusgabeResponse])
def list_ausgaben(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[AusgabeResponse]:
    """Direkte Sicht auf alle gebuchten Ausgaben, unabhaengig vom Ursprung (Beleg-
    Upload oder wiederkehrende Vorlage) — fehlte bisher, ReceiptList zeigt nur
    Belege, keine wiederkehrend ohne Beleg gebuchten Ausgaben."""
    ausgaben = db.query(Ausgabe).filter(Ausgabe.mandant_id == auth["mandant_id"]).order_by(Ausgabe.datum.desc()).all()
    return [
        AusgabeResponse(
            id=a.id, receipt_id=a.receipt_id, betrag=a.betrag, datum=a.datum,
            zahlungsdatum=a.zahlungsdatum, anbieter=a.anbieter, ust_satz=a.ust_satz,
            steueranteile=[
                {"ust_satz": anteil.ust_satz, "bruttobetrag": anteil.bruttobetrag}
                for anteil in a.steueranteile
            ],
            kategorie=a.kategorie, konto=a.konto,
        )
        for a in ausgaben
    ]


def _response(vorlage: WiederkehrendeAusgabe) -> WiederkehrendeAusgabeResponse:
    return WiederkehrendeAusgabeResponse(
        id=vorlage.id, bezeichnung=vorlage.bezeichnung, anbieter=vorlage.anbieter,
        betrag=vorlage.betrag, ust_satz=vorlage.ust_satz, kategorie=vorlage.kategorie,
        intervall=vorlage.intervall, naechstes_datum=vorlage.naechstes_datum,
        enddatum=vorlage.enddatum, aktiv=vorlage.aktiv,
    )


@router.post("/wiederkehrende-ausgaben", response_model=WiederkehrendeAusgabeResponse, status_code=status.HTTP_201_CREATED)
def create_wiederkehrende_ausgabe(
    payload: WiederkehrendeAusgabeCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> WiederkehrendeAusgabeResponse:
    if payload.enddatum and payload.enddatum < payload.naechstes_datum:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enddatum liegt vor dem naechsten Ausgabedatum.")

    vorlage = WiederkehrendeAusgabe(mandant_id=auth["mandant_id"], **payload.model_dump())
    db.add(vorlage)
    db.commit()
    return _response(vorlage)


@router.get("/wiederkehrende-ausgaben", response_model=list[WiederkehrendeAusgabeResponse])
def list_wiederkehrende_ausgaben(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[WiederkehrendeAusgabeResponse]:
    vorlagen = (
        db.query(WiederkehrendeAusgabe)
        .filter(WiederkehrendeAusgabe.mandant_id == auth["mandant_id"])
        .order_by(WiederkehrendeAusgabe.naechstes_datum)
        .all()
    )
    return [_response(v) for v in vorlagen]


@router.post("/wiederkehrende-ausgaben/{vorlage_id}/deaktivieren", response_model=WiederkehrendeAusgabeResponse)
def deaktivieren(vorlage_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> WiederkehrendeAusgabeResponse:
    vorlage = get_scoped_or_404(db, WiederkehrendeAusgabe, vorlage_id, auth["mandant_id"])
    vorlage.aktiv = False
    db.commit()
    return _response(vorlage)


@router.post("/wiederkehrende-ausgaben/erzeugen", response_model=AusgabenErzeugungsErgebnis)
def erzeuge_faellige_ausgaben(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> AusgabenErzeugungsErgebnis:
    mandant_id = auth["mandant_id"]
    heute = date.today()
    faellige = (
        db.query(WiederkehrendeAusgabe)
        .filter(
            WiederkehrendeAusgabe.mandant_id == mandant_id,
            WiederkehrendeAusgabe.aktiv.is_(True),
            WiederkehrendeAusgabe.naechstes_datum <= heute,
        )
        .all()
    )

    erzeugte_ids = []
    for vorlage in faellige:
        ausgabe = Ausgabe(
            mandant_id=mandant_id, receipt_id=None, betrag=vorlage.betrag, datum=vorlage.naechstes_datum,
            zahlungsdatum=vorlage.naechstes_datum, anbieter=vorlage.anbieter,
            ust_satz=vorlage.ust_satz, kategorie=vorlage.kategorie,
            konto=ausgaben_konto(vorlage.kategorie),
        )
        db.add(ausgabe)
        db.flush()
        erzeugte_ids.append(ausgabe.id)

        vorlage.naechstes_datum = naechster_termin(vorlage.naechstes_datum, vorlage.intervall)
        if vorlage.enddatum and vorlage.naechstes_datum > vorlage.enddatum:
            vorlage.aktiv = False

    if erzeugte_ids:
        record_audit(db, aktion="wiederkehrende_ausgaben_erzeugt", mandant_id=mandant_id, user_id=auth["sub"], kontext=str(len(erzeugte_ids)))
    db.commit()
    return AusgabenErzeugungsErgebnis(erzeugte_ausgaben=erzeugte_ids, anzahl=len(erzeugte_ids))
