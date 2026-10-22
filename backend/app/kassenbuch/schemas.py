from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class KassenbuchEintragCreate(BaseModel):
    datum: date
    typ: str = Field(pattern="^(einnahme|ausgabe)$")
    betrag: Decimal = Field(gt=0)
    beschreibung: str = Field(min_length=1, max_length=500)


class KassenbuchEintragResponse(BaseModel):
    id: str
    datum: date
    typ: str
    betrag: Decimal
    beschreibung: str
    saldo_nach_buchung: Decimal
    erstellt_am: str


class KassenbuchUebersicht(BaseModel):
    eintraege: list[KassenbuchEintragResponse]
    aktueller_kassenbestand: Decimal
