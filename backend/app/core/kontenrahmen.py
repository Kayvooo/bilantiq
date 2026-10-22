"""SKR03 account mapping — deliberately a small static table, not a user-editable
chart of accounts (that is real scope, not this feature). Picked SKR03 because it is
the more common default for small businesses/freelancers in Germany; a business on
SKR04 would need different numbers. Confirm with a Steuerberater before relying on
this for real filings — see Annahmen in the Spec.
"""
from decimal import Decimal

# Ausgaben-Kategorie (from app/receipts/ai_extraction.py's CATEGORIES) -> SKR03-Konto.
AUSGABEN_KONTEN: dict[str, str] = {
    "Buerobedarf": "6815",
    "Reisekosten": "6663",
    "Bewirtung": "6644",  # only 70% deductible under §4 Abs. 5 EStG — not computed here, flagged for the Steuerberater
    "Software/IT": "6835",
    "Marketing": "6600",
    "Miete": "6310",
    "Telekommunikation": "6805",
    "Sonstiges": "6800",
}
AUSGABEN_KONTO_STANDARD = "6800"


def ausgaben_konto(kategorie: str | None) -> str:
    if kategorie is None:
        return AUSGABEN_KONTO_STANDARD
    return AUSGABEN_KONTEN.get(kategorie, AUSGABEN_KONTO_STANDARD)


def erloes_konto(ust_satz: Decimal) -> str:
    """Revenue account by VAT rate — objective, not a suggestion the user can be
    wrong about, so this is never stored, only computed (see app/reports/datev.py
    once that spec lands)."""
    if ust_satz == Decimal("19.00") or ust_satz == Decimal("19"):
        return "8400"
    if ust_satz == Decimal("7.00") or ust_satz == Decimal("7"):
        return "8300"
    return "8120"  # umsatzsteuerfrei / 0%


# Anzeigenamen fuer die Summen-/Saldenliste (app/reports/susa.py) — SKR03-Bezeichnungen,
# nicht vollstaendig, deckt nur die Konten ab, die dieses System selbst bebucht.
KONTO_LABEL: dict[str, str] = {
    # AfA-Konten sind Annahmen aus der Feature-Spec, nicht mit einem Steuerberater abgeglichen.
    "0490": "Sonstige Betriebs- und Geschaeftsausstattung",
    "1200": "Bank",
    # Annahme aus der Feature-Spec, nicht mit einem Steuerberater abgeglichen.
    "2700": "Sonstige betriebliche Ertraege",
    "4830": "Abschreibungen auf Sachanlagen",
    "8400": "Erloese 19% USt",
    "8300": "Erloese 7% USt",
    "8120": "Erloese steuerfrei/0%",
    "6815": "Buerobedarf",
    "6663": "Reisekosten",
    "6644": "Bewirtungskosten",
    "6835": "Software/IT-Kosten",
    "6600": "Werbekosten",
    "6310": "Miete",
    "6805": "Telefon",
    "6800": "Sonstiger betrieblicher Aufwand",
}


def konto_label(konto: str) -> str:
    return KONTO_LABEL.get(konto, "Unbekanntes Konto")
