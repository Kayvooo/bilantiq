"""BWA = Betriebswirtschaftliche Auswertung. Hier bewusst eine vereinfachte
Kategorien-Ergebnisrechnung, NICHT das amtliche DATEV-BWA-Kennzahlenschema
(Nr. 1-32 nach DATEV-Vorgabe) — das ist ein lizenziertes, exakt spezifiziertes
Format, das hier nicht nachgebaut wird, um keine falsche Vergleichbarkeit mit
einer echten Kanzlei-BWA vorzutaeuschen.

Rechnet auf denselben Konten wie compute_susa (app/reports/susa.py), also
garantiert dieselben Zahlen wie SuSa und der DATEV-Export: SKR03-Erloeskonten
(8xxx sowie explizit zugeordnete sonstige Ertraege) und Aufwandskonten (6xxx
sowie explizit zugeordnete Abschreibungen) werden nach Kategorie gruppiert.
Bestandskonten wie Bank (1200) oder Anlagen (0490) bleiben aussen vor.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.reports.susa import compute_susa

HINWEIS = (
    "Vereinfachte Kategorien-Auswertung, kein amtliches DATEV-BWA-Kennzahlenschema "
    "(Nr. 1-32). Basiert auf denselben Konten wie die Summen- und Saldenliste. "
    "Ersetzt keine Steuerberatung."
)

SONSTIGE_ERLOESKONTEN = {"2700"}
SONSTIGE_AUFWANDSKONTEN = {"4830"}


def compute_bwa(db: Session, *, mandant_id: str, jahr: int) -> dict:
    susa = compute_susa(db, mandant_id=mandant_id, jahr=jahr)

    erloes_posten = []
    kosten_posten = []
    erloese_gesamt = Decimal("0")
    kosten_gesamt = Decimal("0")

    for konto in susa["konten"]:
        nummer = konto["konto"]
        if nummer.startswith("8") or nummer in SONSTIGE_ERLOESKONTEN:
            betrag = -konto["saldo"]  # Erloeskonten sind haben-lastig, Saldo negativ
            erloes_posten.append({"konto": nummer, "bezeichnung": konto["bezeichnung"], "betrag": betrag})
            erloese_gesamt += betrag
        elif nummer.startswith("6") or nummer in SONSTIGE_AUFWANDSKONTEN:
            betrag = konto["saldo"]  # Aufwandskonten sind soll-lastig, Saldo positiv
            kosten_posten.append({"konto": nummer, "bezeichnung": konto["bezeichnung"], "betrag": betrag})
            kosten_gesamt += betrag
        # andere Konten (z.B. 1200 Bank) sind Bestandskonten, keine GuV-Position

    return {
        "jahr": jahr,
        "erloes_posten": erloes_posten,
        "kosten_posten": kosten_posten,
        "erloese_gesamt": erloese_gesamt,
        "kosten_gesamt": kosten_gesamt,
        "vorlaeufiges_ergebnis": erloese_gesamt - kosten_gesamt,
        "hinweis": HINWEIS,
    }
