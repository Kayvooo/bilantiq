"""Altrechnungen: Liste, Zahlung erfassen, PDF-Archiv und Kontakt-Historie.

Der Import der Rechnungsliste laeuft ueber /stammdaten/rechnungen (nur Inhaber). Hier liegt, was
danach im Alltag passiert. Es gibt bewusst keine Funktion zum Loeschen oder Ersetzen eines PDFs: Archivierte
Belege sind unveraenderbar (GoBD, Aufbewahrung `retention_years`)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, defer, selectinload

from app.altrechnungen import service, storage
from app.altrechnungen.models import Altrechnung
from app.altrechnungen.schemas import (
    AltrechnungListe, AltrechnungResponse, HistorieEintrag, HistorieResponse, PdfAntwort, PdfErgebnis, ZahlungEingabe,
    ZahlungResponse,
)
from app.altrechnungen.zuordnung import Kandidat, Zuordner
from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.core.sperren import sperre_mandant
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.invoices.models import Invoice, Kontakt
from app.invoices.routes import _anzeige_status
from app.receipts.service import erkenne_dateityp

router = APIRouter(prefix="/altrechnungen", tags=["altrechnungen"])
kontakt_router = APIRouter(prefix="/kontakte", tags=["altrechnungen"])


def _mandant(auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


def _antwort(altrechnung: Altrechnung, kontakt_name: str) -> AltrechnungResponse:
    rest = service.restbetrag(altrechnung)
    return AltrechnungResponse(
        id=altrechnung.id, nummer=altrechnung.nummer, kontakt_id=altrechnung.kontakt_id, kontakt_name=kontakt_name,
        rechnungsdatum=altrechnung.rechnungsdatum, faelligkeit=altrechnung.faelligkeit, brutto=altrechnung.brutto,
        offen_beim_import=altrechnung.offen_beim_import, offen=rest, status=service.status(altrechnung),
        bezahlt_im_altsystem=altrechnung.offen_beim_import <= 0, bezahlt_im_altsystem_am=altrechnung.bezahlt_im_altsystem_am,
        hat_pdf=altrechnung.datei_referenz is not None,
        zahlungen=[ZahlungResponse(id=z.id, datum=z.datum, betrag=z.betrag, quelle=z.quelle) for z in altrechnung.zahlungen],
    )


def _kontakt_namen(db: Session, mandant_id: str) -> dict[str, str]:
    return dict(db.execute(select(Kontakt.id, Kontakt.name).where(Kontakt.mandant_id == mandant_id)).all())


def _name(db: Session, altrechnung: Altrechnung) -> str:
    return db.scalar(select(Kontakt.name).where(Kontakt.id == altrechnung.kontakt_id)) or ""


@router.get("", response_model=AltrechnungListe)
def liste(
    status_filter: Literal["alle", "offen", "bezahlt"] = Query("alle", alias="status"),
    kontakt_id: str | None = None,
    ohne_pdf: bool = False,
    limit: int = Query(500, ge=1, le=2000),
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> AltrechnungListe:
    anfrage = (
        db.query(Altrechnung)
        .options(selectinload(Altrechnung.zahlungen), defer(Altrechnung.steueranteile))
        .filter(Altrechnung.mandant_id == auth["mandant_id"])
    )
    if kontakt_id:
        anfrage = anfrage.filter(Altrechnung.kontakt_id == kontakt_id)
    if ohne_pdf:
        anfrage = anfrage.filter(Altrechnung.datei_referenz.is_(None))
    zeilen = anfrage.order_by(Altrechnung.rechnungsdatum.desc(), Altrechnung.erstellt_am.desc()).all()
    if status_filter != "alle":
        gewuenscht_bezahlt = status_filter == "bezahlt"
        zeilen = [z for z in zeilen if (service.status(z) == "bezahlt") == gewuenscht_bezahlt]
    namen = _kontakt_namen(db, auth["mandant_id"])
    return AltrechnungListe(gesamt=len(zeilen), eintraege=[_antwort(z, namen.get(z.kontakt_id, "")) for z in zeilen[:limit]])


@router.post("/{altrechnung_id}/zahlung", response_model=AltrechnungResponse)
def zahlung_erfassen(
    altrechnung_id: str, payload: ZahlungEingabe, auth=Depends(require_full_auth), db: Session = Depends(get_db),
) -> AltrechnungResponse:
    """Erfasst eine Zahlung (Standard: der ganze offene Betrag, heute). Ab hier zaehlt die Rechnung in
    Einnahmen-Ueberschuss-Rechnung und Umsatzsteuer, anteilig nach dem gezahlten Betrag."""
    sperre_mandant(db, auth["mandant_id"])  # serialisiert gleichzeitige Zahlungen auf dieselbe Rechnung
    altrechnung = get_scoped_or_404(db, Altrechnung, altrechnung_id, auth["mandant_id"])
    try:
        service.erfasse_zahlung(db, altrechnung, datum=payload.datum, betrag=payload.betrag, quelle="manuell", user_id=auth["sub"])
    except service.ZahlungAbgelehnt as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(altrechnung)
    return _antwort(altrechnung, _name(db, altrechnung))


# ---------------------------------------------------------------------------
# PDF-Archiv


def _lies_pdf(datei: UploadFile) -> tuple[bytes | None, str | None]:
    """(Inhalt, Ablehnungsgrund)."""
    grenze = settings.altrechnung_pdf_max_bytes
    daten = datei.file.read(grenze + 1)
    if len(daten) > grenze:
        return None, f"Die Datei ist zu groß (maximal {grenze // (1024 * 1024)} MB)."
    if not daten:
        return None, "Die Datei ist leer."
    if erkenne_dateityp(daten) != "application/pdf":
        return None, "Das ist keine PDF-Datei."
    return daten, None


def _speichere(db: Session, altrechnung: Altrechnung, daten: bytes, user_id: str | None) -> None:
    datei_hash = hashlib.sha256(daten).hexdigest()
    altrechnung.datei_referenz = storage.speichere_pdf(altrechnung.mandant_id, datei_hash, daten)
    altrechnung.datei_hash = datei_hash
    altrechnung.datei_hinzugefuegt_am = datetime.now(timezone.utc)
    record_audit(db, aktion="altrechnung_pdf", mandant_id=altrechnung.mandant_id, user_id=user_id, kontext=altrechnung.id)


@router.post("/pdfs", response_model=PdfAntwort)
def pdfs_zuordnen(
    files: list[UploadFile] = File(...), auth=Depends(require_full_auth), mandant: Mandant = Depends(_mandant),
    db: Session = Depends(get_db),
) -> PdfAntwort:
    """Legt mehrere PDFs ab und ordnet sie ueber die Rechnungsnummer im Dateinamen zu. Eindeutige
    Treffer werden sofort gespeichert, alles andere kommt mit Grund zurueck (zur Hand-Zuordnung
    ueber POST /altrechnungen/{id}/pdf)."""
    if len(files) > settings.altrechnung_pdf_max_dateien:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bitte höchstens {settings.altrechnung_pdf_max_dateien} Dateien auf einmal hochladen.",
        )
    zeilen = db.query(Altrechnung).options(defer(Altrechnung.steueranteile)).filter(Altrechnung.mandant_id == mandant.id).all()
    nach_id = {z.id: z for z in zeilen}
    zuordner = Zuordner([Kandidat(z.id, z.nummer) for z in zeilen])
    bekannte_hashes = {z.datei_hash: z.nummer for z in zeilen if z.datei_hash}

    ergebnisse: list[PdfErgebnis] = []
    for datei in files:
        name = Path(datei.filename or "unbenannt.pdf").name
        daten, grund = _lies_pdf(datei)
        if daten is None:
            ergebnisse.append(PdfErgebnis(dateiname=name, status="abgelehnt", grund=grund))
            continue
        datei_hash = hashlib.sha256(daten).hexdigest()
        if datei_hash in bekannte_hashes:
            ergebnisse.append(PdfErgebnis(
                dateiname=name, status="abgelehnt", grund=f"Diese Datei liegt schon bei Rechnung {bekannte_hashes[datei_hash]}.",
            ))
            continue
        art, treffer = zuordner.finde(name)
        if art == "keine":
            ergebnisse.append(PdfErgebnis(dateiname=name, status="keine", grund="Im Dateinamen steht keine bekannte Rechnungsnummer."))
        elif art == "unklar":
            ergebnisse.append(PdfErgebnis(
                dateiname=name, status="unklar", grund="Der Name passt zu mehreren Rechnungen: " + ", ".join(k.nummer for k in treffer),
            ))
        else:
            altrechnung = nach_id[treffer[0].id]
            if altrechnung.datei_referenz:
                ergebnisse.append(PdfErgebnis(
                    dateiname=name, status="abgelehnt", altrechnung_id=altrechnung.id, nummer=altrechnung.nummer,
                    grund=f"Rechnung {altrechnung.nummer} hat schon ein PDF. Archivierte Belege bleiben unverändert.",
                ))
                continue
            _speichere(db, altrechnung, daten, auth["sub"])
            bekannte_hashes[datei_hash] = altrechnung.nummer
            ergebnisse.append(PdfErgebnis(dateiname=name, status="zugeordnet", altrechnung_id=altrechnung.id, nummer=altrechnung.nummer))
    db.commit()
    return PdfAntwort(ergebnisse=ergebnisse)


@router.post("/{altrechnung_id}/pdf", response_model=AltrechnungResponse)
def pdf_zuordnen(
    altrechnung_id: str, file: UploadFile = File(...), auth=Depends(require_full_auth), mandant: Mandant = Depends(_mandant),
    db: Session = Depends(get_db),
) -> AltrechnungResponse:
    """Hand-Zuordnung eines PDFs zu einer Altrechnung ohne PDF."""
    altrechnung = get_scoped_or_404(db, Altrechnung, altrechnung_id, mandant.id)
    if altrechnung.datei_referenz:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rechnung {altrechnung.nummer} hat schon ein PDF. Archivierte Belege bleiben unverändert.",
        )
    daten, grund = _lies_pdf(file)
    if daten is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=grund)
    datei_hash = hashlib.sha256(daten).hexdigest()
    vorhanden = db.scalar(select(Altrechnung.nummer).where(Altrechnung.mandant_id == mandant.id, Altrechnung.datei_hash == datei_hash))
    if vorhanden:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Diese Datei liegt schon bei Rechnung {vorhanden}.")
    _speichere(db, altrechnung, daten, auth["sub"])
    db.commit()
    db.refresh(altrechnung)
    return _antwort(altrechnung, _name(db, altrechnung))


@router.get("/{altrechnung_id}/pdf")
def pdf_ansehen(altrechnung_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    altrechnung = get_scoped_or_404(db, Altrechnung, altrechnung_id, auth["mandant_id"])
    if not altrechnung.datei_referenz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zu dieser Rechnung gibt es kein PDF.")
    try:
        daten = storage.lies(altrechnung.datei_referenz)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Das PDF ist nicht mehr im Dateispeicher vorhanden.") from exc
    return Response(
        content=daten, media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="altrechnung-{altrechnung.id}.pdf"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# Kontakt-Historie


@kontakt_router.get("/{kontakt_id}/historie", response_model=HistorieResponse)
def kontakt_historie(kontakt_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> HistorieResponse:
    """Alle Rechnungen eines Kontakts, die aus Bilantiq und die aus dem Altsystem, mit Umsatz.
    Der Umsatz ist die Summe der Bruttobetraege (ohne Stornos und Entwuerfe), nicht der gezahlte
    Betrag, und enthaelt bewusst auch die Altsystem-Zeit: hier geht es um die Kundenbeziehung, nicht um die Buchfuehrung."""
    kontakt = get_scoped_or_404(db, Kontakt, kontakt_id, auth["mandant_id"])
    eintraege: list[HistorieEintrag] = []
    umsatz_bilantiq = umsatz_alt = offen = Decimal("0")

    for rechnung in db.query(Invoice).filter(Invoice.mandant_id == kontakt.mandant_id, Invoice.kontakt_id == kontakt.id):
        anzeige = _anzeige_status(rechnung)
        rest = rechnung.brutto_gesamt if anzeige in ("final", "ueberfaellig") else Decimal("0")
        if anzeige in ("final", "ueberfaellig", "bezahlt"):
            umsatz_bilantiq += rechnung.brutto_gesamt
        offen += rest
        eintraege.append(HistorieEintrag(
            art="bilantiq", id=rechnung.id, nummer=rechnung.nummer, datum=rechnung.leistungsdatum,
            brutto=rechnung.brutto_gesamt, offen=rest, status=anzeige,
        ))
    for altrechnung in (
        db.query(Altrechnung)
        .options(selectinload(Altrechnung.zahlungen), defer(Altrechnung.steueranteile))
        .filter(Altrechnung.mandant_id == kontakt.mandant_id, Altrechnung.kontakt_id == kontakt.id)
    ):
        rest = service.restbetrag(altrechnung)
        umsatz_alt += altrechnung.brutto
        offen += rest
        eintraege.append(HistorieEintrag(
            art="altsystem", id=altrechnung.id, nummer=altrechnung.nummer, datum=altrechnung.rechnungsdatum,
            brutto=altrechnung.brutto, offen=rest, status=service.status(altrechnung),
        ))
    eintraege.sort(key=lambda e: e.datum, reverse=True)
    return HistorieResponse(
        kontakt_id=kontakt.id, eintraege=eintraege, umsatz_brutto_bilantiq=umsatz_bilantiq,
        umsatz_brutto_altsystem=umsatz_alt, offen_brutto=offen,
    )
