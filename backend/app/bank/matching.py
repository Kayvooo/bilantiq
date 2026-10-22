"""Zuordnungsvorschlaege fuer Bankumsaetze: reine Funktionen ohne Datenbankzugriff.

Der Vorschlag ist eine Heuristik und wird nie automatisch ausgefuehrt. "Sicher" heisst nur:
Betrag und Rechnungsnummer passen beide, dann kann der Nutzer gesammelt bestaetigen.
Jeder Vorschlag nennt seine Gruende im Klartext."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from app.receipts.lernen import normalisiere_anbieter

DATUMS_TOLERANZ_TAGE = 5
BETRAGS_TOLERANZ = Decimal("0.005")
NAMENS_SCHWELLE = 0.85


@dataclass(frozen=True)
class Umsatz:
    id: str
    buchungsdatum: date
    betrag: Decimal  # mit Vorzeichen
    gegenpartei: str | None
    verwendungszweck: str
    # Kontakte, deren hinterlegte IBAN der IBAN der Gegenpartei entspricht.
    iban_kontakt_ids: frozenset[str] = frozenset()
    iban_lieferanten: tuple[str, ...] = ()


@dataclass(frozen=True)
class RechnungKandidat:
    id: str
    nummer: str
    brutto: Decimal
    kunde: str
    faelligkeit: date
    kontakt_id: str | None = None
    # "rechnung" (aus Bilantiq) oder "altrechnung" (aus dem Altsystem, brutto ist dann der Restbetrag)
    typ: str = "rechnung"


@dataclass(frozen=True)
class BelegKandidat:
    id: str
    typ: str  # beleg (noch nicht gebucht) | ausgabe (gebucht, noch ohne Zahlung verknuepft)
    betrag: Decimal | None
    anbieter: str | None
    datum: date | None
    zahlungsdatum: date | None


@dataclass
class Vorschlag:
    typ: str  # rechnung | altrechnung | beleg | ausgabe
    ziel_id: str
    anzeige: str
    score: float
    sicher: bool
    gruende: list[str] = field(default_factory=list)


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _namens_aehnlichkeit(a: str | None, b: str | None) -> float:
    schluessel_a, schluessel_b = normalisiere_anbieter(a), normalisiere_anbieter(b)
    if not schluessel_a or not schluessel_b:
        return 0.0
    kurz, lang = sorted((schluessel_a, schluessel_b), key=len)
    if len(kurz) >= 5 and re.search(rf"(?<!\w){re.escape(kurz)}(?!\w)", lang):
        return 0.9
    return SequenceMatcher(None, schluessel_a, schluessel_b).ratio()


def _betrag_gleich(a: Decimal, b: Decimal) -> bool:
    return abs(abs(a) - abs(b)) < BETRAGS_TOLERANZ


def _datum_nah(a: date | None, b: date | None) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= DATUMS_TOLERANZ_TAGE


def vorschlag_fuer_eingang(umsatz: Umsatz, rechnungen: list[RechnungKandidat]) -> Vorschlag | None:
    """Ein Eingang gehoert vermutlich zu einer offenen Rechnung."""
    zweck = _alnum(umsatz.verwendungszweck)
    kandidaten: list[Vorschlag] = []
    for rechnung in rechnungen:
        betrag_passt = _betrag_gleich(umsatz.betrag, rechnung.brutto)
        nummer = _alnum(rechnung.nummer)
        nummer_passt = len(nummer) >= 5 and nummer in zweck
        name = _namens_aehnlichkeit(umsatz.gegenpartei, rechnung.kunde)
        iban_passt = rechnung.kontakt_id is not None and rechnung.kontakt_id in umsatz.iban_kontakt_ids

        if not (nummer_passt or (betrag_passt and (name >= 0.6 or iban_passt))):
            continue
        score = (
            0.5 * betrag_passt + 0.45 * nummer_passt
            + (0.15 if name >= NAMENS_SCHWELLE else 0.07 if name >= 0.6 else 0.0)
            + 0.15 * iban_passt
        )
        gruende = []
        if nummer_passt:
            gruende.append(f"Rechnungsnummer {rechnung.nummer} steht im Verwendungszweck")
        if betrag_passt:
            gruende.append("Betrag stimmt überein")
        elif nummer_passt:
            gruende.append(f"Betrag weicht ab (Rechnung {rechnung.brutto:.2f}, Zahlung {umsatz.betrag:.2f})")
        if name >= 0.6:
            gruende.append(f"Name der Gegenpartei passt zu {rechnung.kunde}")
        if iban_passt:
            gruende.append(f"IBAN bekannt (Kontakt {rechnung.kunde})")
        kandidaten.append(
            Vorschlag(
                typ=rechnung.typ, ziel_id=rechnung.id, anzeige=f"{rechnung.nummer}, {rechnung.kunde}",
                score=round(min(score, 1.0), 2), sicher=betrag_passt and nummer_passt, gruende=gruende,
            )
        )
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda v: (-v.score, next(r.faelligkeit for r in rechnungen if r.id == v.ziel_id)))
    bester = kandidaten[0]
    gleich_gute = [v for v in kandidaten if v.score == bester.score]
    if len(gleich_gute) > 1:
        # Mehrere gleich passende offene Rechnungen: nichts ist sicher, die aelteste wird vorgeschlagen.
        bester.sicher = False
        bester.gruende.append(f"{len(gleich_gute)} offene Rechnungen passen gleich gut, die älteste wird vorgeschlagen")
    return bester


def vorschlag_fuer_ausgang(umsatz: Umsatz, belege: list[BelegKandidat]) -> Vorschlag | None:
    """Ein Ausgang gehoert vermutlich zu einem Beleg oder einer bereits gebuchten Ausgabe."""
    kandidaten: list[Vorschlag] = []
    for beleg in belege:
        if beleg.betrag is None or not _betrag_gleich(umsatz.betrag, beleg.betrag):
            continue
        name = _namens_aehnlichkeit(umsatz.gegenpartei, beleg.anbieter)
        lieferant = max(umsatz.iban_lieferanten, key=lambda n: _namens_aehnlichkeit(n, beleg.anbieter), default=None)
        lieferant_name = _namens_aehnlichkeit(lieferant, beleg.anbieter) if lieferant else 0.0
        iban_passt = lieferant_name >= 0.6
        name = max(name, lieferant_name)
        nah = _datum_nah(umsatz.buchungsdatum, beleg.zahlungsdatum or beleg.datum)
        if name < 0.6 and not nah:
            continue
        score = 0.4 + 0.35 * (name >= NAMENS_SCHWELLE) + 0.1 * (0.6 <= name < NAMENS_SCHWELLE) + 0.25 * nah
        gruende = ["Betrag stimmt überein"]
        if iban_passt:
            gruende.append(f"IBAN gehört zu Lieferant {lieferant}")
        elif name >= 0.6:
            gruende.append(f"Name der Gegenpartei passt zu {beleg.anbieter}")
        if nah:
            gruende.append(f"Datum liegt höchstens {DATUMS_TOLERANZ_TAGE} Tage auseinander")
        kandidaten.append(
            Vorschlag(
                typ=beleg.typ, ziel_id=beleg.id, anzeige=beleg.anbieter or "Beleg ohne Anbieter",
                score=round(min(score, 1.0), 2), sicher=False, gruende=gruende,
            )
        )
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda v: -v.score)
    return kandidaten[0]
