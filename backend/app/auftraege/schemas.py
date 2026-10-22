from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AuftragsbestaetigungCreate(BaseModel):
    quote_id: str


class AuftragsbestaetigungPositionResponse(BaseModel):
    id: str
    beschreibung: str
    menge: Decimal
    einzelpreis: Decimal
    ust_satz: Decimal


class AuftragsbestaetigungResponse(BaseModel):
    id: str
    quote_id: str
    kontakt_id: str
    nummer: str
    waehrung: str
    netto_gesamt: Decimal
    ust_gesamt: Decimal
    brutto_gesamt: Decimal
    erstellt_am: datetime
    positionen: list[AuftragsbestaetigungPositionResponse]


class LieferscheinPositionCreate(BaseModel):
    beschreibung: str = Field(min_length=1, max_length=500)
    menge: Decimal = Field(gt=0)


class LieferscheinPositionResponse(LieferscheinPositionCreate):
    id: str


class LieferscheinCreate(BaseModel):
    auftragsbestaetigung_id: str
    lieferdatum: date
    positionen: list[LieferscheinPositionCreate] = Field(min_length=1)


class LieferscheinResponse(BaseModel):
    id: str
    auftragsbestaetigung_id: str
    kontakt_id: str
    nummer: str
    lieferdatum: date
    erstellt_am: datetime
    positionen: list[LieferscheinPositionResponse]
