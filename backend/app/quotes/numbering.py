from sqlalchemy.orm import Session

from app.core.numbering import allocate_gapless_number
from app.quotes.models import Angebotsnummernkreis


def allocate_quote_number(db: Session, *, mandant_id: str, jahr: int) -> str:
    return allocate_gapless_number(db, Angebotsnummernkreis, mandant_id=mandant_id, jahr=jahr, prefix="AN")
