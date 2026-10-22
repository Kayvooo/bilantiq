"""Umzugsassistent: zeigt, wie weit der Wechsel von einem anderen Programm ist.

Wie bei den Ersten Schritten gibt es keinen eigenen Zustand. Was erledigt ist, steht in den Daten
(Importe, Bankkonten, Nummernkreis), deshalb kann nichts veralten. Anleitungen fuer einzelne Anbieter
(Menuewege bei lexoffice, sevdesk, ...) gibt es hier bewusst nicht: Sie aendern sich und lassen sich
ohne Zugang zu den Programmen nicht pruefen."""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import offene_posten
from app.altrechnungen.models import Altrechnung
from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.bank.models import Bankkonto
from app.db import get_db
from app.nummernkreis import service as nummernkreis
from app.stammdaten.models import Datenimport

router = APIRouter(prefix="/umzug", tags=["umzug"])

Status = Literal["erledigt", "offen", "nicht_noetig", "info"]


class UmzugSchritt(BaseModel):
    id: str
    titel: str
    beschreibung: str
    status: Status
    detail: str | None = None
    ziel: str | None = None  # Seite im Frontend (DesktopStep), None = nur Hinweis
    aktion: Literal["neu", "import"] | None = None
    ansicht: Literal["altsystem"] | None = None
    nur_inhaber: bool = False
    optional: bool = False
    hinweis: str | None = None


class UmzugResponse(BaseModel):
    schritte: list[UmzugSchritt]
    erledigt: int
    gesamt: int


def _import_summe(db: Session, mandant_id: str, ziel: str) -> tuple[int, int]:
    """(Anzahl nicht zurueckgenommener Importe, darin neu angelegte Datensaetze)."""
    zeile = db.execute(
        select(func.count(Datenimport.id), func.coalesce(func.sum(Datenimport.anzahl_neu), 0)).where(
            Datenimport.mandant_id == mandant_id, Datenimport.ziel == ziel, Datenimport.rueckgaengig_am.is_(None)
        )
    ).one()
    return int(zeile[0]), int(zeile[1])


def _euro(betrag: Decimal) -> str:
    return f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


