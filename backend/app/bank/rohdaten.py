"""Gemeinsame Zwischenform fuer Umsaetze aus CAMT und CSV, vor dem Speichern."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


from app.core.tabelle import TabellenFehler

# Derselbe Fehlertyp wie beim gemeinsamen Tabellenleser, damit Meldungen aus
# app/core/tabelle.py beim Bankimport genauso beim Nutzer ankommen.
ImportFehler = TabellenFehler


@dataclass
class RohUmsatz:
    buchungsdatum: date
    betrag: Decimal  # mit Vorzeichen
    waehrung: str = "EUR"
    wertstellung: date | None = None
    gegenpartei_name: str | None = None
    gegenpartei_iban: str | None = None
    verwendungszweck: str = ""
    end_to_end_id: str | None = None


@dataclass
class RohAuszug:
    umsaetze: list[RohUmsatz]
    konto_iban: str | None = None
