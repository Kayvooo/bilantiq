from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class AnlageCreate(BaseModel):
    bezeichnung: str = Field(min_length=1, max_length=255)
    anschaffungsdatum: date
    anschaffungskosten_netto: Decimal = Field(gt=0)
    nutzungsdauer_jahre: int = Field(ge=1, le=50)
    kategorie: str | None = None


class AfaPlanEintrag(BaseModel):
    jahr: int
    afa_betrag: Decimal
    restbuchwert_ende: Decimal


class AnlageResponse(BaseModel):
    id: str
    bezeichnung: str
    anschaffungsdatum: date
    anschaffungskosten_netto: Decimal
    nutzungsdauer_jahre: int
    kategorie: str | None
    ist_gwg: bool
    afa_plan: list[AfaPlanEintrag]


class AnlagenUebersicht(BaseModel):
    anlagen: list[AnlageResponse]
    afa_gesamt_jahr: Decimal
    jahr: int
    hinweis: str
