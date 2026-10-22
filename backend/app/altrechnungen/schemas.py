from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ZahlungResponse(BaseModel):
    id: str
    datum: date
    betrag: Decimal
    quelle: str


class AltrechnungResponse(BaseModel):
    id: str
    nummer: str
    kontakt_id: str
    kontakt_name: str
    rechnungsdatum: date
    faelligkeit: date | None
    brutto: Decimal
    offen_beim_import: Decimal
    offen: Decimal
    status: Literal["offen", "ueberfaellig", "bezahlt"]
    bezahlt_im_altsystem: bool
    bezahlt_im_altsystem_am: date | None
    hat_pdf: bool
    zahlungen: list[ZahlungResponse]


class AltrechnungListe(BaseModel):
    gesamt: int  # alle Treffer des Filters, auch wenn nur `limit` geliefert werden
    eintraege: list[AltrechnungResponse]


class ZahlungEingabe(BaseModel):
    datum: date | None = None
    betrag: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class PdfErgebnis(BaseModel):
    dateiname: str
    status: Literal["zugeordnet", "unklar", "keine", "abgelehnt"]
    altrechnung_id: str | None = None
    nummer: str | None = None
    grund: str | None = None


class PdfAntwort(BaseModel):
    ergebnisse: list[PdfErgebnis]


class HistorieEintrag(BaseModel):
    art: Literal["bilantiq", "altsystem"]
    id: str
    nummer: str | None
    datum: date
    brutto: Decimal
    offen: Decimal
    status: str


class HistorieResponse(BaseModel):
    kontakt_id: str
    eintraege: list[HistorieEintrag]
    umsatz_brutto_bilantiq: Decimal
    umsatz_brutto_altsystem: Decimal
    offen_brutto: Decimal
