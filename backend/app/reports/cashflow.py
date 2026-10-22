"""Cashflow-Prognose — deliberately not AI-generated.

Forecasting a number the model just makes up is exactly what "keine erfundenen Zahlen"
(projekt-buchhaltung-ki.md) rules out — an LLM has no real signal about a small
business's future cash position beyond what's already in the database. So this is a
plain, explainable projection instead:

- Zufluss = already-issued, still-open invoices, bucketed by their real
  Faelligkeitsdatum. Not a sales forecast — money already owed, nothing more.
- Abfluss = a flat weekly average of the last HISTORIE_TAGE days of booked Ausgaben.
  No seasonality, no per-category modelling — a deliberately simple baseline that is
  honest about being simple (see `hinweis` in the response).
- Overdue invoices are shown separately, not folded into a future week — their
  payment is already uncertain, and pretending otherwise would misstate the forecast.
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import offene_posten
from app.invoices.models import Invoice
from app.receipts.models import Ausgabe

HISTORIE_TAGE = 90


@dataclass
class Wochenprognose:
    woche_start: date
    woche_ende: date
    erwarteter_zufluss: Decimal
    anzahl_faellige_rechnungen: int
    geschaetzter_abfluss: Decimal
    saldo_veraenderung: Decimal
    kumulierter_saldo: Decimal


def _durchschnittliche_wochenausgabe(db: Session, mandant_id: str, heute: date) -> Decimal:
    seit = heute - timedelta(days=HISTORIE_TAGE)
    ausgaben = (
        db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id, Ausgabe.zahlungsdatum >= seit, Ausgabe.zahlungsdatum <= heute).all()
    )
    summe = sum((a.betrag for a in ausgaben), Decimal("0"))
    if summe == 0:
        return Decimal("0.00")
    wochen = Decimal(HISTORIE_TAGE) / Decimal(7)
    return (summe / wochen).quantize(Decimal("0.01"))


def compute_cashflow(db: Session, *, mandant_id: str, wochen: int = 8) -> dict:
    heute = date.today()

    offene_rechnungen = (
        db.query(Invoice)
        .filter(Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.is_(None))
        .all()
    )
    # Offene Rechnungen aus Bilantiq und aus dem Altsystem als (Faelligkeit, Betrag).
    offene = [(r.faelligkeitsdatum, r.brutto_gesamt) for r in offene_rechnungen]
    offene += [(p.faelligkeit or heute, p.betrag) for p in offene_posten(db, mandant_id=mandant_id)]
    ueberfaellig = [(faellig, betrag) for faellig, betrag in offene if faellig < heute]
    zukuenftig = [(faellig, betrag) for faellig, betrag in offene if faellig >= heute]
    ueberfaellige_betrag = sum((betrag for _, betrag in ueberfaellig), Decimal("0"))

    wochenausgabe = _durchschnittliche_wochenausgabe(db, mandant_id, heute)

    prognosen: list[Wochenprognose] = []
    kumuliert = Decimal("0")
    for i in range(wochen):
        start = heute + timedelta(days=7 * i)
        ende = start + timedelta(days=6)
        faellige = [(faellig, betrag) for faellig, betrag in zukuenftig if start <= faellig <= ende]
        zufluss = sum((betrag for _, betrag in faellige), Decimal("0"))
        veraenderung = zufluss - wochenausgabe
        kumuliert += veraenderung
        prognosen.append(Wochenprognose(
            woche_start=start, woche_ende=ende, erwarteter_zufluss=zufluss,
            anzahl_faellige_rechnungen=len(faellige), geschaetzter_abfluss=wochenausgabe,
            saldo_veraenderung=veraenderung, kumulierter_saldo=kumuliert,
        ))

    warnung = None
    erste_negative = next((p for p in prognosen if p.kumulierter_saldo < 0), None)
    if erste_negative is not None:
        warnung = (
            f"Der kumulierte Saldo wird ab der Woche vom {erste_negative.woche_start.isoformat()} "
            "rechnerisch negativ, wenn nur die bekannten Zufluesse und der geschaetzte Abfluss eintreten."
        )

    return {
        "heute": heute,
        "wochen": [asdict(p) for p in prognosen],
        "ueberfaellige_rechnungen_betrag": ueberfaellige_betrag,
        "ueberfaellige_rechnungen_anzahl": len(ueberfaellig),
        "durchschnittliche_wochenausgabe": wochenausgabe,
        "warnung": warnung,
        "hinweis": (
            "Zufluesse sind nur bereits gestellte, offene Rechnungen nach Faelligkeitsdatum — keine "
            "Umsatzprognose fuer neues Geschaeft. Abfluesse sind ein grober Durchschnitt der letzten "
            f"{HISTORIE_TAGE} Tage, ohne Kategorien- oder Saisonanalyse. Ueberfaellige Rechnungen zaehlen "
            "nicht in die Wochenprognose, da ihr Zahlungseingang bereits unsicher ist — sie stehen separat."
        ),
    }
