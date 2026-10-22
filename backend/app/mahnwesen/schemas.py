from datetime import date
from decimal import Decimal

from pydantic import BaseModel

STUFE_BEZEICHNUNG = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung"}


class MahnungResponse(BaseModel):
    id: str
    invoice_id: str
    stufe: int
    stufe_bezeichnung: str
    mahngebuehr: Decimal
    neue_faelligkeit: date
    erstellt_am: str
    versendet_am: str | None = None
    kontakt_email_vorhanden: bool = False


class MahnungUebersichtResponse(MahnungResponse):
    """MahnungResponse plus Rechnungs-Kontext fuer die uebergreifende Mahnungen-Seite,
    die nicht wie die Mahnstufen-Erfassung an eine einzelne Rechnung gebunden ist."""

    rechnung_nummer: str
    kontakt_name: str
    rechnung_brutto: Decimal


class VersendenRequest(BaseModel):
    """Body fuer POST .../versenden -- text ist optional, ohne ihn kommt ein fester
    deutscher Standardtext zum Einsatz (siehe routes.py)."""

    text: str | None = None
