from decimal import Decimal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.core.audit_log import record as record_audit
from app.db import get_db
from app.kassenbuch.models import KassenbuchEintrag
from app.kassenbuch.schemas import KassenbuchEintragCreate, KassenbuchEintragResponse, KassenbuchUebersicht

router = APIRouter(prefix="/kassenbuch", tags=["kassenbuch"])


def _mit_laufendem_saldo(eintraege: list[KassenbuchEintrag]) -> list[KassenbuchEintragResponse]:
    """eintraege muss chronologisch (aeltester zuerst) sortiert sein — der laufende
    Saldo ergibt nur in dieser Reihenfolge Sinn. Rueckgabe ist neuester zuerst,
    wie die uebrigen Listen dieser App (z.B. InvoiceList)."""
    saldo = Decimal("0")
    ergebnis = []
    for eintrag in eintraege:
        saldo += eintrag.betrag if eintrag.typ == "einnahme" else -eintrag.betrag
        ergebnis.append(KassenbuchEintragResponse(
            id=eintrag.id, datum=eintrag.datum, typ=eintrag.typ, betrag=eintrag.betrag,
            beschreibung=eintrag.beschreibung, saldo_nach_buchung=saldo, erstellt_am=eintrag.erstellt_am.isoformat(),
        ))
    ergebnis.reverse()
    return ergebnis


@router.post("", response_model=KassenbuchEintragResponse, status_code=status.HTTP_201_CREATED)
def create_kassenbuch_eintrag(
    payload: KassenbuchEintragCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> KassenbuchEintragResponse:
    eintrag = KassenbuchEintrag(mandant_id=auth["mandant_id"], **payload.model_dump())
    db.add(eintrag)
    db.flush()

    alle = (
        db.query(KassenbuchEintrag)
        .filter(KassenbuchEintrag.mandant_id == auth["mandant_id"])
        .order_by(KassenbuchEintrag.datum, KassenbuchEintrag.erstellt_am)
        .all()
    )
    record_audit(
        db, aktion="kassenbuch_buchung", mandant_id=auth["mandant_id"], user_id=auth["sub"],
        kontext=f"{eintrag.typ} {eintrag.betrag}",
    )
    db.commit()
    return next(e for e in _mit_laufendem_saldo(alle) if e.id == eintrag.id)


@router.get("", response_model=KassenbuchUebersicht)
def list_kassenbuch(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> KassenbuchUebersicht:
    alle = (
        db.query(KassenbuchEintrag)
        .filter(KassenbuchEintrag.mandant_id == auth["mandant_id"])
        .order_by(KassenbuchEintrag.datum, KassenbuchEintrag.erstellt_am)
        .all()
    )
    eintraege = _mit_laufendem_saldo(alle)
    bestand = eintraege[0].saldo_nach_buchung if eintraege else Decimal("0")
    return KassenbuchUebersicht(eintraege=eintraege, aktueller_kassenbestand=bestand)
