import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core.kontenrahmen import ausgaben_konto
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.receipts import storage
from app.receipts.ai_extraction import ReceiptExtractor, get_extractor
from app.receipts.accounting import SUPPORTED_VAT_RATES
from app.bank import service as bank_service
from app.receipts.lernen import HistorieIndex, effektive_vorschlaege
from app.receipts.models import Ausgabe, AusgabeSteueranteil, Receipt
from app.receipts.schemas import (
    AusgabeResponse, BestaetigungRequest, FieldValue, LernVorschlagResponse, ReceiptResponse, SteueranteilResponse,
)
from app.receipts.service import ErfassungsFehler, erfasse_beleg, ist_unklar

router = APIRouter(prefix="/belege", tags=["receipts"])


_is_unklar = ist_unklar


def _historie(db: Session, mandant: Mandant) -> HistorieIndex:
    """Aus frueheren Buchungen gelernte Vorschlaege des Mandanten."""
    return HistorieIndex.laden(db, mandant.id)


def _field(wert, confidence: float | None) -> FieldValue:
    unklar = _is_unklar(confidence)
    return FieldValue(wert=None if unklar else (str(wert) if wert is not None else None), confidence=confidence, unklar=unklar)


def _receipt_response(
    receipt: Receipt,
    *,
    ist_duplikat: bool = False,
    duplikat_von: str | None = None,
    historie: HistorieIndex | None = None,
    zahlungsdatum: date | None = None,
) -> ReceiptResponse:
    eff = effektive_vorschlaege(receipt, historie)
    zusatz = json.loads(receipt.e_rechnung_daten) if receipt.e_rechnung_daten else {}
    anteile = zusatz.get("steueranteile", [])
    return ReceiptResponse(
        id=receipt.id, status=receipt.status, hochgeladen_am=receipt.hochgeladen_am.isoformat(),
        betrag=_field(receipt.betrag, receipt.betrag_confidence),
        datum=_field(receipt.datum, receipt.datum_confidence),
        anbieter=_field(receipt.anbieter, receipt.anbieter_confidence),
        ust_satz=_field(eff.ust_satz, eff.ust_confidence) if eff else _field(receipt.ust_satz, receipt.ust_satz_confidence),
        kategorie_vorschlag=_field(eff.kategorie, eff.kategorie_confidence) if eff else _field(None, None),
        begruendung=eff.begruendung if eff else None,
        buchungskonto_vorschlag=eff.konto if eff else None,
        gebucht_als=receipt.gebucht_als, ist_duplikat=ist_duplikat, duplikat_von=duplikat_von,
        beleg_typ=receipt.beleg_typ,
        rechnungsnummer=receipt.rechnungsnummer,
        faelligkeit=receipt.faelligkeit.isoformat() if receipt.faelligkeit else None,
        iban=receipt.iban,
        # Ein einzelner Satz steckt schon im Feld ust_satz; eine Aufteilung nur bei mehreren.
        steueranteile_vorschlag=[SteueranteilResponse(**anteil) for anteil in anteile] if len(anteile) > 1 else None,
        hinweise=zusatz.get("hinweise", []),
        zahlungsdatum_vorschlag=zahlungsdatum.isoformat() if zahlungsdatum else None,
    )


def _ausgabe_response(ausgabe: Ausgabe) -> AusgabeResponse:
    return AusgabeResponse(
        id=ausgabe.id,
        receipt_id=ausgabe.receipt_id,
        betrag=ausgabe.betrag,
        datum=ausgabe.datum,
        zahlungsdatum=ausgabe.zahlungsdatum,
        anbieter=ausgabe.anbieter,
        ust_satz=ausgabe.ust_satz,
        steueranteile=[
            {"ust_satz": anteil.ust_satz, "bruttobetrag": anteil.bruttobetrag}
            for anteil in ausgabe.steueranteile
        ],
        kategorie=ausgabe.kategorie,
        konto=ausgabe.konto,
    )


