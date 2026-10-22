import csv
import io
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth, require_owner
from app.auth.models import Mandant
from app.core.audit_log import record as record_audit
from app.core.crypto import decrypt_field, encrypt_field
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.payroll.models import LohnMonatsentwurf, Mitarbeiter
from app.payroll.pdf import render_lohnzettel_pdf
from app.payroll.schemas import (
    LohnMonatsentwurfCreate,
    LohnMonatsentwurfResponse,
    LohnMonatsentwurfUpdate,
    MitarbeiterCreate,
    MitarbeiterResponse,
    MitarbeiterUpdate,
)

# Gehaltsdaten und Lohnentwuerfe anderer Beschaeftigter: nur der Owner (Datenminimierung, Art. 5/32 DSGVO). Das gilt fuer
# jede Route des Routers; require_full_auth in den Handlern bleibt (FastAPI wertet die Abhaengigkeit nur einmal aus).
router = APIRouter(prefix="/lohn", tags=["payroll"], dependencies=[Depends(require_owner)])
CENT = Decimal("0.01")
PREPARATION_NOTICE = (
    "Lohnvorbereitung ohne Berechnung gesetzlicher Steuern und Sozialabgaben. "
    "Keine rechtsverbindliche Lohnabrechnung oder Meldung."
)


def _pruefe_mandant(db: Session, auth: dict) -> None:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _mitarbeiter_response(item: Mitarbeiter) -> MitarbeiterResponse:
    return MitarbeiterResponse(
        id=item.id,
        personalnummer=item.personalnummer,
        vorname=decrypt_field(item.vorname_encrypted),
        nachname=decrypt_field(item.nachname_encrypted),
        eintrittsdatum=item.eintrittsdatum,
        austrittsdatum=item.austrittsdatum,
        monatsbrutto=item.monatsbrutto,
        aktiv=item.aktiv,
    )


def _entwurf_response(item: LohnMonatsentwurf) -> LohnMonatsentwurfResponse:
    return LohnMonatsentwurfResponse(
        id=item.id,
        mitarbeiter_id=item.mitarbeiter_id,
        personalnummer=item.mitarbeiter.personalnummer,
        mitarbeiter_name=f"{decrypt_field(item.mitarbeiter.vorname_encrypted)} {decrypt_field(item.mitarbeiter.nachname_encrypted)}",
        jahr=item.jahr,
        monat=item.monat,
        grundbrutto=item.grundbrutto,
        steuerpflichtige_zuschlaege=item.steuerpflichtige_zuschlaege,
        steuerfreie_erstattungen=item.steuerfreie_erstattungen,
        sonstige_abzuege=item.sonstige_abzuege,
        gesamtbrutto=item.gesamtbrutto,
        zwischenbetrag_vor_abgaben=item.zwischenbetrag_vor_abgaben,
        status=item.status,
        abgeschlossen_am=item.abgeschlossen_am,
        hinweis=PREPARATION_NOTICE,
    )


