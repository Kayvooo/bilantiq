"""Zahlungen und Status von Altrechnungen."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.models import Altrechnung, AltrechnungZahlung
from app.core.audit_log import record as record_audit

CENT = Decimal("0.01")
TOLERANZ = Decimal("0.005")


class ZahlungAbgelehnt(ValueError):
    """Meldung fuer den Nutzer."""


def bezahlt_in_bilantiq(altrechnung: Altrechnung) -> Decimal:
    return sum((z.betrag for z in altrechnung.zahlungen), Decimal("0"))


def restbetrag(altrechnung: Altrechnung) -> Decimal:
    rest = altrechnung.offen_beim_import - bezahlt_in_bilantiq(altrechnung)
    return rest.quantize(CENT) if rest > TOLERANZ else Decimal("0.00")


def status(altrechnung: Altrechnung, heute: date | None = None) -> str:
    """offen | ueberfaellig | bezahlt (auch: schon im Altsystem bezahlt)."""
    if restbetrag(altrechnung) <= 0:
        return "bezahlt"
    heute = heute or date.today()
    if altrechnung.faelligkeit is not None and altrechnung.faelligkeit < heute:
        return "ueberfaellig"
    return "offen"


def erfasse_zahlung(
    db: Session, altrechnung: Altrechnung, *, datum: date | None, betrag: Decimal | None, quelle: str, user_id: str | None,
) -> AltrechnungZahlung:
    """Haengt eine Zahlung an. Wie bei Bilantiq-Rechnungen laesst sie sich nicht zuruecknehmen."""
    rest = restbetrag(altrechnung)
    if rest <= 0:
        raise ZahlungAbgelehnt("Diese Rechnung ist schon vollständig bezahlt.")
    betrag = rest if betrag is None else betrag.quantize(CENT)
    if betrag <= 0:
        raise ZahlungAbgelehnt("Der Betrag muss größer als 0 sein.")
    if betrag > rest + TOLERANZ:
        raise ZahlungAbgelehnt(f"Der Betrag ({betrag:.2f} €) ist höher als der offene Betrag ({rest:.2f} €).")
    datum = datum or date.today()
    if datum > date.today():
        raise ZahlungAbgelehnt("Das Zahlungsdatum liegt in der Zukunft.")
    zahlung = AltrechnungZahlung(
        mandant_id=altrechnung.mandant_id, altrechnung_id=altrechnung.id, datum=datum, betrag=betrag, quelle=quelle, user_id=user_id,
    )
    altrechnung.zahlungen.append(zahlung)
    record_audit(
        db, aktion="altrechnung_zahlung", mandant_id=altrechnung.mandant_id, user_id=user_id,
        kontext=f"{altrechnung.id} {quelle} {betrag:.2f}",
    )
    return zahlung
