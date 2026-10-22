"""Hilfsfunktionen rund um Kontakte, die mehrere Module brauchen (Routen, Bankabgleich,
Stammdaten-Import)."""
from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.key_management import blind_index
from app.invoices.models import Invoice, Kontakt


def kontakt_iban_hash(mandant_id: str, iban: str) -> str:
    return blind_index(iban.replace(" ", ""), purpose=f"kontakt-iban:{mandant_id}")


def setze_iban(kontakt: Kontakt, iban: str | None) -> None:
    kontakt.iban = iban
    kontakt.iban_hash = kontakt_iban_hash(kontakt.mandant_id, iban) if iban else None


def kontakt_wird_verwendet(db: Session, kontakt_id: str) -> bool:
    """True, wenn ein Beleg (Rechnung, Altrechnung, Angebot, Auftrag, Lieferschein, Vorlage) auf den Kontakt
    zeigt. Solche Kontakte duerfen nur archiviert werden, nie geloescht."""
    # Spaete Importe: diese Module importieren selbst app.invoices.models.
    from app.altrechnungen.models import Altrechnung
    from app.auftraege.models import Auftragsbestaetigung, Lieferschein
    from app.quotes.models import Quote
    from app.wiederkehrend.models import WiederkehrendeRechnung

    for model in (Invoice, Quote, Auftragsbestaetigung, Lieferschein, WiederkehrendeRechnung, Altrechnung):
        if db.scalar(select(exists().where(model.kontakt_id == kontakt_id))):
            return True
    return False
