from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class MitarbeiterCreate(BaseModel):
    personalnummer: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9._-]+$")
    vorname: str = Field(min_length=1, max_length=100)
    nachname: str = Field(min_length=1, max_length=100)
    eintrittsdatum: date
    austrittsdatum: date | None = None
    monatsbrutto: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

    @field_validator("personalnummer", "vorname", "nachname")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_dates(self):
        if self.austrittsdatum is not None and self.austrittsdatum < self.eintrittsdatum:
            raise ValueError("Austrittsdatum darf nicht vor dem Eintrittsdatum liegen.")
        return self


class MitarbeiterUpdate(BaseModel):
    vorname: str | None = Field(default=None, min_length=1, max_length=100)
    nachname: str | None = Field(default=None, min_length=1, max_length=100)
    eintrittsdatum: date | None = None
    austrittsdatum: date | None = None
    monatsbrutto: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @field_validator("vorname", "nachname")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class MitarbeiterResponse(BaseModel):
    id: str
    personalnummer: str
    vorname: str
    nachname: str
    eintrittsdatum: date
    austrittsdatum: date | None
    monatsbrutto: Decimal
    aktiv: bool


class LohnMonatsentwurfCreate(BaseModel):
    mitarbeiter_id: str
    jahr: int = Field(ge=2020, le=2100)
    monat: int = Field(ge=1, le=12)
    grundbrutto: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    steuerpflichtige_zuschlaege: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    steuerfreie_erstattungen: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    sonstige_abzuege: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class LohnMonatsentwurfUpdate(BaseModel):
    """Nur erlaubt, solange der Entwurf im Status 'vorbereitung' ist -- siehe
    Korrektur-Endpunkte in routes.py fuer den Weg zurueck aus 'abgeschlossen'."""

    grundbrutto: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    steuerpflichtige_zuschlaege: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    steuerfreie_erstattungen: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sonstige_abzuege: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class LohnMonatsentwurfResponse(BaseModel):
    id: str
    mitarbeiter_id: str
    personalnummer: str
    mitarbeiter_name: str
    jahr: int
    monat: int
    grundbrutto: Decimal
    steuerpflichtige_zuschlaege: Decimal
    steuerfreie_erstattungen: Decimal
    sonstige_abzuege: Decimal
    gesamtbrutto: Decimal
    zwischenbetrag_vor_abgaben: Decimal
    status: str  # "vorbereitung" oder "abgeschlossen" -- interner Bearbeitungsstatus der Vorbereitung
    abgeschlossen_am: datetime | None = None
    # Bleibt bewusst dauerhaft False bis BMF-PAP/ELSTER/ITSG abgeschlossen sind (siehe CLAUDE.md):
    # "abgeschlossen" oben ist nur "an die Steuerkanzlei uebergeben", keine rechtsverbindliche Lohnabrechnung.
    verbindlicher_abschluss_verfuegbar: bool = False
    hinweis: str
