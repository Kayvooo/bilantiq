from decimal import Decimal

from sqlalchemy.orm import Session

from app.anlagen.afa import afa_fuer_jahr, berechne_afa_plan
from app.anlagen.models import Anlage


def sammle_afa_jahreswerte(
    db: Session,
    *,
    mandant_id: str,
    jahr: int,
) -> list[tuple[Anlage, Decimal]]:
    """Positive Jahres-AfA je Anlage, zentral fuer EÜR und Buchungszeilen."""
    anlagen = db.query(Anlage).filter(Anlage.mandant_id == mandant_id).all()
    werte: list[tuple[Anlage, Decimal]] = []
    for anlage in anlagen:
        plan = berechne_afa_plan(
            anlage.anschaffungsdatum,
            anlage.anschaffungskosten_netto,
            anlage.nutzungsdauer_jahre,
        )
        betrag = afa_fuer_jahr(plan, jahr)
        if betrag > 0:
            werte.append((anlage, betrag))
    return werte
