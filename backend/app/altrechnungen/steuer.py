"""Steueranteile einer Altrechnung bestimmen und Zahlungen darauf verteilen.

Die Altrechnung wird nicht neu berechnet: Die Betraege kommen aus der Datei und werden nur auf
Stimmigkeit geprueft. Wo der Steuersatz nicht eindeutig ist (gemischte Saetze), wird die Zeile
abgelehnt statt zu raten. Bei Ist-Versteuerung zaehlt die Umsatzsteuer in dem Zeitraum, in dem
bezahlt wurde, und nur anteilig nach dem gezahlten Betrag (siehe `verteile_zahlung`)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
# Zum Ableiten des Satzes aus Netto und Brutto: erst die heutigen Saetze, dann die befristeten von 2020.
ABLEITBARE_SAETZE = (Decimal("19"), Decimal("7"), Decimal("0"), Decimal("16"), Decimal("5"))
# Angegebene Saetze: auch 16 % und 5 % (Juli bis Dezember 2020) sind in einem Archiv glaubwuerdig.
ERLAUBTE_SAETZE = frozenset(ABLEITBARE_SAETZE)
TOLERANZ = Decimal("0.01")


class SteuerFehler(ValueError):
    """Meldung fuer den Nutzer."""


@dataclass(frozen=True)
class Anteil:
    satz: Decimal
    netto: Decimal
    ust: Decimal

    @property
    def brutto(self) -> Decimal:
        return self.netto + self.ust


def _cent(wert: Decimal) -> Decimal:
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


def _gleich(a: Decimal, b: Decimal, toleranz: Decimal = TOLERANZ) -> bool:
    return abs(a - b) <= toleranz


def _satz(wert: Decimal) -> Decimal:
    return wert.quantize(CENT)


def _aus_netto(netto: Decimal, satz: Decimal) -> Anteil:
    return Anteil(_satz(satz), _cent(netto), _cent(netto * satz / 100))


def bestimme_anteile(
    *, netto: Decimal | None, ust: Decimal | None, brutto: Decimal | None, satz: Decimal | None,
    netto_je_satz: dict[Decimal, Decimal],
) -> tuple[Decimal, list[Anteil]]:
    """Gibt (Brutto gesamt, Anteile je Steuersatz) zurueck."""
    # 1. Netto je Steuersatz ist die genaueste Angabe.
    if netto_je_satz:
        anteile = [_aus_netto(n, s) for s, n in sorted(netto_je_satz.items(), reverse=True) if n != 0]
        if not anteile:
            raise SteuerFehler("Alle Netto-Beträge je Steuersatz sind 0.")
        summe = sum((a.brutto for a in anteile), Decimal("0"))
        if brutto is not None and not _gleich(summe, brutto, TOLERANZ * len(anteile)):
            raise SteuerFehler(
                f"Die Netto-Beträge je Steuersatz ergeben {summe:.2f} € brutto, in der Datei steht {brutto:.2f} €."
            )
        return (brutto if brutto is not None else summe), _auf_brutto(anteile, brutto)

    # 2. Ein angegebener Steuersatz.
    if satz is not None:
        if satz.normalize() not in ERLAUBTE_SAETZE:
            raise SteuerFehler(f"USt-Satz {satz.normalize()} % ist kein deutscher Steuersatz (19, 7, 0, 16 oder 5 %).")
        if netto is not None:
            anteil = _aus_netto(netto, satz)
        elif brutto is not None:
            anteil = _aus_netto(brutto / (1 + satz / 100), satz)
        else:
            raise SteuerFehler("Betrag fehlt: Bitte Brutto oder Netto zuordnen.")
        if brutto is not None and not _gleich(anteil.brutto, brutto):
            raise SteuerFehler(
                f"Der Steuersatz {satz.normalize()} % passt nicht zu den Beträgen "
                f"(Netto {anteil.netto:.2f} € ergibt {anteil.brutto:.2f} €, in der Datei steht {brutto:.2f} €)."
            )
        return (brutto if brutto is not None else anteil.brutto), _auf_brutto([anteil], brutto)

    # 3. Netto und Brutto (oder USt) bekannt: Steuersatz ableiten, nur deutsche Saetze.
    if netto is None and brutto is not None and ust is not None:
        netto = brutto - ust
    if brutto is None and netto is not None and ust is not None:
        brutto = netto + ust
    if netto is not None and brutto is not None:
        if netto <= 0:
            raise SteuerFehler("Nettobetrag muss größer als 0 sein.")
        for kandidat in ABLEITBARE_SAETZE:
            anteil = _aus_netto(netto, kandidat)
            if _gleich(anteil.brutto, brutto) and (ust is None or _gleich(anteil.ust, ust)):
                return brutto, _auf_brutto([anteil], brutto)
        raise SteuerFehler(
            "Der Steuersatz lässt sich nicht eindeutig bestimmen (gemischte Steuersätze?). Bitte den Steuersatz "
            "oder das Netto je Steuersatz (19 %, 7 %, 0 %) zuordnen."
        )
    raise SteuerFehler("Betrag fehlt: Bitte Brutto oder Netto mit USt zuordnen.")


def _auf_brutto(anteile: list[Anteil], brutto: Decimal | None) -> list[Anteil]:
    """Gleicht Rundungsdifferenzen (hoechstens wenige Cent) im groessten Anteil an die Summe aus
    der Datei an, damit die Teile immer genau den Bruttobetrag ergeben."""
    if brutto is None:
        return anteile
    differenz = brutto - sum((a.brutto for a in anteile), Decimal("0"))
    if differenz == 0:
        return anteile
    index = max(range(len(anteile)), key=lambda i: anteile[i].brutto)
    groesster = anteile[index]
    korrigiert = Anteil(groesster.satz, groesster.netto, groesster.ust + differenz)
    return [korrigiert if i == index else a for i, a in enumerate(anteile)]


def verteile_zahlung(anteile: list[Anteil], betrag: Decimal) -> list[Anteil]:
    """Verteilt eine Zahlung im Verhaeltnis der Bruttoanteile auf die Steuersaetze. Netto und USt
    entstehen aus dem gezahlten Betrag, so dass auch Teilzahlungen und Skonto stimmen."""
    gesamt = sum((a.brutto for a in anteile), Decimal("0"))
    if gesamt <= 0 or betrag <= 0:
        return []
    ergebnis: list[Anteil] = []
    verteilt = Decimal("0")
    for i, anteil in enumerate(anteile):
        teil = betrag - verteilt if i == len(anteile) - 1 else _cent(betrag * anteil.brutto / gesamt)
        verteilt += teil
        netto = _cent(teil * anteil.netto / anteil.brutto) if anteil.brutto else Decimal("0.00")
        ergebnis.append(Anteil(anteil.satz, netto, teil - netto))
    return ergebnis


def anteile_als_json(anteile: list[Anteil]) -> str:
    return json.dumps([{"satz": str(a.satz), "netto": str(a.netto), "ust": str(a.ust)} for a in anteile])


def anteile_aus_json(text: str) -> list[Anteil]:
    return [Anteil(Decimal(e["satz"]), Decimal(e["netto"]), Decimal(e["ust"])) for e in json.loads(text)]
