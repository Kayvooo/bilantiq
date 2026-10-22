"""Checkliste "Erste Schritte": zeigt, was im Konto schon eingerichtet ist.

Der Fortschritt wird aus vorhandenen Daten abgeleitet, es gibt keinen eigenen Zustand, der
veralten koennte: Wer eine Rechnung erstellt, hat den Schritt erledigt, auch ohne die
Checkliste je geoeffnet zu haben."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.bank.models import Bankkonto
from app.db import get_db
from app.invoices.models import Invoice, Kontakt
from app.receipts.models import Receipt
from app.stammdaten.models import Datenimport

router = APIRouter(prefix="/erste-schritte", tags=["erste-schritte"])


class Schritt(BaseModel):
    id: str
    titel: str
    beschreibung: str
    erledigt: bool
    ziel: str  # Name der Seite im Frontend
    optional: bool = False
    hinweis: str | None = None


class ErsteSchritteResponse(BaseModel):
    schritte: list[Schritt]
    erledigt: int
    gesamt: int


def _anzahl(db: Session, modell, mandant_id: str, *bedingungen) -> int:
    return db.scalar(select(func.count()).select_from(modell).where(modell.mandant_id == mandant_id, *bedingungen)) or 0


@router.get("", response_model=ErsteSchritteResponse)
def erste_schritte(auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> ErsteSchritteResponse:
    mandant_id = auth["mandant_id"]
    mandant = db.get(Mandant, mandant_id)

    schritte = [
        Schritt(
            id="unternehmen", titel="Unternehmensdaten ergänzen",
            beschreibung="Anschrift und USt-IdNr. oder Steuernummer gehören auf jede Rechnung.",
            erledigt=bool(mandant.adresse and (mandant.ust_id or mandant.steuernummer)), ziel="settings",
        ),
        Schritt(
            id="design", titel="Rechnungsdesign anpassen",
            beschreibung="Lade dein Logo hoch und wähle Vorlage und Farbe.",
            erledigt=bool(mandant.logo_referenz or mandant.briefpapier_id), ziel="rechnungsvorlage",
        ),
        Schritt(
            id="kunde", titel="Ersten Kunden anlegen",
            beschreibung="Kunden brauchst du für Angebote und Rechnungen.",
            erledigt=_anzahl(db, Kontakt, mandant_id) > 0, ziel="contacts",
        ),
        Schritt(
            id="rechnung", titel="Erste Rechnung erstellen",
            beschreibung="Erstelle und finalisiere eine Rechnung mit Live-Vorschau.",
            erledigt=_anzahl(db, Invoice, mandant_id, Invoice.status == "final") > 0, ziel="invoices",
        ),
        Schritt(
            id="beleg", titel="Ersten Beleg hochladen",
            beschreibung="Foto, PDF oder E-Rechnung: Bilantiq liest Betrag, Datum und Anbieter aus.",
            erledigt=_anzahl(db, Receipt, mandant_id) > 0, ziel="receipts",
        ),
        Schritt(
            id="bank", titel="Kontoauszug importieren",
            beschreibung="Zahlungen werden Rechnungen und Belegen zugeordnet, ohne dass du alles abgleichen musst.",
            erledigt=_anzahl(db, Bankkonto, mandant_id) > 0, ziel="bank",
        ),
        Schritt(
            id="umzug", titel="Daten vom alten Anbieter übernehmen",
            beschreibung="Optional: Kontakte, Produkte und Rechnungen aus Excel, CSV oder einem anderen Programm übernehmen.",
            erledigt=_anzahl(db, Datenimport, mandant_id, Datenimport.rueckgaengig_am.is_(None)) > 0, ziel="umzug", optional=True,
        ),
        Schritt(
            id="steuerberater", titel="Steuerberatung hinterlegen",
            beschreibung="Optional: Kontakt der Kanzlei für Auswertungen und Exporte.",
            erledigt=bool(mandant.steuerberater_name or mandant.steuerberater_email), ziel="steuerberater", optional=True,
        ),
    ]
    return ErsteSchritteResponse(schritte=schritte, erledigt=sum(s.erledigt for s in schritte), gesamt=len(schritte))
