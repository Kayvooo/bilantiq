from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.validierung import UngueltigerWert, pruefe_bic, pruefe_iban, pruefe_leitweg_id, pruefe_ust_id

KontaktTyp = Literal["kunde", "lieferant", "beide"]

_OPTIONALE_TEXTFELDER = (
    "strasse", "plz", "ort", "ust_id", "email", "kundennummer", "anrede", "vorname", "nachname", "telefon",
    "notiz", "steuernummer", "iban", "bic", "leitweg_id",
)
_PRUEFUNGEN = {"ust_id": pruefe_ust_id, "iban": pruefe_iban, "bic": pruefe_bic, "leitweg_id": pruefe_leitweg_id}


class _KontaktPruefung(BaseModel):
    """Leere Eingaben werden zu None, IBAN, BIC, USt-IdNr. und Leitweg-ID werden geprueft und
    normalisiert gespeichert. Nur fuer Eingaben, nie fuer Antworten (Altbestand bleibt lesbar)."""

    @field_validator(*_OPTIONALE_TEXTFELDER, mode="before", check_fields=False)
    @classmethod
    def _leer_ist_none(cls, wert):
        if isinstance(wert, str) and not wert.strip():
            return None
        return wert.strip() if isinstance(wert, str) else wert

    @field_validator(*_PRUEFUNGEN, mode="after", check_fields=False)
    @classmethod
    def _pruefe(cls, wert, info):
        if wert is None:
            return wert
        try:
            return _PRUEFUNGEN[info.field_name](wert)
        except UngueltigerWert as exc:
            raise PydanticCustomError("ungueltig", str(exc)) from exc

    @field_validator("land", mode="after", check_fields=False)
    @classmethod
    def _land_gross(cls, wert):
        return wert.upper() if isinstance(wert, str) else wert


class _KontaktFelder(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str = Field(default="DE", min_length=2, max_length=2)
    ust_id: str | None = None
    email: EmailStr | None = None
    ist_geschaeftskunde: bool = True
    kundennummer: str | None = Field(default=None, max_length=50)
    typ: KontaktTyp = "kunde"
    anrede: str | None = Field(default=None, max_length=30)
    vorname: str | None = Field(default=None, max_length=100)
    nachname: str | None = Field(default=None, max_length=100)
    telefon: str | None = Field(default=None, max_length=50)
    notiz: str | None = Field(default=None, max_length=2000)
    steuernummer: str | None = Field(default=None, max_length=30)
    iban: str | None = Field(default=None, max_length=42)
    bic: str | None = Field(default=None, max_length=11)
    zahlungsziel_tage: int | None = Field(default=None, ge=0, le=365)
    skonto_prozent: Decimal | None = Field(default=None, ge=0, le=100)
    skonto_tage: int | None = Field(default=None, ge=0, le=365)
    leitweg_id: str | None = Field(default=None, max_length=46)


class KontaktCreate(_KontaktPruefung, _KontaktFelder):
    pass


class KontaktResponse(_KontaktFelder):
    id: str
    archiviert: bool = False


class KontaktUpdate(_KontaktPruefung):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = Field(default=None, min_length=2, max_length=2)
    ust_id: str | None = None
    email: EmailStr | None = None
    ist_geschaeftskunde: bool | None = None
    kundennummer: str | None = Field(default=None, max_length=50)
    typ: KontaktTyp | None = None
    anrede: str | None = Field(default=None, max_length=30)
    vorname: str | None = Field(default=None, max_length=100)
    nachname: str | None = Field(default=None, max_length=100)
    telefon: str | None = Field(default=None, max_length=50)
    notiz: str | None = Field(default=None, max_length=2000)
    steuernummer: str | None = Field(default=None, max_length=30)
    iban: str | None = Field(default=None, max_length=42)
    bic: str | None = Field(default=None, max_length=11)
    zahlungsziel_tage: int | None = Field(default=None, ge=0, le=365)
    skonto_prozent: Decimal | None = Field(default=None, ge=0, le=100)
    skonto_tage: int | None = Field(default=None, ge=0, le=365)
    leitweg_id: str | None = Field(default=None, max_length=46)


# Pflichtfelder, die per PATCH nicht auf None gesetzt werden duerfen.
KONTAKT_PFLICHTFELDER = frozenset({"name", "land", "ist_geschaeftskunde", "typ"})


class InvoicePositionCreate(BaseModel):
    beschreibung: str = Field(min_length=1, max_length=500)
    menge: Decimal = Field(gt=0)
    einzelpreis: Decimal
    ust_satz: Decimal = Field(ge=0, le=100)
    kategorie: str | None = Field(default=None, max_length=100)
    artikelnummer: str | None = Field(default=None, max_length=50)


class InvoicePositionResponse(InvoicePositionCreate):
    id: str


class InvoiceCreate(BaseModel):
    kontakt_id: str
    leistungsdatum: date
    faelligkeitsdatum: date
    waehrung: str = Field(default="EUR", min_length=3, max_length=3)
    positionen: list[InvoicePositionCreate] = Field(min_length=1)
    betreff: str | None = Field(default=None, max_length=255)
    kopftext: str | None = Field(default=None, max_length=2000)
    fusstext: str | None = Field(default=None, max_length=2000)
    referenznummer: str | None = Field(default=None, max_length=100)
    kostenstelle: str | None = Field(default=None, max_length=100)
    zahlungsmethode: str | None = Field(default=None, max_length=50)
    skonto_tage: int | None = Field(default=None, ge=0)
    skonto_prozent: Decimal | None = Field(default=None, ge=0, le=100)
    interne_kontaktperson_user_id: str | None = None


class InvoiceResponse(BaseModel):
    id: str
    kontakt_id: str
    kontakt_name: str
    nummer: str | None
    status: str
    anzeige_status: str
    leistungsdatum: date
    faelligkeitsdatum: date
    waehrung: str
    netto_gesamt: Decimal
    ust_gesamt: Decimal
    brutto_gesamt: Decimal
    e_invoice_format: str | None
    korrigiert_invoice_id: str | None
    bezahlt_am: date | None
    positionen: list[InvoicePositionResponse]
    e_rechnung_hinweis: bool = False
    betreff: str | None
    kopftext: str | None
    fusstext: str | None
    referenznummer: str | None
    kostenstelle: str | None
    zahlungsmethode: str | None
    skonto_tage: int | None
    skonto_prozent: Decimal | None
    interne_kontaktperson_user_id: str | None
    versendet_am: str | None = None
    kontakt_email_vorhanden: bool = False


class PositionskategorieResponse(BaseModel):
    id: str
    name: str


class EInvoiceValidationError(BaseModel):
    fehlende_felder: list[str]


class BezahltMarkieren(BaseModel):
    bezahlt_am: date | None = None  # None -> heute


class VersendenRequest(BaseModel):
    """Body fuer POST .../versenden -- text ist optional, ohne ihn kommt ein fester
    deutscher Standardtext zum Einsatz (siehe routes.py)."""

    text: str | None = None
