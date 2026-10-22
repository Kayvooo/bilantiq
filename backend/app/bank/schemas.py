from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.bank.parser_csv import CsvProfil, CsvVorschau


class KontoCreate(BaseModel):
    bezeichnung: str = Field(min_length=1, max_length=100)
    iban: str | None = Field(default=None, max_length=40)


class KontoResponse(BaseModel):
    id: str
    bezeichnung: str
    iban: str | None
    csv_profil: CsvProfil | None
    anzahl_umsaetze: int


class ImportVorschau(BaseModel):
    format: Literal["camt", "csv"]
    anzahl: int
    zeitraum_von: date | None = None
    zeitraum_bis: date | None = None
    beispiele: list[dict[str, str]] = []
    csv: CsvVorschau | None = None
    gespeichertes_profil: CsvProfil | None = None


class ImportErgebnis(BaseModel):
    import_id: str
    format: Literal["camt", "csv"]
    neu: int
    doppelt: int
    zeitraum_von: date | None
    zeitraum_bis: date | None


class VorschlagResponse(BaseModel):
    typ: Literal["rechnung", "altrechnung", "beleg", "ausgabe"]
    ziel_id: str
    anzeige: str
    score: float
    sicher: bool
    gruende: list[str]


class UmsatzResponse(BaseModel):
    id: str
    bankkonto_id: str
    buchungsdatum: date
    wertstellung: date | None
    betrag: str
    gegenpartei_name: str | None
    gegenpartei_iban: str | None
    verwendungszweck: str
    status: Literal["offen", "zugeordnet", "ignoriert"]
    zuordnung_typ: Literal["rechnung", "altrechnung", "beleg", "ausgabe"] | None
    zuordnung_id: str | None
    ignoriert_grund: str | None
    beleg_fehlt: bool
    vorschlag: VorschlagResponse | None


class UmsatzListe(BaseModel):
    umsaetze: list[UmsatzResponse]
    gesamt: int


class Zusammenfassung(BaseModel):
    offen: int
    beleg_fehlt: int
    sichere_vorschlaege: int
    zugeordnet: int
    ignoriert: int


class ZuordnenRequest(BaseModel):
    typ: Literal["rechnung", "altrechnung", "beleg", "ausgabe"]
    ziel_id: str = Field(min_length=1, max_length=36)


class IgnorierenRequest(BaseModel):
    grund: str = Field(min_length=1, max_length=200)


class BestaetigenRequest(BaseModel):
    umsatz_ids: list[str] = Field(min_length=1, max_length=200)


class Uebersprungen(BaseModel):
    umsatz_id: str
    grund: str


class BestaetigenErgebnis(BaseModel):
    bestaetigt: int
    uebersprungen: list[Uebersprungen]
