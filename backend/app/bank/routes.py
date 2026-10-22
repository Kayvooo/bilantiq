from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.bank import service
from app.bank.models import Bankimport, Bankkonto, Bankumsatz
from app.bank.parser_camt import lese_camt
from app.bank.parser_csv import CsvProfil, vorschau_csv
from app.bank.rohdaten import ImportFehler
from app.bank.schemas import (
    BestaetigenErgebnis, BestaetigenRequest, IgnorierenRequest, ImportErgebnis, ImportVorschau, KontoCreate,
    KontoResponse, Uebersprungen, UmsatzListe, UmsatzResponse, VorschlagResponse, ZuordnenRequest, Zusammenfassung,
)
from app.config import settings
from app.core.audit_log import record as record_audit
from app.db import get_db
from app.receipts.service import erkenne_dateityp

router = APIRouter(prefix="/bank", tags=["bank"])


def _mandant(auth: dict = Depends(require_full_auth), db: Session = Depends(get_db)) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


def _konto_oder_404(db: Session, mandant: Mandant, konto_id: str) -> Bankkonto:
    konto = db.get(Bankkonto, konto_id)
    if konto is None or konto.mandant_id != mandant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bankkonto nicht gefunden.")
    return konto


def _konto_response(db: Session, konto: Bankkonto) -> KontoResponse:
    anzahl = db.scalar(select(func.count()).select_from(Bankumsatz).where(Bankumsatz.bankkonto_id == konto.id)) or 0
    return KontoResponse(
        id=konto.id, bezeichnung=konto.bezeichnung, iban=konto.iban,
        csv_profil=service.profil_aus_json(konto.csv_profil), anzahl_umsaetze=anzahl,
    )


def _lies_datei(datei: UploadFile) -> bytes:
    grenze = settings.bank_max_bytes
    daten = datei.file.read(grenze + 1)
    if len(daten) > grenze:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Die Datei ist zu groß (maximal {grenze // (1024 * 1024)} MB).",
        )
    return daten


def _format(daten: bytes) -> str:
    typ = erkenne_dateityp(daten)
    if typ == "application/xml":
        return "camt"
    if typ is None:
        return "csv"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Bitte einen Kontoauszug als CAMT.053 (XML) oder als CSV-Datei hochladen.",
    )


@router.post("/konten", response_model=KontoResponse, status_code=status.HTTP_201_CREATED)
def lege_konto_an(payload: KontoCreate, mandant: Mandant = Depends(_mandant), db: Session = Depends(get_db)) -> KontoResponse:
    iban = payload.iban.replace(" ", "").upper() if payload.iban else None
    konto = Bankkonto(
        mandant_id=mandant.id, bezeichnung=payload.bezeichnung.strip(), iban=iban,
        iban_hash=service.iban_hash(mandant.id, iban) if iban else None,
    )
    db.add(konto)
    db.commit()
    return _konto_response(db, konto)


@router.get("/konten", response_model=list[KontoResponse])
def liste_konten(mandant: Mandant = Depends(_mandant), db: Session = Depends(get_db)) -> list[KontoResponse]:
    konten = db.query(Bankkonto).filter(Bankkonto.mandant_id == mandant.id).order_by(Bankkonto.erstellt_am).all()
    return [_konto_response(db, konto) for konto in konten]


@router.post("/konten/{konto_id}/import/vorschau", response_model=ImportVorschau)
def import_vorschau(
    konto_id: str, file: UploadFile = File(...), mandant: Mandant = Depends(_mandant), db: Session = Depends(get_db),
) -> ImportVorschau:
    konto = _konto_oder_404(db, mandant, konto_id)
    daten = _lies_datei(file)
    try:
        if _format(daten) == "camt":
            auszug = lese_camt(daten)
            return ImportVorschau(
                format="camt", anzahl=len(auszug.umsaetze),
                zeitraum_von=min(u.buchungsdatum for u in auszug.umsaetze),
                zeitraum_bis=max(u.buchungsdatum for u in auszug.umsaetze),
                beispiele=[
                    {"datum": u.buchungsdatum.isoformat(), "betrag": f"{u.betrag:.2f}", "name": u.gegenpartei_name or "",
                     "zweck": u.verwendungszweck}
                    for u in auszug.umsaetze[:5]
                ],
            )
        csv_vorschau = vorschau_csv(daten)
    except ImportFehler as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ImportVorschau(
        format="csv", anzahl=csv_vorschau.anzahl_zeilen, csv=csv_vorschau,
        gespeichertes_profil=service.profil_aus_json(konto.csv_profil),
    )


