from datetime import date

from pydantic import BaseModel, Field

from app.invoices.schemas import InvoicePositionCreate, InvoicePositionResponse
from app.wiederkehrend.models import INTERVALLE


class WiederkehrendeRechnungCreate(BaseModel):
    kontakt_id: str
    bezeichnung: str = Field(min_length=1, max_length=255)
    intervall: str = Field(pattern="^(" + "|".join(INTERVALLE) + ")$")
    naechstes_datum: date
    enddatum: date | None = None
    positionen: list[InvoicePositionCreate] = Field(min_length=1)


class WiederkehrendeRechnungResponse(BaseModel):
    id: str
    kontakt_id: str
    kontakt_name: str
    bezeichnung: str
    intervall: str
    naechstes_datum: date
    enddatum: date | None
    aktiv: bool
    positionen: list[InvoicePositionResponse]


class ErzeugungsErgebnis(BaseModel):
    erzeugte_rechnungen: list[str]  # Invoice-IDs
    anzahl: int
