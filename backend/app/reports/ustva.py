"""UStVA-Zahlen (Umsatzsteuervoranmeldung) — die Berechnung, nicht die ELSTER-Uebermittlung.

Ist-Versteuerung angenommen: Umsatzsteuer wird dem Zeitraum zugeordnet, in dem die
Rechnung tatsaechlich bezahlt wurde (Invoice.bezahlt_am), nicht dem Rechnungsdatum.
Das passt zur bereits kassenbasierten EUER-Logik (app/reports/euer.py) und ist die
uebliche Besteuerungsart fuer Freiberufler/kleine Unternehmen, aber nicht die einzige —
ein Soll-versteuerndes Unternehmen muesste stattdessen nach Leistungsdatum rechnen.
Siehe Annahmen in der Spec.

Deckt die Kennziffern ab, die eine ganz normale Rechnung mit 19%/7% USt und normale
Vorsteuer aus Belegen braucht — nicht den vollstaendigen amtlichen Kennziffernkatalog
(innergemeinschaftliche Lieferungen, Reverse Charge, Kleinunternehmerregelung §19 UStG
etc. sind nicht abgebildet). Kein ELSTER-Versand: das braeuchte eine ERiC-Anbindung mit
Zertifikat, bewusst nicht Teil dieser Spec.
"""
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import zahlungsanteile
from app.invoices.models import Invoice
from app.receipts.accounting import ausgabe_vorsteuer
from app.receipts.models import Ausgabe

STANDARD_SAETZE = {Decimal("19.00"), Decimal("7.00")}


def zeitraum_grenzen(jahr: int, zeitraum_typ: str, periode: int) -> tuple[date, date]:
    if zeitraum_typ == "monat":
        if not 1 <= periode <= 12:
            raise ValueError("periode muss 1-12 sein fuer zeitraum_typ=monat")
        letzter_tag = calendar.monthrange(jahr, periode)[1]
        return date(jahr, periode, 1), date(jahr, periode, letzter_tag)
    if zeitraum_typ == "quartal":
        if not 1 <= periode <= 4:
            raise ValueError("periode muss 1-4 sein fuer zeitraum_typ=quartal")
        start_monat = (periode - 1) * 3 + 1
        end_monat = start_monat + 2
        letzter_tag = calendar.monthrange(jahr, end_monat)[1]
        return date(jahr, start_monat, 1), date(jahr, end_monat, letzter_tag)
    raise ValueError(f"Unbekannter zeitraum_typ: {zeitraum_typ!r} (erwartet: monat|quartal)")


def compute_ustva(db: Session, *, mandant_id: str, jahr: int, zeitraum_typ: str, periode: int) -> dict:
    von, bis = zeitraum_grenzen(jahr, zeitraum_typ, periode)

    bezahlte_rechnungen = (
        db.query(Invoice)
        .filter(
            Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.isnot(None),
            Invoice.bezahlt_am >= von, Invoice.bezahlt_am <= bis,
        )
        .all()
    )

    umsatz_19_netto = Decimal("0")
    ust_19 = Decimal("0")
    umsatz_7_netto = Decimal("0")
    ust_7 = Decimal("0")
    umsatz_sonstige_netto = Decimal("0")

    for rechnung in bezahlte_rechnungen:
        for position in rechnung.positionen:
            netto = (position.menge * position.einzelpreis).quantize(Decimal("0.01"))
            steuer = (netto * position.ust_satz / Decimal("100")).quantize(Decimal("0.01"))
            if position.ust_satz == Decimal("19.00"):
                umsatz_19_netto += netto
                ust_19 += steuer
            elif position.ust_satz == Decimal("7.00"):
                umsatz_7_netto += netto
                ust_7 += steuer
            else:
                umsatz_sonstige_netto += netto

    # Rechnungen aus dem Altsystem: nur Zahlungen, die in Bilantiq erfasst wurden, anteilig je Steuersatz.
    alt_anteile = zahlungsanteile(db, mandant_id=mandant_id, von=von, bis=bis)
    for anteil in alt_anteile:
        if anteil.satz == Decimal("19.00"):
            umsatz_19_netto += anteil.netto
            ust_19 += anteil.ust
        elif anteil.satz == Decimal("7.00"):
            umsatz_7_netto += anteil.netto
            ust_7 += anteil.ust
        else:
            umsatz_sonstige_netto += anteil.netto  # 0 % und die befristeten Saetze von 2020 (hier ohne USt)

    # Vorsteuer wird hier nach dem Beleg-/Rechnungsdatum zugeordnet. Das ist bewusst
    # getrennt vom EÜR-Zahlungsdatum; Sonderfälle (z.B. Anzahlungen) sind weiterhin
    # nicht Teil dieser vereinfachten UStVA.
    ausgaben = db.query(Ausgabe).filter(
        Ausgabe.mandant_id == mandant_id, Ausgabe.datum >= von, Ausgabe.datum <= bis
    ).all()
    vorsteuer_gesamt = sum((ausgabe_vorsteuer(ausgabe) for ausgabe in ausgaben), Decimal("0"))

    umsatzsteuer_gesamt = ust_19 + ust_7
    zahllast = umsatzsteuer_gesamt - vorsteuer_gesamt

    return {
        "jahr": jahr, "zeitraum_typ": zeitraum_typ, "periode": periode,
        "zeitraum_von": von, "zeitraum_bis": bis,
        "umsatz_19_netto": umsatz_19_netto, "umsatzsteuer_19": ust_19,
        "umsatz_7_netto": umsatz_7_netto, "umsatzsteuer_7": ust_7,
        "umsatz_sonstige_netto": umsatz_sonstige_netto,
        "umsatzsteuer_gesamt": umsatzsteuer_gesamt, "vorsteuer_gesamt": vorsteuer_gesamt,
        "zahllast": zahllast,
        "anzahl_rechnungen": len(bezahlte_rechnungen) + len({a.altrechnung_id for a in alt_anteile}), "anzahl_ausgaben": len(ausgaben),
        "hinweis": (
            "Für Ausgangsumsätze wird Ist-Versteuerung angenommen (Zeitpunkt der Zahlung). "
            "Vorsteuer aus Ausgaben wird nach dem erfassten Beleg-/Rechnungsdatum zugeordnet. "
            "Deckt normale 19%/7%-Umsaetze und Vorsteuer ab, nicht Sonderfaelle wie "
            "innergemeinschaftliche Lieferungen, Reverse Charge oder Kleinunternehmerregelung. "
            "Kein ELSTER-Versand — das ist eine Berechnungshilfe, keine amtliche Uebermittlung. "
            "Positive Zahllast = an das Finanzamt zu zahlen, negative Zahllast = Erstattung."
        ),
    }
