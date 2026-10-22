from sqlalchemy.orm import Session

from app.auftraege.models import Auftragsbestaetigungsnummernkreis, Lieferscheinnummernkreis
from app.core.numbering import allocate_gapless_number


def allocate_auftragsbestaetigung_number(db: Session, *, mandant_id: str, jahr: int) -> str:
    return allocate_gapless_number(db, Auftragsbestaetigungsnummernkreis, mandant_id=mandant_id, jahr=jahr, prefix="AB")


def allocate_lieferschein_number(db: Session, *, mandant_id: str, jahr: int) -> str:
    return allocate_gapless_number(db, Lieferscheinnummernkreis, mandant_id=mandant_id, jahr=jahr, prefix="LS")
