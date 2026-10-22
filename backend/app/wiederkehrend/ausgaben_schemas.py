from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.intervall import INTERVALLE


class WiederkehrendeAusgabeCreate(BaseModel):
    bezeichnung: str = Field(min_length=1, max_length=255)
    anbieter: str = Field(min_length=1, max_length=255)
    betrag: Decimal = Field(gt=0)
    ust_satz: Decimal = Field(ge=0, le=100)
    kategorie: str = Field(min_length=1, max_length=100)
    intervall: str = Field(pattern="^(" + "|".join(INTERVALLE) + ")$")
    naechstes_datum: date
    enddatum: date | None = None


class WiederkehrendeAusgabeResponse(BaseModel):
    id: str
    bezeichnung: str
    anbieter: str
    betrag: Decimal
    ust_satz: Decimal
    kategorie: str
    intervall: str
    naechstes_datum: date
    enddatum: date | None
    aktiv: bool


class AusgabenErzeugungsErgebnis(BaseModel):
    erzeugte_ausgaben: list[str]
    anzahl: int
