"""Fachlogik fuer das Markieren einer Rechnung als bezahlt (manuell und per Bankabgleich)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.audit_log import record as record_audit
from app.invoices.models import Invoice


def markiere_rechnung_bezahlt(
    db: Session,
    invoice: Invoice,
    *,
    bezahlt_am: date,
    user_id: str | None = None,
) -> None:
    """Gemeinsame, transaktionsneutrale Fachfunktion fuer manuelle Zahlung und Bankabgleich.

    Commit/Rollback bleibt beim Aufrufer, damit Audit-Eintrag und Rechnungszustand
    atomar gespeichert werden.
    """
    if invoice.status != "final":
        raise ValueError("Nur finale Rechnungen koennen als bezahlt markiert werden.")
    if invoice.bezahlt_am is not None:
        raise ValueError("Diese Rechnung ist bereits als bezahlt markiert.")

    invoice.bezahlt_am = bezahlt_am
    record_audit(
        db,
        aktion="rechnung_bezahlt_markiert",
        mandant_id=invoice.mandant_id,
        user_id=user_id,
        kontext=invoice.nummer,
    )