@router.post("", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
def upload_beleg(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
    extractor: ReceiptExtractor = Depends(get_extractor),
) -> ReceiptResponse:
    grenze = settings.receipt_max_bytes
    daten = file.file.read(grenze + 1)
    if len(daten) > grenze:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Die Datei ist zu groß (maximal {grenze // (1024 * 1024)} MB).",
        )
    try:
        erfassung = erfasse_beleg(
            db,
            mandant_id=auth["mandant_id"],
            daten=daten,
            deklarierter_typ=file.content_type,
            user_id=auth["sub"],
            extractor=extractor,
            force=force,
        )
    except ErfassungsFehler as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _receipt_response(
        erfassung.receipt,
        ist_duplikat=erfassung.duplikat,
        duplikat_von=erfassung.receipt.id if erfassung.duplikat else None,
        historie=_historie(db, erfassung.mandant),
        zahlungsdatum=bank_service.zahlungsdatum_fuer_beleg(db, erfassung.mandant.id, erfassung.receipt.id),
    )


@router.get("", response_model=list[ReceiptResponse])
def list_belege(auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> list[ReceiptResponse]:
    mandant = db.get(Mandant, auth["mandant_id"])
    belege = (
        db.query(Receipt).filter(Receipt.mandant_id == auth["mandant_id"]).order_by(Receipt.hochgeladen_am.desc()).all()
    )
    historie = _historie(db, mandant)
    zahlungsdaten = bank_service.zahlungsdaten_fuer_belege(db, mandant.id)
    return [
        _receipt_response(
            b, historie=historie, zahlungsdatum=zahlungsdaten.get(b.id),
        )
        for b in belege
    ]


@router.get("/vorschlag", response_model=LernVorschlagResponse)
def get_lernvorschlag(
    anbieter: str = Query(min_length=1, max_length=255),
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
) -> LernVorschlagResponse:
    """Vorschlag aus frueheren Buchungen, waehrend der Nutzer im Bestaetigungsformular
    den Anbieter anpasst."""
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    lern = HistorieIndex.laden(db, mandant.id).vorschlag(anbieter)
    if lern is None:
        return LernVorschlagResponse(gefunden=False)
    return LernVorschlagResponse(
        gefunden=True, kategorie=lern.kategorie, konto=lern.konto,
        ust_satz=str(lern.ust_satz) if lern.ust_satz is not None else None,
        confidence=lern.confidence, begruendung=lern.begruendung,
    )


@router.get("/{beleg_id}/datei")
def get_beleg_datei(beleg_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> Response:
    """Liefert den Originalbeleg nur innerhalb des aktuellen Mandanten aus."""
    receipt = get_scoped_or_404(db, Receipt, beleg_id, auth["mandant_id"])
    try:
        data = storage.read(receipt.datei_referenz)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Originalbeleg ist nicht mehr im Dateispeicher vorhanden.",
        ) from exc
    media_type = storage.mime_type_for_reference(receipt.datei_referenz)
    # XML nie inline ausliefern: Es ist ein Datensatz zum Herunterladen, keine Seite.
    anzeige = "attachment" if media_type == "application/xml" else "inline"
    endung = ".xml" if media_type == "application/xml" else ""
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'{anzeige}; filename="beleg-{receipt.id}{endung}"'},
    )


@router.get("/{beleg_id}", response_model=ReceiptResponse)
def get_beleg(beleg_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> ReceiptResponse:
    mandant = db.get(Mandant, auth["mandant_id"])
    receipt = get_scoped_or_404(db, Receipt, beleg_id, auth["mandant_id"])
    return _receipt_response(
        receipt, historie=_historie(db, mandant),
        zahlungsdatum=bank_service.zahlungsdatum_fuer_beleg(db, mandant.id, receipt.id),
    )


@router.delete("/{beleg_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_beleg(beleg_id: str, auth=Depends(require_full_auth), db: Session = Depends(get_db)) -> None:
    receipt = get_scoped_or_404(db, Receipt, beleg_id, auth["mandant_id"])
    if receipt.status == "gebucht":
        # Wie Ausgabe (siehe models.py): einmal gebucht, nicht mehr loeschbar --
        # sonst liesse sich eine bereits gebuchte Ausgabe rueckwirkend aus der
        # Beleg-Historie tilgen, obwohl die Buchung selbst bestehen bleibt.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Beleg ist bereits gebucht und kann aus Nachvollziehbarkeitsgruenden nicht geloescht werden.",
        )
    bank_service.loese_beleg_zuordnung(db, auth["mandant_id"], receipt.id)
    db.delete(receipt)
    record_audit(db, aktion="beleg_geloescht", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=beleg_id)
    db.commit()


@router.post("/{beleg_id}/bestaetigen", response_model=AusgabeResponse, status_code=status.HTTP_201_CREATED)
def bestaetige_beleg(
    beleg_id: str, payload: BestaetigungRequest, auth=Depends(require_full_auth), db: Session = Depends(get_db)
) -> AusgabeResponse:
    mandant = db.get(Mandant, auth["mandant_id"])
    receipt = get_scoped_or_404(db, Receipt, beleg_id, auth["mandant_id"])
    if receipt.status == "gebucht":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Beleg ist bereits gebucht.")
    historie = _historie(db, mandant)
    eff = effektive_vorschlaege(receipt, historie)

    betrag = payload.betrag if payload.betrag is not None else (None if _is_unklar(receipt.betrag_confidence) else receipt.betrag)
    datum = payload.datum if payload.datum is not None else (None if _is_unklar(receipt.datum_confidence) else receipt.datum)
    anbieter = payload.anbieter if payload.anbieter is not None else (None if _is_unklar(receipt.anbieter_confidence) else receipt.anbieter)
    zahlungsdatum = payload.zahlungsdatum or bank_service.zahlungsdatum_fuer_beleg(db, auth["mandant_id"], receipt.id) or datum
    ust_satz = payload.ust_satz if payload.ust_satz is not None else (None if _is_unklar(receipt.ust_satz_confidence) else receipt.ust_satz)
    if ust_satz is None and eff is not None and not payload.steueranteile and not _is_unklar(eff.ust_confidence):
        ust_satz = eff.ust_satz
    steueranteile = payload.steueranteile
    if steueranteile and payload.ust_satz is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entweder einen USt-Satz oder eine USt-Aufteilung angeben, nicht beides.",
        )
    if steueranteile:
        if len({anteil.ust_satz for anteil in steueranteile}) != len(steueranteile):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Jeder USt-Satz darf in der Aufteilung nur einmal vorkommen.",
            )
        if any(anteil.ust_satz not in SUPPORTED_VAT_RATES for anteil in steueranteile):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USt-Aufteilung unterstützt derzeit nur 0 %, 7 % und 19 %.",
            )
        if any(anteil.bruttobetrag <= 0 for anteil in steueranteile):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Jeder Bruttobetrag der USt-Aufteilung muss größer als 0 sein.",
            )
        if sum((anteil.bruttobetrag for anteil in steueranteile), Decimal("0")) != betrag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Die Bruttobeträge der USt-Aufteilung müssen zusammen dem Gesamtbetrag entsprechen.",
            )
        ust_satz = steueranteile[0].ust_satz if len(steueranteile) == 1 else None
    elif ust_satz is not None:
        if ust_satz not in SUPPORTED_VAT_RATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="USt-Satz unterstützt derzeit nur 0 %, 7 % und 19 %.",
            )
    kategorie = payload.kategorie
    if kategorie is None and eff is not None:
        kategorie = None if _is_unklar(eff.kategorie_confidence) else eff.kategorie
    konto = payload.konto
    if konto is None and eff is not None and kategorie is not None:
        # Das gelernte Konto gilt nur, wenn auch die gelernte Kategorie uebernommen wurde.
        konto = eff.konto if (payload.kategorie is None and eff.gelernt) else ausgaben_konto(kategorie)

    fehlend = [
        name for name, wert in [
            ("betrag", betrag), ("datum", datum), ("zahlungsdatum", zahlungsdatum), ("anbieter", anbieter),
            ("ust_satz_oder_aufteilung", ust_satz if not steueranteile else True),
            ("kategorie", kategorie), ("konto", konto),
        ] if wert is None
    ]
    if fehlend:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Diese Felder sind unklar und muessen vor der Buchung angegeben werden: {', '.join(fehlend)}",
        )

    ausgabe = Ausgabe(
        mandant_id=auth["mandant_id"], receipt_id=receipt.id, betrag=betrag, datum=datum,
        zahlungsdatum=zahlungsdatum, anbieter=anbieter, ust_satz=ust_satz,
        kategorie=kategorie, konto=konto,
    )
    db.add(ausgabe)
    db.flush()
    anteile = steueranteile or (
        [{"ust_satz": ust_satz, "bruttobetrag": betrag}] if ust_satz is not None else []
    )
    for anteil in anteile:
        if isinstance(anteil, dict):
            satz, brutto = anteil["ust_satz"], anteil["bruttobetrag"]
        else:
            satz, brutto = anteil.ust_satz, anteil.bruttobetrag
        db.add(AusgabeSteueranteil(
            mandant_id=auth["mandant_id"],
            ausgabe_id=ausgabe.id,
            bruttobetrag=brutto,
            ust_satz=satz,
        ))

    receipt.status = "gebucht"
    receipt.gebucht_als = ausgabe.id
    bank_service.verknuepfe_beleg_mit_ausgabe(db, auth["mandant_id"], receipt.id, ausgabe.id)
    record_audit(db, aktion="beleg_gebucht", mandant_id=auth["mandant_id"], user_id=auth["sub"], kontext=f"{ausgabe.id} konto {konto}")
    db.commit()

    db.refresh(ausgabe)
    return _ausgabe_response(ausgabe)
