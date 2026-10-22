from datetime import datetime

from pydantic import BaseModel


class FeldInfo(BaseModel):
    schluessel: str
    label: str
    pflicht: bool
    typ: str


class VorschauAntwort(BaseModel):
    format: str
    kodierung: str | None
    trennzeichen: str | None
    blatt: str | None
    blaetter: list[str]
    kopfzeilen: list[str]
    beispielzeilen: list[list[str]]
    anzahl_zeilen: int
    vorgeschlagene_zuordnung: dict[str, str]
    dezimal_vorschlag: str
    felder: list[FeldInfo]


class ZeileAntwort(BaseModel):
    nummer: int
    status: str
    anzeige: str
    grund: str | None
    fehler: list[str]
    hinweise: list[str]
    ergaenzt: list[str]


class PruefAntwort(BaseModel):
    ziel: str
    anzahl_zeilen: int
    neu: int
    ergaenzen: int
    vorhanden: int
    doppelt: int
    fehler: int
    mit_hinweisen: int
    # Alle auffaelligen Zeilen (nicht "neu" oder mit Hinweis), hoechstens 500.
    zeilen: list[ZeileAntwort]
    # Die ersten neuen Zeilen so, wie sie angelegt wuerden (Label -> Wert).
    beispiele: list[dict[str, str]]


class ImportAntwort(PruefAntwort):
    import_id: str


class ImportProtokoll(BaseModel):
    id: str
    ziel: str
    dateiname: str
    erstellt_am: datetime
    anzahl_neu: int
    anzahl_ergaenzt: int
    anzahl_uebersprungen: int
    anzahl_fehler: int
    rueckgaengig_am: datetime | None


class RueckgaengigAntwort(BaseModel):
    geloescht: int
    behalten: int