@router.post("/konten/{konto_id}/import", response_model=ImportErgebnis, status_code=status.HTTP_201_CREATED)
def importiere_auszug(
    konto_id: str,
    file: UploadFile = File(...),
    profil: str | None = Form(None),
    mandant: Mandant = Depends(_mandant),
    auth: dict = Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> ImportErgebnis:
    konto = _konto_oder_404(db, mandant, konto_id)
    daten = _lies_datei(file)
    format_ = _format(daten)
    csv_profil = None
    if format_ == "csv":
        try:
            csv_profil = CsvProfil.model_validate_json(profil) if profil else service.profil_aus_json(konto.csv_profil)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Das Spaltenprofil ist ungültig.") from exc
    try:
        ergebnis = service.importiere(
            db, mandant_id=mandant.id, konto=konto, daten=daten, dateiname=file.filename or "kontoauszug",
            format_=format_, profil=csv_profil, user_id=auth["sub"],
        )
    except ImportFehler as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return ImportErgebnis(
        import_id=ergebnis.id, format=format_, neu=ergebnis.anzahl_neu, doppelt=ergebnis.anzahl_doppelt,
        zeitraum_von=ergebnis.zeitraum_von, zeitraum_bis=ergebnis.zeitraum_bis,
    )


def _umsatz_response(
    db: Session, mandant_id: str, zeile: Bankumsatz, vorschlaege: dict[str, service.matching.Vorschlag],
) -> UmsatzResponse:
    vorschlag = vorschlaege.get(zeile.id)
    return UmsatzResponse(
        id=zeile.id, bankkonto_id=zeile.bankkonto_id, buchungsdatum=zeile.buchungsdatum, wertstellung=zeile.wertstellung,
        betrag=f"{zeile.betrag:.2f}", gegenpartei_name=zeile.gegenpartei_name, gegenpartei_iban=zeile.gegenpartei_iban,
        verwendungszweck=zeile.verwendungszweck or "", status=zeile.status, zuordnung_typ=zeile.zuordnung_typ,
        zuordnung_id=zeile.zuordnung_id, ignoriert_grund=zeile.ignoriert_grund,
        beleg_fehlt=zeile.status == "offen" and zeile.betrag < 0,
        vorschlag=VorschlagResponse(**vars(vorschlag)) if vorschlag else None,
    )


@router.get("/umsaetze", response_model=UmsatzListe)
def liste_umsaetze(
    status_filter: str = Query("offen", alias="status", pattern="^(offen|zugeordnet|ignoriert|beleg_fehlt|alle)$"),
    konto_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mandant: Mandant = Depends(_mandant),
    db: Session = Depends(get_db),
) -> UmsatzListe:
    abfrage = db.query(Bankumsatz).filter(Bankumsatz.mandant_id == mandant.id)
    if konto_id:
        abfrage = abfrage.filter(Bankumsatz.bankkonto_id == konto_id)
    if status_filter in {"offen", "zugeordnet", "ignoriert"}:
        abfrage = abfrage.filter(Bankumsatz.status == status_filter)
    elif status_filter == "beleg_fehlt":
        abfrage = abfrage.filter(Bankumsatz.status == "offen")
    zeilen = abfrage.order_by(Bankumsatz.buchungsdatum.desc(), Bankumsatz.erstellt_am.desc()).all()
    if status_filter == "beleg_fehlt":  # Betraege sind verschluesselt, der Filter laeuft deshalb hier
        zeilen = [z for z in zeilen if z.betrag < 0]
    seite = zeilen[offset:offset + limit]
    vorschlaege = service.berechne_vorschlaege(db, mandant.id, [z for z in seite if z.status == "offen"])
    return UmsatzListe(umsaetze=[_umsatz_response(db, mandant.id, z, vorschlaege) for z in seite], gesamt=len(zeilen))


@router.get("/zusammenfassung", response_model=Zusammenfassung)
def zusammenfassung(mandant: Mandant = Depends(_mandant), db: Session = Depends(get_db)) -> Zusammenfassung:
    zahlen = dict(db.execute(
        select(Bankumsatz.status, func.count()).where(Bankumsatz.mandant_id == mandant.id).group_by(Bankumsatz.status)
    ).all())
    offene = db.query(Bankumsatz).filter(Bankumsatz.mandant_id == mandant.id, Bankumsatz.status == "offen").all()
    vorschlaege = service.berechne_vorschlaege(db, mandant.id, offene)
    return Zusammenfassung(
        offen=zahlen.get("offen", 0), zugeordnet=zahlen.get("zugeordnet", 0), ignoriert=zahlen.get("ignoriert", 0),
        beleg_fehlt=sum(1 for u in offene if u.betrag < 0),
        sichere_vorschlaege=sum(1 for v in vorschlaege.values() if v.sicher),
    )


def _fehler(exc: service.ZuordnungsFehler) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/umsaetze/{umsatz_id}/zuordnen", response_model=UmsatzResponse)
def ordne_zu(
    umsatz_id: str, payload: ZuordnenRequest, mandant: Mandant = Depends(_mandant),
    auth: dict = Depends(require_full_auth), db: Session = Depends(get_db),
) -> UmsatzResponse:
    try:
        umsatz = service.ordne_zu(
            db, mandant_id=mandant.id, umsatz_id=umsatz_id, typ=payload.typ, ziel_id=payload.ziel_id, user_id=auth["sub"],
        )
    except service.ZuordnungsFehler as exc:
        db.rollback()
        raise _fehler(exc) from exc
    db.commit()
    return _umsatz_response(db, mandant.id, umsatz, {})


@router.post("/umsaetze/{umsatz_id}/ignorieren", response_model=UmsatzResponse)
def ignoriere_umsatz(
    umsatz_id: str, payload: IgnorierenRequest, mandant: Mandant = Depends(_mandant),
    auth: dict = Depends(require_full_auth), db: Session = Depends(get_db),
) -> UmsatzResponse:
    try:
        umsatz = service.ignoriere(db, mandant_id=mandant.id, umsatz_id=umsatz_id, grund=payload.grund.strip(), user_id=auth["sub"])
    except service.ZuordnungsFehler as exc:
        db.rollback()
        raise _fehler(exc) from exc
    db.commit()
    return _umsatz_response(db, mandant.id, umsatz, {})


@router.post("/umsaetze/{umsatz_id}/zuordnung-aufheben", response_model=UmsatzResponse)
def hebe_zuordnung_auf(
    umsatz_id: str, mandant: Mandant = Depends(_mandant), auth: dict = Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> UmsatzResponse:
    try:
        umsatz = service.hebe_auf(db, mandant_id=mandant.id, umsatz_id=umsatz_id, user_id=auth["sub"])
    except service.ZuordnungsFehler as exc:
        db.rollback()
        raise _fehler(exc) from exc
    db.commit()
    return _umsatz_response(db, mandant.id, umsatz, {})


@router.post("/zuordnungen/bestaetigen", response_model=BestaetigenErgebnis)
def bestaetige_sichere_zuordnungen(
    payload: BestaetigenRequest, mandant: Mandant = Depends(_mandant), auth: dict = Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> BestaetigenErgebnis:
    """Bestaetigt gesammelt die aktuellen *sicheren* Vorschlaege der genannten Umsaetze.
    Alles andere wird mit Begruendung uebersprungen, nichts wird geraten."""
    zeilen = db.query(Bankumsatz).filter(Bankumsatz.mandant_id == mandant.id, Bankumsatz.id.in_(payload.umsatz_ids)).all()
    vorhanden = {z.id: z for z in zeilen}
    vorschlaege = service.berechne_vorschlaege(db, mandant.id, [z for z in zeilen if z.status == "offen"])
    bestaetigt, uebersprungen = 0, []
    for umsatz_id in payload.umsatz_ids:
        zeile = vorhanden.get(umsatz_id)
        vorschlag = vorschlaege.get(umsatz_id)
        if zeile is None:
            uebersprungen.append(Uebersprungen(umsatz_id=umsatz_id, grund="Umsatz nicht gefunden."))
        elif zeile.status != "offen":
            uebersprungen.append(Uebersprungen(umsatz_id=umsatz_id, grund="Schon zugeordnet oder ignoriert."))
        elif vorschlag is None or not vorschlag.sicher:
            uebersprungen.append(Uebersprungen(umsatz_id=umsatz_id, grund="Kein sicherer Vorschlag."))
        else:
            try:
                with db.begin_nested():
                    service.ordne_zu(
                        db, mandant_id=mandant.id, umsatz_id=umsatz_id, typ=vorschlag.typ, ziel_id=vorschlag.ziel_id,
                        user_id=auth["sub"],
                    )
                bestaetigt += 1
            except service.ZuordnungsFehler as exc:
                uebersprungen.append(Uebersprungen(umsatz_id=umsatz_id, grund=exc.detail))
    db.commit()
    return BestaetigenErgebnis(bestaetigt=bestaetigt, uebersprungen=uebersprungen)
