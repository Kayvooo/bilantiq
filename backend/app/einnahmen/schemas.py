from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SonstigeEinnahmeCreate(BaseModel):
    bezeichnung: str = Field(min_length=1, max_length=255)
    betrag_brutto: Decimal = Field(gt=0)
    ust_satz: Decimal = Field(ge=0, le=100)
    datum: date
    verwendungszweck: str | None = Field(default=None, max_length=500)


class SonstigeEinnahmeResponse(SonstigeEinnahmeCreate):
    id: str


class SonstigeEinnahmeUpdate(BaseModel):
    bezeichnung: str | None = Field(default=None, min_length=1, max_length=255)
    betrag_brutto: Decimal | None = Field(default=None, gt=0)
    ust_satz: Decimal | None = Field(default=None, ge=0, le=100)
    datum: date | None = None
    verwendungszweck: str | None = Field(default=None, max_length=500)
