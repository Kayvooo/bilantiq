"""Stammdaten importieren und exportieren (Kontakte, Produkte). Nur fuer den Inhaber, weil
ein Export den kompletten Kundenstamm enthaelt."""
from __future__ import annotations

import csv
import hashlib
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_owner
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core.tabelle import Tabelle, TabellenFehler, lese_tabelle
from app.db import get_db
from app.stammdaten import export, service
from app.stammdaten.felder import FELDER, schlage_zuordnung_vor
from app.stammdaten.models import Datenimport
from app.stammdaten.schemas import (
    FeldInfo, ImportAntwort, ImportProtokoll, PruefAntwort, RueckgaengigAntwort, VorschauAntwort, ZeileAntwort,
)

router = APIRouter(prefix="/stammdaten", tags=["stammdaten"])

Ziel = Literal["kontakte", "produkte", "rechnungen"]
ExportZiel = Literal["kontakte", "produkte"]
MAX_ZEILEN_IN_ANTWORT = 500


def _lies_datei(datei: UploadFile) -> bytes:
    grenze = settings.import_max_bytes
    daten = datei.file.read(grenze + 1)
    if len(daten) > grenze:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Die Datei ist zu groß (maximal {grenze // (1024 * 1024)} MB).",
        )
    if not daten:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Die Datei ist leer.")
    return daten


def _optionen(roh: str | None) -> service.Optionen:
    if not roh:
        return service.Optionen()
    try:
        return service.Optionen.model_validate_json(roh)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Die Importeinstellungen sind ungültig.") from exc


def _tabelle(daten: bytes, optionen: service.Optionen) -> Tabelle:
    try:
        return lese_tabelle(daten, blatt=optionen.blatt, kodierung=optionen.kodierung, trennzeichen=optionen.trennzeichen)
    except TabellenFehler as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _antwort(bericht: service.Bericht) -> PruefAntwort:
    felder = {feld.schluessel: feld for feld in FELDER[bericht.ziel]}
    auffaellig = [zeile for zeile in bericht.zeilen if zeile.status != "neu" or zeile.hinweise]
    beispiele = [
        {felder[schluessel].label: export._als_text(felder[schluessel], wert) for schluessel, wert in zeile.werte.items() if schluessel in felder}
        for zeile in bericht.zeilen if zeile.status == "neu"
    ][:5]
    return PruefAntwort(
        ziel=bericht.ziel, anzahl_zeilen=len(bericht.zeilen),
        neu=bericht.anzahl("neu"), ergaenzen=bericht.anzahl("ergaenzen"), vorhanden=bericht.anzahl("vorhanden"),
        doppelt=bericht.anzahl("doppelt"), fehler=bericht.anzahl("fehler"),
        mit_hinweisen=sum(1 for zeile in bericht.zeilen if zeile.hinweise),
        zeilen=[
            ZeileAntwort(
                nummer=z.nummer, status=z.status, anzeige=z.anzeige, grund=z.grund, fehler=z.fehler, hinweise=z.hinweise,
                ergaenzt=z.ergaenzt,
            )
            for z in auffaellig[:MAX_ZEILEN_IN_ANTWORT]
        ],
        beispiele=beispiele,
    )


def _pruefe_oder_400(db: Session, mandant_id: str, ziel: str, tabelle: Tabelle, optionen: service.Optionen) -> service.Bericht:
    try:
        return service.pruefe(db, mandant_id=mandant_id, ziel=ziel, tabelle=tabelle, optionen=optionen)
    except service.ImportAbgelehnt as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{ziel}/import/vorschau", response_model=VorschauAntwort)
def import_vorschau(
    ziel: Ziel, file: UploadFile = File(...), optionen: str | None = Form(None), auth=Depends(require_owner),
) -> VorschauAntwort:
    einstellungen = _optionen(optionen)
    tabelle = _tabelle(_lies_datei(file), einstellungen)
    zuordnung = schlage_zuordnung_vor(ziel, tabelle.kopf, tabelle.zeilen)
    return VorschauAntwort(
        format=tabelle.format, kodierung=tabelle.kodierung, trennzeichen=tabelle.trennzeichen, blatt=tabelle.blatt,
        blaetter=tabelle.blaetter, kopfzeilen=tabelle.kopf, beispielzeilen=tabelle.zeilen[:5],
        anzahl_zeilen=len(tabelle.zeilen), vorgeschlagene_zuordnung=zuordnung,
        dezimal_vorschlag=service.schlage_dezimal_fuer_zuordnung_vor(ziel, tabelle, zuordnung),
        felder=[FeldInfo(schluessel=f.schluessel, label=f.label, pflicht=f.pflicht, typ=f.typ) for f in FELDER[ziel]],
    )


@router.post("/{ziel}/import/pruefen", response_model=PruefAntwort)
def import_pruefen(
    ziel: Ziel, file: UploadFile = File(...), optionen: str = Form(...), auth=Depends(require_owner),
    db: Session = Depends(get_db),
) -> PruefAntwort:
    einstellungen = _optionen(optionen)
    tabelle = _tabelle(_lies_datei(file), einstellungen)
    return _antwort(_pruefe_oder_400(db, auth["mandant_id"], ziel, tabelle, einstellungen))


@router.post("/{ziel}/import/fehlerliste")
def import_fehlerliste(
    ziel: Ziel, file: UploadFile = File(...), optionen: str = Form(...), auth=Depends(require_owner),
    db: Session = Depends(get_db),
) -> Response:
    """Die Originalzeilen mit Fehlern oder Hinweisen plus eine Spalte "Fehler", zum Korrigieren
    und erneuten Hochladen."""
    einstellungen = _optionen(optionen)
    tabelle = _tabelle(_lies_datei(file), einstellungen)
    bericht = _pruefe_oder_400(db, auth["mandant_id"], ziel, tabelle, einstellungen)
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow([*tabelle.kopf, "Fehler"])
    for zeile in bericht.zeilen:
        if zeile.fehler or zeile.hinweise:
            original = tabelle.zeilen[zeile.nummer - 2]
            schreiber.writerow([*(export.entschaerfe(wert) for wert in original), "; ".join(zeile.fehler + zeile.hinweise)])
    return Response(
        content=("﻿" + puffer.getvalue()).encode("utf-8"), media_type=export.MEDIA_TYPEN["csv"],
        headers={"Content-Disposition": f'attachment; filename="fehlerliste-{ziel}.csv"'},
    )


@router.post("/{ziel}/import", response_model=ImportAntwort)
def importieren(
    ziel: Ziel, file: UploadFile = File(...), optionen: str = Form(...), auth=Depends(require_owner),
    db: Session = Depends(get_db),
) -> ImportAntwort:
    einstellungen = _optionen(optionen)
    daten = _lies_datei(file)
    tabelle = _tabelle(daten, einstellungen)
    try:
        protokoll, bericht = service.importiere(
            db, mandant_id=auth["mandant_id"], user_id=auth["sub"], ziel=ziel, tabelle=tabelle, optionen=einstellungen,
            dateiname=file.filename or "", datei_hash=hashlib.sha256(daten).hexdigest(), datei_inhalt=daten,
        )
    except service.ImportAbgelehnt as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ImportAntwort(import_id=protokoll.id, **_antwort(bericht).model_dump())


@router.get("/importe", response_model=list[ImportProtokoll])
def liste_importe(auth=Depends(require_owner), db: Session = Depends(get_db)) -> list[ImportProtokoll]:
    protokolle = (
        db.query(Datenimport).filter(Datenimport.mandant_id == auth["mandant_id"]).order_by(Datenimport.erstellt_am.desc()).limit(50)
    )
    return [
        ImportProtokoll(
            id=p.id, ziel=p.ziel, dateiname=p.dateiname, erstellt_am=p.erstellt_am, anzahl_neu=p.anzahl_neu,
            anzahl_ergaenzt=p.anzahl_ergaenzt, anzahl_uebersprungen=p.anzahl_uebersprungen, anzahl_fehler=p.anzahl_fehler,
            rueckgaengig_am=p.rueckgaengig_am,
        )
        for p in protokolle
    ]


@router.post("/importe/{import_id}/rueckgaengig", response_model=RueckgaengigAntwort)
def rueckgaengig(import_id: str, auth=Depends(require_owner), db: Session = Depends(get_db)) -> RueckgaengigAntwort:
    protokoll = db.get(Datenimport, import_id)
    if protokoll is None or protokoll.mandant_id != auth["mandant_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nicht gefunden.")
    try:
        geloescht, behalten = service.mache_rueckgaengig(db, mandant_id=auth["mandant_id"], user_id=auth["sub"], protokoll=protokoll)
    except service.ImportAbgelehnt as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return RueckgaengigAntwort(geloescht=geloescht, behalten=behalten)


@router.get("/{ziel}/export")
def exportieren(
    ziel: ExportZiel, format: Literal["csv", "xlsx"] = Query("csv"), auth=Depends(require_owner), db: Session = Depends(get_db),
) -> Response:
    inhalt, dateiname = export.exportiere(db, mandant_id=auth["mandant_id"], ziel=ziel, format_=format)
    record_audit(db, aktion="stammdaten_export", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=f"{ziel} {format}")
    db.commit()
    return Response(
        content=inhalt, media_type=export.MEDIA_TYPEN[format],
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"', "Cache-Control": "no-store"},
    )


@router.get("/{ziel}/vorlage")
def importvorlage(ziel: Ziel, format: Literal["csv", "xlsx"] = Query("csv"), auth=Depends(require_owner)) -> Response:
    inhalt, dateiname = export.vorlage(ziel=ziel, format_=format)
    return Response(
        content=inhalt, media_type=export.MEDIA_TYPEN[format],
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )
