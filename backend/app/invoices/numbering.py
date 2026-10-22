from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.altrechnungen.models import Altrechnung
from app.altrechnungen.nummer import nummer_hash
from app.core.numbering import allocate_gapless_number
from app.invoices.models import Rechnungsnummernkreis


def allocate_invoice_number(db: Session, *, mandant_id: str, jahr: int) -> str:
    nummer = allocate_gapless_number(db, Rechnungsnummernkreis, mandant_id=mandant_id, jahr=jahr, prefix="RE")
    # Letzte Absicherung (§ 14 UStG: eindeutige Nummern): Gibt es die Nummer schon als Rechnung aus dem alten
    # Programm, wird nichts vergeben. Der Aufrufer rollt zurueck, der Zaehler bleibt unveraendert.
    if db.scalar(select(Altrechnung.id).where(Altrechnung.mandant_id == mandant_id, Altrechnung.nummer_hash == nummer_hash(mandant_id, nummer))):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Die Rechnungsnummer {nummer} gibt es schon bei den Rechnungen aus dem alten Programm. "
                "Bitte zuerst den Nummernkreis fortsetzen (Einstellungen, Buchhaltung, oder Datenumzug)."
            ),
        )
    return nummer
