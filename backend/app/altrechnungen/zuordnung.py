"""Ordnet hochgeladene PDFs ueber die Rechnungsnummer im Dateinamen einer Altrechnung zu.

Eindeutig ist ein Treffer nur, wenn genau eine Rechnungsnummer (die laengste passende) im Namen
steht und nicht von weiteren Ziffern oder Buchstaben umgeben ist: "RE-2024-1" steckt nicht in
"RE-2024-10". Kurze Nummern (unter 4 Zeichen) zaehlen nur, wenn sie den ganzen Namen bilden.
Alles andere wird dem Nutzer zur Hand-Zuordnung gezeigt, nie geraten."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MIN_ZEICHEN_FUER_TEILTREFFER = 4


@dataclass(frozen=True)
class Kandidat:
    id: str
    nummer: str


def _zeichen(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


class Zuordner:
    def __init__(self, kandidaten: list[Kandidat]):
        self._eintraege: list[tuple[Kandidat, str, re.Pattern[str] | None]] = []
        for kandidat in kandidaten:
            zeichen = _zeichen(kandidat.nummer)
            if not zeichen:
                continue
            muster = None
            if len(zeichen) >= MIN_ZEICHEN_FUER_TEILTREFFER:
                # Zwischen den Zeichen duerfen beliebige Trennzeichen stehen ("RE 2024 0001").
                muster = re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]*".join(map(re.escape, zeichen)) + r"(?![a-z0-9])")
            self._eintraege.append((kandidat, zeichen, muster))

    def finde(self, dateiname: str) -> tuple[Literal["eindeutig", "unklar", "keine"], list[Kandidat]]:
        stamm = re.sub(r"\.pdf$", "", dateiname.strip(), flags=re.IGNORECASE).casefold()
        stamm_zeichen = _zeichen(stamm)
        treffer: list[tuple[int, Kandidat]] = []
        for kandidat, zeichen, muster in self._eintraege:
            if muster is None:
                if stamm_zeichen == zeichen:
                    treffer.append((len(zeichen), kandidat))
            elif muster.search(stamm):
                treffer.append((len(zeichen), kandidat))
        if not treffer:
            return "keine", []
        laengste = max(laenge for laenge, _ in treffer)
        beste = [kandidat for laenge, kandidat in treffer if laenge == laengste]
        return ("eindeutig" if len(beste) == 1 else "unklar"), beste
