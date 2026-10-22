from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.schemas import AssistantPlan
from app.invoices.models import Invoice
from app.receipts.accounting import ausgabe_netto
from app.receipts.models import Ausgabe
from app.reports.bwa import compute_bwa
from app.reports.cashflow import compute_cashflow
from app.reports.dashboard import compute_dashboard
from app.reports.euer import compute_euer
from app.reports.susa import compute_susa
from app.reports.ustva import compute_ustva


def _jahr(plan: AssistantPlan, requested_year: int | None) -> int:
    return plan.jahr or requested_year or date.today().year


def _invoice_row(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "nummer": invoice.nummer,
        "kunde": invoice.kontakt.name,
        "brutto": invoice.brutto_gesamt,
        "waehrung": invoice.waehrung,
        "faelligkeitsdatum": invoice.faelligkeitsdatum,
        "bezahlt_am": invoice.bezahlt_am,
    }


def _date_range(plan: AssistantPlan, requested_year: int | None) -> tuple[date, date]:
    if plan.von and plan.bis:
        if plan.von > plan.bis:
            raise ValueError("'von' darf nicht nach 'bis' liegen.")
        return plan.von, plan.bis
    jahr = _jahr(plan, requested_year)
    return date(jahr, 1, 1), date(jahr, 12, 31)


def execute_tool(
    db: Session,
    *,
    mandant_id: str,
    plan: AssistantPlan,
    requested_year: int | None,
) -> dict:
    tool = plan.tool
    jahr = _jahr(plan, requested_year)

    if tool == "dashboard":
        return compute_dashboard(db, mandant_id=mandant_id, jahr=jahr)
    if tool == "euer":
        return compute_euer(db, mandant_id=mandant_id, jahr=jahr)
    if tool == "ustva":
        typ = plan.zeitraum_typ or "monat"
        heute = date.today()
        periode = plan.periode
        if periode is None:
            periode = heute.month if typ == "monat" else (heute.month - 1) // 3 + 1
        return compute_ustva(
            db,
            mandant_id=mandant_id,
            jahr=jahr,
            zeitraum_typ=typ,
            periode=periode,
        )
    if tool == "bwa":
        return compute_bwa(db, mandant_id=mandant_id, jahr=jahr)
    if tool == "susa":
        return compute_susa(db, mandant_id=mandant_id, jahr=jahr)
    if tool == "cashflow":
        return compute_cashflow(db, mandant_id=mandant_id, wochen=plan.wochen or 8)
    if tool in {"offene_rechnungen", "ueberfaellige_rechnungen"}:
        query = db.query(Invoice).filter(
            Invoice.mandant_id == mandant_id,
            Invoice.status == "final",
            Invoice.bezahlt_am.is_(None),
        )
        invoices = query.order_by(Invoice.faelligkeitsdatum).all()
        if tool == "ueberfaellige_rechnungen":
            invoices = [invoice for invoice in invoices if invoice.faelligkeitsdatum < date.today()]
        return {"rechnungen": [_invoice_row(invoice) for invoice in invoices]}
    if tool in {"ausgaben", "ausgaben_nach_kategorie"}:
        von, bis = _date_range(plan, requested_year)
        ausgaben = (
            db.query(Ausgabe)
            .filter(
                Ausgabe.mandant_id == mandant_id,
                Ausgabe.zahlungsdatum >= von,
                Ausgabe.zahlungsdatum <= bis,
            )
            .order_by(Ausgabe.zahlungsdatum)
            .all()
        )
        if tool == "ausgaben":
            gesamt_brutto = sum((a.betrag for a in ausgaben), Decimal("0"))
            gesamt_netto = sum((ausgabe_netto(a) for a in ausgaben), Decimal("0"))
            return {
                "von": von,
                "bis": bis,
                "anzahl": len(ausgaben),
                "gesamt_brutto": gesamt_brutto,
                "gesamt_netto": gesamt_netto,
                "hinweis": "Einzelliste ist aus Prompt-Schutz auf die ersten 100 Buchungen begrenzt.",
                "ausgaben": [
                    {
                        "id": a.id,
                        "zahlungsdatum": a.zahlungsdatum,
                        "anbieter": a.anbieter,
                        "kategorie": a.kategorie,
                        "konto": a.konto,
                        "brutto": a.betrag,
                        "netto": ausgabe_netto(a),
                    }
                    for a in ausgaben[:100]
                ],
            }
        kategorien: dict[str, dict[str, Decimal]] = {}
        for ausgabe in ausgaben:
            bucket = kategorien.setdefault(
                ausgabe.kategorie,
                {"brutto": Decimal("0"), "netto": Decimal("0")},
            )
            bucket["brutto"] += ausgabe.betrag
            bucket["netto"] += ausgabe_netto(ausgabe)
        return {
            "von": von,
            "bis": bis,
            "kategorien": [
                {"kategorie": name, **werte}
                for name, werte in sorted(kategorien.items())
            ],
        }
    if tool == "keine":
        return {"hinweis": "Keine passende freigegebene Bilantiq-Datenquelle fuer diese Frage."}
    raise ValueError(f"Nicht erlaubtes Tool: {tool}")
