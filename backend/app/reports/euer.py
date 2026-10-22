"""EUER = Einnahmen-Ueberschuss-Rechnung, the cash-basis profit calculation German
small businesses file with their tax return (§ 4 Abs. 3 EStG).

Zufluss-/Abflussprinzip (§ 11 EStG): income counts when the money actually arrives,
expenses when they actually leave — not when an invoice was issued or a receipt dated.
That is why this reads Invoice.bezahlt_am (not erstellt_am/finalisiert_am) for invoice
income, SonstigeEinnahme.datum for separately received income, and
Ausgabe.zahlungsdatum for expenses. Belegdatum und Zahlungsdatum are deliberately
separate because an Eingangsrechnung may be paid later.

Amounts are net (Umsatzsteuer excluded) because VAT collected or paid is a liability
to/receivable from the Finanzamt, not the business's own income or expense — the
standard treatment for a regelbesteuert business, and a no-op for a Kleinunternehmer
whose ust_satz is always 0 anyway (netto == brutto there).

This computes numbers; it is not tax advice and does not replace a Steuerberater —
see the StBerG §5 boundary already applied to KI-Belegerfassung.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import offene_posten, zahlungsanteile
from app.invoices.models import Invoice
from app.einnahmen.models import SonstigeEinnahme
from app.receipts.accounting import ausgabe_netto
from app.receipts.models import Ausgabe
from app.reports.afa import sammle_afa_jahreswerte

HINWEIS = (
    "Netto-Betraege nach Zufluss-/Abflussprinzip (§ 11 EStG). Umsatzsteuer ist als "
    "durchlaufender Posten nicht enthalten; die Jahres-AfA ist als nicht zahlungswirksame "
    "Betriebsausgabe enthalten. Rechnungen aus einem früheren Programm zählen nur mit Zahlungen, die in "
    "Bilantiq erfasst wurden. Ersetzt keine Steuerberatung."
)


def _sonstige_einnahme_netto(einnahme: SonstigeEinnahme) -> Decimal:
    return (
        einnahme.betrag_brutto / (Decimal("1") + einnahme.ust_satz / Decimal("100"))
    ).quantize(Decimal("0.01"))


def compute_euer(db: Session, *, mandant_id: str, jahr: int) -> dict:
    von = date(jahr, 1, 1)
    bis = date(jahr, 12, 31)

    bezahlte_rechnungen = (
        db.query(Invoice)
        .filter(
            Invoice.mandant_id == mandant_id,
            Invoice.status == "final",
            Invoice.bezahlt_am.isnot(None),
            Invoice.bezahlt_am >= von,
            Invoice.bezahlt_am <= bis,
        )
        .all()
    )
    sonstige_einnahmen = (
        db.query(SonstigeEinnahme)
        .filter(
            SonstigeEinnahme.mandant_id == mandant_id,
            SonstigeEinnahme.datum >= von,
            SonstigeEinnahme.datum <= bis,
        )
        .all()
    )
    einnahmen_netto = sum((i.netto_gesamt for i in bezahlte_rechnungen), Decimal("0"))
    einnahmen_netto += sum((_sonstige_einnahme_netto(e) for e in sonstige_einnahmen), Decimal("0"))
    alt_anteile = zahlungsanteile(db, mandant_id=mandant_id, von=von, bis=bis)
    einnahmen_netto += sum((a.netto for a in alt_anteile), Decimal("0"))

    ausgaben = db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id, Ausgabe.zahlungsdatum >= von, Ausgabe.zahlungsdatum <= bis).all()
    ausgaben_netto = sum((ausgabe_netto(a) for a in ausgaben), Decimal("0"))
    afa_jahreswerte = sammle_afa_jahreswerte(db, mandant_id=mandant_id, jahr=jahr)
    ausgaben_netto += sum((betrag for _, betrag in afa_jahreswerte), Decimal("0"))

    offene = (
        db.query(Invoice)
        .filter(Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.is_(None))
        .all()
    )
    offene_brutto = sum((i.brutto_gesamt for i in offene), Decimal("0"))
    offene_brutto += sum((p.betrag for p in offene_posten(db, mandant_id=mandant_id)), Decimal("0"))

    return {
        "jahr": jahr,
        "zeitraum_von": von,
        "zeitraum_bis": bis,
        "betriebseinnahmen_netto": einnahmen_netto,
        "anzahl_einnahmen": len(bezahlte_rechnungen) + len(sonstige_einnahmen) + len({a.zahlung_id for a in alt_anteile}),
        "betriebsausgaben_netto": ausgaben_netto,
        "anzahl_ausgaben": len(ausgaben) + len(afa_jahreswerte),
        "ueberschuss_netto": einnahmen_netto - ausgaben_netto,
        "offene_forderungen_brutto": offene_brutto,
        "hinweis": HINWEIS,
    }