@router.post("/mitarbeitende", response_model=MitarbeiterResponse, status_code=status.HTTP_201_CREATED)
def create_mitarbeiter(payload: MitarbeiterCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    exists = db.query(Mitarbeiter).filter(
        Mitarbeiter.mandant_id == mandant_id,
        Mitarbeiter.personalnummer == payload.personalnummer,
    ).first()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Personalnummer ist bereits vergeben.")

    item = Mitarbeiter(
        mandant_id=mandant_id,
        personalnummer=payload.personalnummer,
        vorname_encrypted=encrypt_field(payload.vorname),
        nachname_encrypted=encrypt_field(payload.nachname),
        eintrittsdatum=payload.eintrittsdatum,
        austrittsdatum=payload.austrittsdatum,
        monatsbrutto=_money(payload.monatsbrutto),
    )
    db.add(item)
    record_audit(db, aktion="mitarbeiter_angelegt", mandant_id=mandant_id, user_id=auth["sub"], kontext=payload.personalnummer)
    db.commit()
    return _mitarbeiter_response(item)


@router.get("/mitarbeitende", response_model=list[MitarbeiterResponse])
def list_mitarbeitende(auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    items = db.query(Mitarbeiter).filter(Mitarbeiter.mandant_id == auth["mandant_id"]).order_by(Mitarbeiter.personalnummer).all()
    return [_mitarbeiter_response(item) for item in items]


@router.post("/mitarbeitende/{mitarbeiter_id}/deaktivieren", response_model=MitarbeiterResponse)
def deactivate_mitarbeiter(mitarbeiter_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, Mitarbeiter, mitarbeiter_id, auth["mandant_id"])
    if not item.aktiv:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mitarbeitende Person ist bereits deaktiviert.")
    item.aktiv = False
    record_audit(db, aktion="mitarbeiter_deaktiviert", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=item.personalnummer)
    db.commit()
    return _mitarbeiter_response(item)


@router.post("/mitarbeitende/{mitarbeiter_id}/reaktivieren", response_model=MitarbeiterResponse)
def reactivate_mitarbeiter(mitarbeiter_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, Mitarbeiter, mitarbeiter_id, auth["mandant_id"])
    if item.aktiv:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mitarbeitende Person ist bereits aktiv.")
    item.aktiv = True
    record_audit(db, aktion="mitarbeiter_reaktiviert", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=item.personalnummer)
    db.commit()
    return _mitarbeiter_response(item)


@router.patch("/mitarbeitende/{mitarbeiter_id}", response_model=MitarbeiterResponse)
def update_mitarbeiter(mitarbeiter_id: str, payload: MitarbeiterUpdate, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, Mitarbeiter, mitarbeiter_id, auth["mandant_id"])
    updates = payload.model_dump(exclude_unset=True)

    neues_eintrittsdatum = updates.get("eintrittsdatum", item.eintrittsdatum)
    neues_austrittsdatum = updates.get("austrittsdatum", item.austrittsdatum)
    if neues_austrittsdatum is not None and neues_austrittsdatum < neues_eintrittsdatum:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Austrittsdatum darf nicht vor dem Eintrittsdatum liegen.")

    if "vorname" in updates:
        item.vorname_encrypted = encrypt_field(updates["vorname"])
    if "nachname" in updates:
        item.nachname_encrypted = encrypt_field(updates["nachname"])
    if "eintrittsdatum" in updates:
        item.eintrittsdatum = updates["eintrittsdatum"]
    if "austrittsdatum" in updates:
        item.austrittsdatum = updates["austrittsdatum"]
    if "monatsbrutto" in updates:
        item.monatsbrutto = _money(updates["monatsbrutto"])

    record_audit(db, aktion="mitarbeiter_bearbeitet", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=item.personalnummer)
    db.commit()
    return _mitarbeiter_response(item)


def _berechne_summen(grundbrutto: Decimal, zuschlaege: Decimal, erstattungen: Decimal, abzuege: Decimal) -> tuple[Decimal, Decimal]:
    gesamtbrutto = _money(grundbrutto + zuschlaege)
    zwischenbetrag = _money(gesamtbrutto + erstattungen - abzuege)
    if zwischenbetrag < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Sonstige Abzüge übersteigen die vorbereitete Auszahlung.")
    return gesamtbrutto, zwischenbetrag


def _validate_employment_month(item: Mitarbeiter, year: int, month: int) -> None:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    if item.eintrittsdatum > last or (item.austrittsdatum is not None and item.austrittsdatum < first):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Monat liegt außerhalb des Beschäftigungszeitraums.")


@router.post("/monatsentwuerfe", response_model=LohnMonatsentwurfResponse, status_code=status.HTTP_201_CREATED)
def create_monatsentwurf(payload: LohnMonatsentwurfCreate, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    mandant_id = auth["mandant_id"]
    mitarbeiter = get_scoped_or_404(db, Mitarbeiter, payload.mitarbeiter_id, mandant_id)
    if not mitarbeiter.aktiv:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deaktivierte Mitarbeitende können keine neuen Monatsentwürfe erhalten.")
    _validate_employment_month(mitarbeiter, payload.jahr, payload.monat)
    exists = db.query(LohnMonatsentwurf).filter(
        LohnMonatsentwurf.mandant_id == mandant_id,
        LohnMonatsentwurf.mitarbeiter_id == mitarbeiter.id,
        LohnMonatsentwurf.jahr == payload.jahr,
        LohnMonatsentwurf.monat == payload.monat,
    ).first()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Für diese Person und diesen Monat existiert bereits ein Entwurf.")

    grundbrutto = _money(payload.grundbrutto if payload.grundbrutto is not None else mitarbeiter.monatsbrutto)
    zuschlaege = _money(payload.steuerpflichtige_zuschlaege)
    erstattungen = _money(payload.steuerfreie_erstattungen)
    abzuege = _money(payload.sonstige_abzuege)
    gesamtbrutto, zwischenbetrag = _berechne_summen(grundbrutto, zuschlaege, erstattungen, abzuege)

    item = LohnMonatsentwurf(
        mandant_id=mandant_id,
        mitarbeiter_id=mitarbeiter.id,
        jahr=payload.jahr,
        monat=payload.monat,
        grundbrutto=grundbrutto,
        steuerpflichtige_zuschlaege=zuschlaege,
        steuerfreie_erstattungen=erstattungen,
        sonstige_abzuege=abzuege,
        gesamtbrutto=gesamtbrutto,
        zwischenbetrag_vor_abgaben=zwischenbetrag,
    )
    db.add(item)
    record_audit(db, aktion="lohn_monatsentwurf_angelegt", mandant_id=mandant_id, user_id=auth["sub"], kontext=f"{mitarbeiter.personalnummer}:{payload.jahr}-{payload.monat:02d}")
    db.commit()
    return _entwurf_response(item)


def _entwurf_kontext(item: LohnMonatsentwurf) -> str:
    return f"{item.mitarbeiter.personalnummer}:{item.jahr}-{item.monat:02d}"


@router.patch("/monatsentwuerfe/{entwurf_id}", response_model=LohnMonatsentwurfResponse)
def update_monatsentwurf(entwurf_id: str, payload: LohnMonatsentwurfUpdate, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, LohnMonatsentwurf, entwurf_id, auth["mandant_id"])
    if item.status != "vorbereitung":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Abgeschlossene Entwürfe können nicht direkt bearbeitet werden -- zuerst reaktivieren.",
        )
    updates = payload.model_dump(exclude_unset=True)
    grundbrutto = _money(updates.get("grundbrutto", item.grundbrutto))
    zuschlaege = _money(updates.get("steuerpflichtige_zuschlaege", item.steuerpflichtige_zuschlaege))
    erstattungen = _money(updates.get("steuerfreie_erstattungen", item.steuerfreie_erstattungen))
    abzuege = _money(updates.get("sonstige_abzuege", item.sonstige_abzuege))
    gesamtbrutto, zwischenbetrag = _berechne_summen(grundbrutto, zuschlaege, erstattungen, abzuege)

    item.grundbrutto = grundbrutto
    item.steuerpflichtige_zuschlaege = zuschlaege
    item.steuerfreie_erstattungen = erstattungen
    item.sonstige_abzuege = abzuege
    item.gesamtbrutto = gesamtbrutto
    item.zwischenbetrag_vor_abgaben = zwischenbetrag

    record_audit(db, aktion="lohn_monatsentwurf_bearbeitet", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=_entwurf_kontext(item))
    db.commit()
    return _entwurf_response(item)


@router.post("/monatsentwuerfe/{entwurf_id}/abschliessen", response_model=LohnMonatsentwurfResponse)
def abschliessen_monatsentwurf(entwurf_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    """Markiert die Vorbereitung als fertig fuer die Uebergabe an die Steuerkanzlei --
    keine rechtsverbindliche Lohnabrechnung, siehe verbindlicher_abschluss_verfuegbar
    in schemas.py."""
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, LohnMonatsentwurf, entwurf_id, auth["mandant_id"])
    if item.status != "vorbereitung":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dieser Entwurf ist bereits abgeschlossen.")
    item.status = "abgeschlossen"
    item.abgeschlossen_am = datetime.now(timezone.utc)
    record_audit(db, aktion="lohn_monatsentwurf_abgeschlossen", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=_entwurf_kontext(item))
    db.commit()
    return _entwurf_response(item)


@router.post("/monatsentwuerfe/{entwurf_id}/reaktivieren", response_model=LohnMonatsentwurfResponse)
def reaktivieren_monatsentwurf(entwurf_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    item = get_scoped_or_404(db, LohnMonatsentwurf, entwurf_id, auth["mandant_id"])
    if item.status != "abgeschlossen":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nur abgeschlossene Entwürfe können reaktiviert werden.")
    item.status = "vorbereitung"
    item.abgeschlossen_am = None
    record_audit(db, aktion="lohn_monatsentwurf_reaktiviert", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=_entwurf_kontext(item))
    db.commit()
    return _entwurf_response(item)


@router.get("/monatsentwuerfe/{entwurf_id}/lohnzettel")
def lohnzettel_pdf(entwurf_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    _pruefe_mandant(db, auth)
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    item = get_scoped_or_404(db, LohnMonatsentwurf, entwurf_id, auth["mandant_id"])
    pdf = render_lohnzettel_pdf(mandant, item.mitarbeiter, item, PREPARATION_NOTICE)
    dateiname = f"Lohnzettel-{item.mitarbeiter.personalnummer}-{item.jahr}-{item.monat:02d}.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{dateiname}"'})


@router.get("/monatsentwuerfe", response_model=list[LohnMonatsentwurfResponse])
def list_monatsentwuerfe(jahr: int | None = None, monat: int | None = None, auth=Depends(require_full_auth), db: Session = Depends(get_db)):
    _pruefe_mandant(db, auth)
    query = db.query(LohnMonatsentwurf).filter(LohnMonatsentwurf.mandant_id == auth["mandant_id"])
    if jahr is not None:
        query = query.filter(LohnMonatsentwurf.jahr == jahr)
    if monat is not None:
        if monat < 1 or monat > 12:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Monat muss zwischen 1 und 12 liegen.")
        query = query.filter(LohnMonatsentwurf.monat == monat)
    items = query.order_by(LohnMonatsentwurf.jahr.desc(), LohnMonatsentwurf.monat.desc()).all()
    return [_entwurf_response(item) for item in items]


@router.get("/monate/{jahr}/{monat}/export")
def export_month(jahr: int, monat: int, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    _pruefe_mandant(db, auth)
    if jahr < 2020 or jahr > 2100 or monat < 1 or monat > 12:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ungültiger Abrechnungsmonat.")
    items = db.query(LohnMonatsentwurf).filter(
        LohnMonatsentwurf.mandant_id == auth["mandant_id"],
        LohnMonatsentwurf.jahr == jahr,
        LohnMonatsentwurf.monat == monat,
    ).order_by(LohnMonatsentwurf.mitarbeiter_id).all()

    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Status", "Personalnummer", "Name", "Jahr", "Monat", "Grundbrutto", "Steuerpflichtige Zuschläge", "Steuerfreie Erstattungen", "Sonstige Abzüge", "Gesamtbrutto", "Zwischensumme vor gesetzlichen Abgaben", "Hinweis"])
    for item in items:
        writer.writerow([
            "VORBEREITUNG",
            item.mitarbeiter.personalnummer,
            f"{decrypt_field(item.mitarbeiter.vorname_encrypted)} {decrypt_field(item.mitarbeiter.nachname_encrypted)}",
            item.jahr,
            item.monat,
            f"{item.grundbrutto:.2f}",
            f"{item.steuerpflichtige_zuschlaege:.2f}",
            f"{item.steuerfreie_erstattungen:.2f}",
            f"{item.sonstige_abzuege:.2f}",
            f"{item.gesamtbrutto:.2f}",
            f"{item.zwischenbetrag_vor_abgaben:.2f}",
            PREPARATION_NOTICE,
        ])
    content = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="Lohnvorbereitung-{jahr}-{monat:02d}.csv"'})
