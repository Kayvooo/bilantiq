from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class QuotePositionCreate(BaseModel):
    beschreibung: str = Field(min_length=1, max_length=500)
    menge: Decimal = Field(gt=0)
    einzelpreis: Decimal
    ust_satz: Decimal = Field(ge=0, le=100)


class QuotePositionResponse(QuotePositionCreate):
    id: str


class QuoteCreate(BaseModel):
    kontakt_id: str
    gueltig_bis: date
    waehrung: str = Field(default="EUR", min_length=3, max_length=3)
    positionen: list[QuotePositionCreate] = Field(min_length=1)


class QuoteResponse(BaseModel):
    id: str
    kontakt_id: str
    nummer: str | None
    status: str  # entwurf | versendet | angenommen | abgelehnt — plus computed "abgelaufen" below
    anzeige_status: str
    gueltig_bis: date
    waehrung: str
    netto_gesamt: Decimal
    ust_gesamt: Decimal
    brutto_gesamt: Decimal
    umgewandelt_in_invoice_id: str | None
    positionen: list[QuotePositionResponse]
    email_versendet_am: str | None = None
    kontakt_email_vorhanden: bool = False


class VersendenRequest(BaseModel):
    """Body fuer POST .../per-email-senden -- text ist optional, ohne ihn kommt ein
    fester deutscher Standardtext zum Einsatz (siehe routes.py)."""

    text: str | None = None