@router.get("", response_model=UmzugResponse)
def umzug(auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> UmzugResponse:
    mandant_id = auth["mandant_id"]
    mandant = db.get(Mandant, mandant_id)
    heute = date.today()

    importe = {ziel: _import_summe(db, mandant_id, ziel) for ziel in ("kontakte", "produkte", "rechnungen")}
    irgendein_import = any(anzahl for anzahl, _ in importe.values())

    alt_gesamt = db.scalar(select(func.count()).select_from(Altrechnung).where(Altrechnung.mandant_id == mandant_id)) or 0
    alt_mit_pdf = db.scalar(select(func.count()).select_from(Altrechnung).where(Altrechnung.mandant_id == mandant_id, Altrechnung.datei_referenz.is_not(None))) or 0
    posten = offene_posten(db, mandant_id=mandant_id) if alt_gesamt else []
    offen_summe = sum((p.betrag for p in posten), Decimal("0"))
    ueberfaellig = sum(1 for p in posten if p.faelligkeit is not None and p.faelligkeit < heute)

    stand = nummernkreis.lese_stand(db, mandant_id)
    bank_vorhanden = (db.scalar(select(func.count()).select_from(Bankkonto).where(Bankkonto.mandant_id == mandant_id)) or 0) > 0

    def import_detail(ziel: str, einzahl: str, mehrzahl: str) -> str | None:
        anzahl, neu = importe[ziel]
        return f"{neu} {einzahl if neu == 1 else mehrzahl} übernommen" if anzahl else None

    rechnungen_detail = None
    if importe["rechnungen"][0]:
        rechnungen_detail = f"{alt_gesamt} Rechnungen übernommen, {alt_mit_pdf} mit PDF, {len(posten)} offen"

    if not alt_gesamt:
        nummernkreis_status: Status = "nicht_noetig"
        nummernkreis_detail = "Erst nötig, wenn du Rechnungen aus dem alten Programm übernommen hast."
    else:
        nummernkreis_status = "offen" if stand.kollision else "erledigt"
        nummernkreis_detail = f"Nächste Rechnungsnummer in Bilantiq: {stand.naechste_rechnungsnummer}"
        if stand.hoechste_altsystem is not None:
            nummernkreis_detail += f". Im alten Programm gab es bis {nummernkreis.formatiere(stand.jahr, stand.hoechste_altsystem)}."

    schritte = [
        UmzugSchritt(
            id="export", titel="Beim alten Anbieter exportieren",
            beschreibung=(
                "Exportiere Kontakte, Artikel und die Rechnungsliste als Excel- oder CSV-Datei und lade die PDFs deiner Rechnungen "
                "herunter. Wo das steht, unterscheidet sich je Programm. Exportiere, bevor du kündigst, und bewahre den vollständigen "
                "Original-Export zehn Jahre auf (GoBD)."
            ),
            status="erledigt" if irgendein_import else "offen",
        ),
        UmzugSchritt(
            id="kontakte", titel="Kontakte übernehmen", beschreibung="Kunden und Lieferanten aus Excel oder CSV, mit Prüfung vor dem Übernehmen.",
            status="erledigt" if importe["kontakte"][0] else "offen", detail=import_detail("kontakte", "Kontakt", "Kontakte"),
            ziel="contacts", aktion="import", nur_inhaber=True,
        ),
        UmzugSchritt(
            id="produkte", titel="Produkte übernehmen", beschreibung="Artikel und Leistungen mit Preisen und Artikelnummern.",
            status="erledigt" if importe["produkte"][0] else "offen", detail=import_detail("produkte", "Produkt", "Produkte"),
            ziel="produkte", aktion="import", nur_inhaber=True, optional=True,
        ),
        UmzugSchritt(
            id="rechnungen", titel="Rechnungsliste und PDFs übernehmen",
            beschreibung=(
                "Die Rechnungen bleiben unverändert als Archiv. Bereits bezahlte zählen in keiner Auswertung, offene gelten als Forderung."
            ),
            status="erledigt" if importe["rechnungen"][0] else "offen", detail=rechnungen_detail,
            ziel="invoices", ansicht="altsystem", nur_inhaber=True,
        ),
        UmzugSchritt(
            id="nummernkreis", titel="Nummernkreis fortsetzen",
            beschreibung=(
                "Damit Bilantiq keine Rechnungsnummer noch einmal vergibt, die es im alten Programm schon gab (§ 14 UStG), "
                "setzt du die nächste Nummer hinter die letzte alte."
            ),
            status=nummernkreis_status, detail=nummernkreis_detail, ziel="umzug", nur_inhaber=True,
        ),
        UmzugSchritt(
            id="offene_posten", titel="Offene Posten prüfen",
            beschreibung="Prüfe, welche alten Rechnungen noch offen sind, und erfasse Zahlungen, sobald das Geld da ist. Erst dann zählen sie in Einnahmen und Umsatzsteuer.",
            status="info" if posten else "nicht_noetig",
            detail=(f"{len(posten)} offene Rechnungen über {_euro(offen_summe)}, davon {ueberfaellig} überfällig" if posten else "Keine offenen Rechnungen aus dem alten Programm."),
            ziel="invoices" if posten else None, ansicht="altsystem" if posten else None,
        ),
        UmzugSchritt(
            id="kontoauszug", titel="Kontoauszug importieren",
            beschreibung="Zahlungen werden Rechnungen zugeordnet, auch den offenen aus dem alten Programm (über Betrag, Rechnungsnummer und Name).",
            status="erledigt" if bank_vorhanden else "offen", ziel="bank", optional=True,
        ),
        UmzugSchritt(
            id="steuerberater", titel="Steuerberatung informieren",
            beschreibung=(
                "Sag der Kanzlei, ab wann Bilantiq die Buchführung übernimmt und dass Rechnungen aus dem alten Programm nur mit den "
                "Zahlungen zählen, die in Bilantiq erfasst werden."
            ),
            status="erledigt" if (mandant.steuerberater_name or mandant.steuerberater_email) else "offen", ziel="steuerberater", optional=True,
        ),
    ]
    gezaehlt = [s for s in schritte if s.status in ("erledigt", "offen")]
    return UmzugResponse(schritte=schritte, erledigt=sum(s.status == "erledigt" for s in gezaehlt), gesamt=len(gezaehlt))
