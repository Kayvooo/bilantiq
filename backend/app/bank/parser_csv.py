"""CSV-Kontoauszuege lesen.

CSV-Exporte unterscheiden sich von Bank zu Bank (Kodierung, Trennzeichen, Spaltennamen,
Datums- und Zahlenformat). Deshalb gibt es kein festes Format, sondern ein Spaltenprofil,
das der Nutzer bei Bedarf anpasst und das je Bankkonto gemerkt wird. Vorschlaege fuer das
Profil sind Heuristiken, nichts wird still angenommen."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.bank.rohdaten import ImportFehler, RohAuszug, RohUmsatz
from app.core.tabelle import (
    dekodiere,
    erkenne_trennzeichen,
    parse_betrag as _parse_betrag,
    parse_datum as _parse_datum,
    schlage_datumsformat_vor as _schlage_datumsformat_vor,
    schlage_dezimal_vor as _schlage_dezimal_vor,
    zeilen_aus_text,
)

MAX_FEHLER_IN_MELDUNG = 5


def _zeilen(text: str, trennzeichen: str) -> tuple[list[str], list[list[str]]]:
    return zeilen_aus_text(text, trennzeichen, leer_meldung="Die CSV-Datei enthält keine Umsatzzeilen.")


class CsvProfil(BaseModel):
    datum: str
    datum_format: str = "%d.%m.%Y"
    dezimal: Literal["komma", "punkt"] = "komma"
    betrag: str | None = None
    soll: str | None = None
    haben: str | None = None
    name: str | None = None
    iban: str | None = None
    verwendungszweck: list[str] = Field(default_factory=list)
    wertstellung: str | None = None
    waehrung: str | None = None
    trennzeichen: str | None = None
    kodierung: str | None = None


class CsvVorschau(BaseModel):
    kopfzeilen: list[str]
    beispielzeilen: list[list[str]]
    anzahl_zeilen: int
    trennzeichen: str
    kodierung: str
    vorgeschlagenes_profil: CsvProfil | None


_HINWEISE = {
    "datum": ("buchungstag", "buchungsdatum", "booking date", "completed date", "datum", "date", "valuta"),
    "wertstellung": ("wertstellung", "valuta", "value date", "started date"),
    "betrag": ("betrag", "amount", "umsatz"),
    "soll": ("soll", "debit", "belastung"),
    "haben": ("haben", "credit", "gutschrift"),
    "name": ("beguenstigter", "begünstigter", "auftraggeber", "zahlungspflichtiger", "empfänger", "empfaenger",
             "counterparty", "name", "description", "beschreibung"),
    "iban": ("iban", "kontonummer"),
    "verwendungszweck": ("verwendungszweck", "buchungstext", "reference", "purpose", "description", "beschreibung"),
    "waehrung": ("währung", "waehrung", "currency"),
}


def _spalte(kopf: list[str], schluessel: str, ausgeschlossen: set[str] = frozenset()) -> str | None:
    kleine = [(spalte, spalte.casefold()) for spalte in kopf if spalte not in ausgeschlossen]
    for hinweis in _HINWEISE[schluessel]:
        for spalte, klein in kleine:
            if klein == hinweis or hinweis in klein:
                return spalte
    return None


def schlage_profil_vor(kopf: list[str], zeilen: list[list[str]]) -> CsvProfil | None:
    datum = _spalte(kopf, "datum")
    if datum is None:
        return None
    betrag = _spalte(kopf, "betrag")
    soll = _spalte(kopf, "soll") if betrag is None else None
    haben = _spalte(kopf, "haben") if betrag is None else None
    if betrag is None and (soll is None or haben is None):
        return None

    spalten_index = {name: index for index, name in enumerate(kopf)}

    def beispiele(spalte: str | None) -> list[str]:
        if spalte is None:
            return []
        return [zeile[spalten_index[spalte]] for zeile in zeilen[:20] if len(zeile) > spalten_index[spalte]]

    wertstellung = _spalte(kopf, "wertstellung", {datum})
    name = _spalte(kopf, "name")
    zweck = _spalte(kopf, "verwendungszweck")
    geldspalte = betrag or haben
    return CsvProfil(
        datum=datum,
        datum_format=_schlage_datumsformat_vor(beispiele(datum)),
        dezimal=_schlage_dezimal_vor(beispiele(geldspalte)),
        betrag=betrag, soll=soll, haben=haben,
        name=name, iban=_spalte(kopf, "iban"),
        verwendungszweck=[zweck] if zweck else [],
        wertstellung=wertstellung, waehrung=_spalte(kopf, "waehrung"),
    )


def vorschau_csv(daten: bytes) -> CsvVorschau:
    text, kodierung = dekodiere(daten)
    trennzeichen = erkenne_trennzeichen(text)
    kopf, zeilen = _zeilen(text, trennzeichen)
    return CsvVorschau(
        kopfzeilen=kopf,
        beispielzeilen=zeilen[:5],
        anzahl_zeilen=len(zeilen),
        trennzeichen=trennzeichen,
        kodierung=kodierung,
        vorgeschlagenes_profil=schlage_profil_vor(kopf, zeilen),
    )


def lese_csv(daten: bytes, profil: CsvProfil) -> RohAuszug:
    text, _ = dekodiere(daten, profil.kodierung)
    kopf, zeilen = _zeilen(text, profil.trennzeichen or erkenne_trennzeichen(text))
    index = {name: nummer for nummer, name in enumerate(kopf)}

    benoetigt = [profil.datum, profil.betrag, profil.soll, profil.haben, profil.name, profil.iban,
                 profil.wertstellung, profil.waehrung, *profil.verwendungszweck]
    fehlend = [name for name in benoetigt if name and name not in index]
    if fehlend:
        raise ImportFehler(f"Diese Spalten gibt es in der Datei nicht: {', '.join(fehlend)}.")
    if profil.betrag is None and not (profil.soll and profil.haben):
        raise ImportFehler("Bitte eine Betragsspalte oder je eine Soll- und Haben-Spalte angeben.")

    def zelle(zeile: list[str], spalte: str | None) -> str:
        if spalte is None or index[spalte] >= len(zeile):
            return ""
        return zeile[index[spalte]]

    umsaetze: list[RohUmsatz] = []
    probleme: list[str] = []
    for nummer, zeile in enumerate(zeilen, start=2):
        buchung = _parse_datum(zelle(zeile, profil.datum), profil.datum_format)
        if profil.betrag is not None:
            betrag = _parse_betrag(zelle(zeile, profil.betrag), profil.dezimal)
        else:
            soll = _parse_betrag(zelle(zeile, profil.soll), profil.dezimal)
            haben = _parse_betrag(zelle(zeile, profil.haben), profil.dezimal)
            betrag = (haben or Decimal("0")) - abs(soll or Decimal("0")) if (soll or haben) else None
        waehrung = (zelle(zeile, profil.waehrung) or "EUR").upper()

        if buchung is None:
            probleme.append(f"Zeile {nummer}: Datum '{zelle(zeile, profil.datum)}' passt nicht zum Format {profil.datum_format}.")
        elif betrag is None or betrag == 0:
            probleme.append(f"Zeile {nummer}: Kein lesbarer Betrag.")
        elif waehrung != "EUR":
            probleme.append(f"Zeile {nummer}: Währung {waehrung}, es werden nur Euro-Umsätze unterstützt.")
        else:
            zweck = " ".join(wert for wert in (zelle(zeile, spalte) for spalte in profil.verwendungszweck) if wert)
            umsaetze.append(
                RohUmsatz(
                    buchungsdatum=buchung,
                    wertstellung=_parse_datum(zelle(zeile, profil.wertstellung), profil.datum_format) if profil.wertstellung else None,
                    betrag=betrag,
                    waehrung=waehrung,
                    gegenpartei_name=zelle(zeile, profil.name) or None,
                    gegenpartei_iban=zelle(zeile, profil.iban).replace(" ", "") or None,
                    verwendungszweck=zweck,
                )
            )
    if probleme:
        mehr = f" (und {len(probleme) - MAX_FEHLER_IN_MELDUNG} weitere)" if len(probleme) > MAX_FEHLER_IN_MELDUNG else ""
        raise ImportFehler("Der Import wurde nicht durchgeführt. " + " ".join(probleme[:MAX_FEHLER_IN_MELDUNG]) + mehr)
    return RohAuszug(umsaetze=umsaetze)
