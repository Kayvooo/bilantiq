"""Lineare Abschreibung (AfA) nach §7 EStG, monatsgenau im Anschaffungsjahr
(§7 Abs. 1 Satz 4 EStG) -- Berechnung, keine Rechtsberatung. Der GWG-Grenzwert
(§6 Abs. 2 EStG) ist eine Annahme zum jetzigen Stand, nicht rechtlich geprueft,
siehe Annahmen in der Spec. Keine amtlichen AfA-Tabellen hinterlegt: die
Nutzungsdauer kommt direkt vom Anlagegut (app/anlagen/models.py), nicht aus
einer Kategorie-Nachschlagetabelle."""
from datetime import date
from decimal import Decimal

GWG_GRENZE = Decimal("800.00")


def berechne_afa_plan(anschaffungsdatum: date, anschaffungskosten_netto: Decimal, nutzungsdauer_jahre: int) -> list[dict]:
    if anschaffungskosten_netto <= GWG_GRENZE:
        return [{"jahr": anschaffungsdatum.year, "afa_betrag": anschaffungskosten_netto, "restbuchwert_ende": Decimal("0.00")}]

    jahres_afa = (anschaffungskosten_netto / nutzungsdauer_jahre).quantize(Decimal("0.01"))
    monate_erstes_jahr = 12 - anschaffungsdatum.month + 1
    betrag = (jahres_afa * monate_erstes_jahr / 12).quantize(Decimal("0.01"))

    plan = []
    restwert = anschaffungskosten_netto
    jahr = anschaffungsdatum.year
    while restwert > 0:
        betrag = min(betrag, restwert)
        restwert -= betrag
        plan.append({"jahr": jahr, "afa_betrag": betrag, "restbuchwert_ende": restwert})
        jahr += 1
        betrag = jahres_afa
    return plan


def afa_fuer_jahr(plan: list[dict], jahr: int) -> Decimal:
    for eintrag in plan:
        if eintrag["jahr"] == jahr:
            return eintrag["afa_betrag"]
    return Decimal("0.00")
