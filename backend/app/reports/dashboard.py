"""Aggregation für die Startseite (Uebersicht). Nur Widgets aus echten Bilantiq-Daten
— bewusst kein "Buchhaltungsscore" oder "Top 5 Produkte": ohne Bankanbindung (kein
finAPI, siehe app/kassenbuch/) gibt es keinen sinnvollen Score, und ohne Produktkatalog
(noch nicht gebaut) waere eine Top-Produkte-Liste aus Freitext-Positionsbeschreibungen
nur geraten. "Bank" heisst hier bewusst "Kassenbuch", aus demselben Grund wie in der
Navigation (siehe docs/specs/brand-redesign.md)."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import offene_posten, zahlungen_je_kontakt, zahlungsanteile
from app.core.audit_log import AuditLogEintrag
from app.invoices.models import Invoice, Kontakt
from app.kassenbuch.models import KassenbuchEintrag
from app.receipts.accounting import ausgabe_netto
from app.receipts.models import Ausgabe
from app.reports.euer import HINWEIS as EUER_HINWEIS

KLEINUNTERNEHMERGRENZE = Decimal("25000.00")  # § 19 UStG, Vorjahresumsatz-Schwelle


def compute_dashboard(db: Session, *, mandant_id: str, jahr: int) -> dict:
    von = date(jahr, 1, 1)
    bis = date(jahr, 12, 31)
    heute = date.today()

    bezahlte_rechnungen = (
        db.query(Invoice)
        .filter(
            Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.isnot(None),
            Invoice.bezahlt_am >= von, Invoice.bezahlt_am <= bis,
        )
        .all()
    )
    ausgaben_jahr = db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id, Ausgabe.zahlungsdatum >= von, Ausgabe.zahlungsdatum <= bis).all()

    monats_einnahmen = [Decimal("0")] * 12
    monats_ausgaben = [Decimal("0")] * 12
    for rechnung in bezahlte_rechnungen:
        monats_einnahmen[rechnung.bezahlt_am.month - 1] += rechnung.netto_gesamt
    for ausgabe in ausgaben_jahr:
        monats_ausgaben[ausgabe.zahlungsdatum.month - 1] += ausgabe_netto(ausgabe)

    alt_anteile = zahlungsanteile(db, mandant_id=mandant_id, von=von, bis=bis)
    for anteil in alt_anteile:
        monats_einnahmen[anteil.datum.month - 1] += anteil.netto

    einnahmen_gesamt = sum(monats_einnahmen, Decimal("0"))
    ausgaben_gesamt = sum(monats_ausgaben, Decimal("0"))
    umsatz_brutto_jahr = sum((r.brutto_gesamt for r in bezahlte_rechnungen), Decimal("0"))
    umsatz_brutto_jahr += sum((a.brutto for a in alt_anteile), Decimal("0"))

    offene = (
        db.query(Invoice)
        .filter(Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.is_(None))
        .all()
    )
    # Offene Forderungen aus dem Altsystem zaehlen mit, bis sie bezahlt sind.
    posten = offene_posten(db, mandant_id=mandant_id)
    faellige = [r for r in offene if r.faelligkeitsdatum < heute]
    nicht_faellige = [r for r in offene if r.faelligkeitsdatum >= heute]
    alt_faellig = [p for p in posten if p.faelligkeit is not None and p.faelligkeit < heute]
    alt_nicht_faellig = [p for p in posten if p.faelligkeit is None or p.faelligkeit >= heute]

    alle_bezahlten = (
        db.query(Invoice)
        .filter(Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.isnot(None))
        .all()
    )
    kunden_umsatz: dict[str, Decimal] = {}
    for rechnung in alle_bezahlten:
        kunden_umsatz[rechnung.kontakt.name] = kunden_umsatz.get(rechnung.kontakt.name, Decimal("0")) + rechnung.brutto_gesamt
    # Zahlungen auf Altrechnungen, die in Bilantiq erfasst wurden, zaehlen zum Kundenumsatz.
    namen = dict(db.query(Kontakt.id, Kontakt.name).filter(Kontakt.mandant_id == mandant_id))
    for kontakt_id, betrag in zahlungen_je_kontakt(db, mandant_id=mandant_id).items():
        if name := namen.get(kontakt_id):
            kunden_umsatz[name] = kunden_umsatz.get(name, Decimal("0")) + betrag
    top_kunden = sorted(kunden_umsatz.items(), key=lambda kv: kv[1], reverse=True)[:5]

    alle_ausgaben = db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id).all()
    kategorie_summen: dict[str, Decimal] = {}
    for ausgabe in alle_ausgaben:
        kategorie_summen[ausgabe.kategorie] = kategorie_summen.get(ausgabe.kategorie, Decimal("0")) + ausgabe.betrag
    top_ausgaben = sorted(kategorie_summen.items(), key=lambda kv: kv[1], reverse=True)[:5]

    kassenbuch_eintraege = db.query(KassenbuchEintrag).filter(KassenbuchEintrag.mandant_id == mandant_id).all()
    kassenbestand = sum(
        (e.betrag if e.typ == "einnahme" else -e.betrag for e in kassenbuch_eintraege), Decimal("0")
    )

    verlauf = (
        db.query(AuditLogEintrag)
        .filter(AuditLogEintrag.mandant_id == mandant_id)
        .order_by(AuditLogEintrag.zeitpunkt.desc())
        .limit(10)
        .all()
    )

    return {
        "jahr": jahr,
        "gewinn_vor_steuern": einnahmen_gesamt - ausgaben_gesamt,
        "einnahmen": einnahmen_gesamt,
        "ausgaben": ausgaben_gesamt,
        "monatswerte": [
            {"monat": i + 1, "einnahmen": monats_einnahmen[i], "ausgaben": monats_ausgaben[i]} for i in range(12)
        ],
        "faellige_rechnungen": {
            "anzahl": len(faellige) + len(alt_faellig),
            "betrag": sum((r.brutto_gesamt for r in faellige), Decimal("0")) + sum((p.betrag for p in alt_faellig), Decimal("0")),
        },
        "offene_rechnungen": {
            "anzahl": len(nicht_faellige) + len(alt_nicht_faellig),
            "betrag": sum((r.brutto_gesamt for r in nicht_faellige), Decimal("0"))
            + sum((p.betrag for p in alt_nicht_faellig), Decimal("0")),
        },
        "kleinunternehmergrenze": KLEINUNTERNEHMERGRENZE,
        "umsatz_brutto_jahr": umsatz_brutto_jahr,
        "kassenbestand": kassenbestand,
        "top_kunden": [{"name": name, "betrag": betrag} for name, betrag in top_kunden],
        "top_ausgaben_kategorien": [{"name": name, "betrag": betrag} for name, betrag in top_ausgaben],
        "verlauf": [
            {"aktion": e.aktion, "kontext": e.kontext, "zeitpunkt": e.zeitpunkt} for e in verlauf
        ],
        "hinweis": EUER_HINWEIS,
    }
