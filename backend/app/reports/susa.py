"""SuSa = Summen- und Saldenliste: pro SKR03-Konto die Summe aller Soll- und
Haben-Buchungen eines Jahres sowie der resultierende Saldo — die uebliche erste
Auswertung, die eine Steuerkanzlei anfordert.

Rechnet auf denselben Buchungszeilen wie der DATEV-Export (app/reports/datev.py,
sammle_buchungszeilen), damit beide Auswertungen niemals auseinanderlaufen. Jede
Buchungszeile ist eine doppelte Buchung: die Soll/Haben-Seite von `konto`, die
jeweils andere Seite von `gegenkonto`, mit demselben Betrag — die Grundannahme
jeder doppelten Buchfuehrung, hier nicht gesondert getestet, weil sie direkt aus
Buchungszeile.soll_haben folgt.

Wie EUER/UStVA: rechnet Zahlen, ersetzt keine Steuerberatung.
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.kontenrahmen import konto_label
from app.reports.datev import sammle_buchungszeilen

HINWEIS = (
    "Basiert auf denselben Buchungen wie der DATEV-Export (bezahlte Rechnungen, "
    "sonstige Einnahmen, gebuchte Ausgaben und AfA). Kein vollstaendiger Kontenrahmen, "
    "nur die von Bilantiq selbst bebuchten Konten. Ersetzt keine Steuerberatung."
)


@dataclass
class _Bewegung:
    soll: Decimal
    haben: Decimal


def compute_susa(db: Session, *, mandant_id: str, jahr: int) -> dict:
    zeilen = sammle_buchungszeilen(db, mandant_id=mandant_id, jahr=jahr)

    bewegungen: dict[str, _Bewegung] = {}

    def _buchen(konto: str, seite: str, betrag: Decimal) -> None:
        eintrag = bewegungen.setdefault(konto, _Bewegung(Decimal("0"), Decimal("0")))
        if seite == "S":
            eintrag.soll += betrag
        else:
            eintrag.haben += betrag

    for zeile in zeilen:
        gegenseite = "H" if zeile.soll_haben == "S" else "S"
        _buchen(zeile.konto, zeile.soll_haben, zeile.umsatz)
        _buchen(zeile.gegenkonto, gegenseite, zeile.umsatz)

    konten = []
    summe_soll = Decimal("0")
    summe_haben = Decimal("0")
    for konto in sorted(bewegungen):
        bewegung = bewegungen[konto]
        summe_soll += bewegung.soll
        summe_haben += bewegung.haben
        konten.append({
            "konto": konto,
            "bezeichnung": konto_label(konto),
            "soll": bewegung.soll,
            "haben": bewegung.haben,
            "saldo": bewegung.soll - bewegung.haben,
        })

    return {
        "jahr": jahr,
        "konten": konten,
        "summe_soll": summe_soll,
        "summe_haben": summe_haben,
        "hinweis": HINWEIS,
    }
