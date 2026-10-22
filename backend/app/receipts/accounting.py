"""Gemeinsame, deterministische Berechnung fuer Ausgaben mit einem oder mehreren USt-Saetzen."""
from decimal import Decimal

from app.receipts.models import Ausgabe

CENT = Decimal("0.01")
SUPPORTED_VAT_RATES = {Decimal("0"), Decimal("7"), Decimal("19")}


def steueraufteilung(ausgabe: Ausgabe) -> list[tuple[Decimal, Decimal]]:
    """Liefert (USt-Satz, Bruttobetrag). Legacy-Zeilen ohne Kinddatensaetze bleiben lesbar."""
    if ausgabe.steueranteile:
        return [(anteil.ust_satz, anteil.bruttobetrag) for anteil in ausgabe.steueranteile]
    if ausgabe.ust_satz is None:
        return []
    return [(ausgabe.ust_satz, ausgabe.betrag)]


def netto_und_steuer(brutto: Decimal, ust_satz: Decimal) -> tuple[Decimal, Decimal]:
    netto = (brutto / (Decimal("1") + ust_satz / Decimal("100"))).quantize(CENT)
    return netto, (brutto - netto).quantize(CENT)


def ausgabe_netto(ausgabe: Ausgabe) -> Decimal:
    return sum((netto_und_steuer(brutto, satz)[0] for satz, brutto in steueraufteilung(ausgabe)), Decimal("0"))


def ausgabe_vorsteuer(ausgabe: Ausgabe) -> Decimal:
    return sum((netto_und_steuer(brutto, satz)[1] for satz, brutto in steueraufteilung(ausgabe)), Decimal("0"))
