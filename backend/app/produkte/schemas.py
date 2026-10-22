from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ProduktCreate(BaseModel):
    bezeichnung: str = Field(min_length=1, max_length=255)
    beschreibung: str | None = Field(default=None, max_length=500)
    einzelpreis: Decimal = Field(ge=0)
    ust_satz: Decimal = Field(ge=0, le=100)
    einheit: str = Field(min_length=1, max_length=50)
    aktiv: bool = True
    lagerbestand_aktiv: bool = False
    artikelnummer: str | None = Field(default=None, max_length=50)


class ProduktResponse(ProduktCreate):
    id: str
    # None, wenn lagerbestand_aktiv False ist; sonst die aus den Lagerbewegungen
    # aufsummierte aktuelle Menge (siehe _lagerbestand() in routes.py).
    lagerbestand: Decimal | None = None


class ProduktUpdate(BaseModel):
    bezeichnung: str | None = Field(default=None, min_length=1, max_length=255)
    beschreibung: str | None = Field(default=None, max_length=500)
    einzelpreis: Decimal | None = Field(default=None, ge=0)
    ust_satz: Decimal | None = Field(default=None, ge=0, le=100)
    einheit: str | None = Field(default=None, min_length=1, max_length=50)
    aktiv: bool | None = None
    lagerbestand_aktiv: bool | None = None
    artikelnummer: str | None = Field(default=None, max_length=50)


class LagerbewegungCreate(BaseModel):
    datum: date
    typ: Literal["zugang", "abgang"]
    menge: Decimal = Field(gt=0)
    grund: str = Field(min_length=1, max_length=500)


class LagerbewegungResponse(LagerbewegungCreate):
    id: str
    produkt_id: str
