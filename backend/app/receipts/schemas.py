from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class FieldValue(BaseModel):
    wert: str | None
    confidence: float | None
    unklar: bool


class SteueranteilInput(BaseModel):
    ust_satz: Decimal
    bruttobetrag: Decimal


class SteueranteilResponse(BaseModel):
    ust_satz: Decimal
    bruttobetrag: Decimal


class ReceiptResponse(BaseModel):
    id: str
    status: str
    hochgeladen_am: str
    betrag: FieldValue
    datum: FieldValue
    anbieter: FieldValue
    ust_satz: FieldValue
    kategorie_vorschlag: FieldValue
    begruendung: str | None
    buchungskonto_vorschlag: str | None
    gebucht_als: str | None
    ist_duplikat: bool = False
    duplikat_von: str | None = None
    beleg_typ: str = "ocr"
    rechnungsnummer: str | None = None
    faelligkeit: str | None = None
    iban: str | None = None
    steueranteile_vorschlag: list[SteueranteilResponse] | None = None
    hinweise: list[str] = []
    zahlungsdatum_vorschlag: str | None = None


class LernVorschlagResponse(BaseModel):
    gefunden: bool
    kategorie: str | None = None
    konto: str | None = None
    ust_satz: str | None = None
    confidence: float | None = None
    begruendung: str | None = None


class BestaetigungRequest(BaseModel):
    """Every field is optional — omitted ones fall back to the AI's extracted value.
    A field must end up set (either by the AI above the confidence threshold, or here)
    or confirmation is rejected. `konto` defaults to the Kontenrahmen suggestion for
    the final kategorie if not given — see app/core/kontenrahmen.py."""
    betrag: Decimal | None = None
    datum: date | None = None
    zahlungsdatum: date | None = None
    anbieter: str | None = None
    ust_satz: Decimal | None = None
    steueranteile: list[SteueranteilInput] | None = None
    kategorie: str | None = None
    konto: str | None = None


class AusgabeResponse(BaseModel):
    id: str
    receipt_id: str | None  # None bei wiederkehrend erzeugten Ausgaben ohne Beleg
    betrag: Decimal
    datum: date
    zahlungsdatum: date
    anbieter: str
    ust_satz: Decimal | None
    steueranteile: list[SteueranteilResponse] = Field(default_factory=list)
    kategorie: str
    konto: str
