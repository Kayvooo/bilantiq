import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.ai.client import AiClient, AiResponseError, AiUnavailable, get_ai_client
from app.ai.prompts import (
    ASSISTANT_ANSWER_SYSTEM,
    ASSISTANT_PLANNER_SYSTEM,
    INVOICE_DRAFT_SYSTEM,
    QUOTE_DRAFT_SYSTEM,
    TEXT_SYSTEM,
)
from app.ai.schemas import (
    AssistantPlan,
    AssistantRequest,
    AssistantResponse,
    NaturalLanguageDraftRequest,
    TextSuggestionRequest,
    TextSuggestionResponse,
)
from app.ai.tools import execute_tool
from app.auth.dependencies import require_full_auth
from app.auth.models import Mandant
from app.buchhaltungseinstellungen.models import Buchhaltungseinstellungen
from app.core.audit_log import record as record_audit
from app.core.rls import get_scoped_or_404
from app.db import get_db
from app.invoices.models import Invoice, Kontakt
from app.invoices.schemas import InvoiceCreate
from app.mahnwesen.models import Mahnung
from app.mahnwesen.schemas import STUFE_BEZEICHNUNG
from app.quotes.models import Quote
from app.quotes.schemas import QuoteCreate

router = APIRouter(prefix="/ai", tags=["ai"])


def _lade_mandant(db: Session, auth: dict) -> Mandant:
    mandant = db.get(Mandant, auth["mandant_id"])
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mandant nicht gefunden.")
    return mandant


def _complete_json(ai: AiClient, messages: list[dict[str, str]], schema):
    try:
        return ai.complete_json(messages, schema)
    except AiUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Der lokale KI-Dienst ist derzeit nicht erreichbar.",
        ) from exc
    except AiResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Der lokale KI-Dienst hat keine gueltige strukturierte Antwort geliefert.",
        ) from exc


def _complete_text(ai: AiClient, messages: list[dict[str, str]]) -> str:
    try:
        return ai.complete_text(messages)
    except AiUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Der lokale KI-Dienst ist derzeit nicht erreichbar.",
        ) from exc
    except AiResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Der lokale KI-Dienst hat keine gueltige Antwort geliefert.",
        ) from exc


def _kontakte_context(db: Session, mandant_id: str) -> list[dict[str, str]]:
    kontakte = db.query(Kontakt).filter(Kontakt.mandant_id == mandant_id).limit(200).all()
    kontakte.sort(key=lambda kontakt: kontakt.name.casefold())
    return [{"id": k.id, "name": k.name} for k in kontakte]


def _einstellungen_context(db: Session, mandant_id: str) -> dict:
    einstellungen = db.get(Buchhaltungseinstellungen, mandant_id)
    if einstellungen is None:
        return {
            "standard_zahlungsziel_tage": 14,
            "standard_ust_satz": "19.00",
            "kleinunternehmer": False,
        }
    return {
        "standard_zahlungsziel_tage": einstellungen.standard_zahlungsziel_tage,
        "standard_ust_satz": str(einstellungen.standard_ust_satz),
        "kleinunternehmer": einstellungen.kleinunternehmer,
    }


@router.post("/assistent", response_model=AssistantResponse)
def assistant(
    payload: AssistantRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
    ai: AiClient = Depends(get_ai_client),
) -> AssistantResponse:
    _lade_mandant(db, auth)

    planner_input = {
        "heute": date.today().isoformat(),
        "vorgegebenes_jahr": payload.jahr,
        "frage": payload.frage,
    }
    plan = _complete_json(
        ai,
        [
            {"role": "system", "content": ASSISTANT_PLANNER_SYSTEM},
            {"role": "user", "content": json.dumps(planner_input, ensure_ascii=False)},
        ],
        AssistantPlan,
    )

    if plan.tool == "keine":
        return AssistantResponse(
            antwort="Diese Frage kann ich mit den freigegebenen Bilantiq-Daten derzeit nicht verlaesslich beantworten.",
            tool="keine",
        )

    try:
        daten = execute_tool(
            db,
            mandant_id=auth["mandant_id"],
            plan=plan,
            requested_year=payload.jahr,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    answer_input = {
        "frage": payload.frage,
        "tool": plan.tool,
        "daten": jsonable_encoder(daten),
    }
    antwort = _complete_text(
        ai,
        [
            {"role": "system", "content": ASSISTANT_ANSWER_SYSTEM},
            {"role": "user", "content": json.dumps(answer_input, ensure_ascii=False)},
        ],
    )
    record_audit(
        db,
        aktion="ai_assistent_gelesen",
        mandant_id=auth["mandant_id"],
        user_id=auth["sub"],
        kontext=f"tool={plan.tool}",
    )
    db.commit()
    return AssistantResponse(antwort=antwort, tool=plan.tool)


@router.post("/rechnungsentwurf", response_model=InvoiceCreate)
def create_invoice_draft_from_text(
    payload: NaturalLanguageDraftRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
    ai: AiClient = Depends(get_ai_client),
) -> InvoiceCreate:
    _lade_mandant(db, auth)
    kontakte = _kontakte_context(db, auth["mandant_id"])
    if not kontakte:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vor einem KI-Rechnungsentwurf muss mindestens ein Kontakt vorhanden sein.",
        )
    context = {
        "heute": date.today().isoformat(),
        "kontakte": kontakte,
        "einstellungen": _einstellungen_context(db, auth["mandant_id"]),
        "schema": {
            "kontakt_id": "ID aus kontakte",
            "leistungsdatum": "YYYY-MM-DD",
            "faelligkeitsdatum": "YYYY-MM-DD",
            "waehrung": "EUR",
            "positionen": [
                {
                    "beschreibung": "Text",
                    "menge": "Decimal > 0",
                    "einzelpreis": "Netto-Decimal",
                    "ust_satz": "Decimal 0-100",
                    "kategorie": "optional",
                    "artikelnummer": "optional",
                }
            ],
            "betreff": "optional",
            "kopftext": "optional",
            "fusstext": "optional",
            "referenznummer": "optional",
            "kostenstelle": "optional",
            "zahlungsmethode": "optional",
            "skonto_tage": "optional",
            "skonto_prozent": "optional",
            "interne_kontaktperson_user_id": None,
        },
        "anweisung": payload.anweisung,
    }
    draft = _complete_json(
        ai,
        [
            {"role": "system", "content": INVOICE_DRAFT_SYSTEM},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        InvoiceCreate,
    )
    if draft.faelligkeitsdatum < draft.leistungsdatum:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="KI-Entwurf ist unplausibel: Faelligkeitsdatum liegt vor dem Leistungsdatum.",
        )

    # Noch nichts speichern: Der Entwurf wird zuerst in den bestehenden Editor
    # geladen und erst durch eine explizite Nutzeraktion ueber POST /invoices angelegt.
    get_scoped_or_404(db, Kontakt, draft.kontakt_id, auth["mandant_id"])
    record_audit(
        db,
        aktion="ai_rechnungsentwurf_vorgeschlagen",
        mandant_id=auth["mandant_id"],
        user_id=auth["sub"],
        kontext="formularentwurf",
    )
    db.commit()
    return draft


@router.post("/angebotsentwurf", response_model=QuoteCreate)
def create_quote_draft_from_text(
    payload: NaturalLanguageDraftRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
    ai: AiClient = Depends(get_ai_client),
) -> QuoteCreate:
    _lade_mandant(db, auth)
    kontakte = _kontakte_context(db, auth["mandant_id"])
    if not kontakte:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vor einem KI-Angebotsentwurf muss mindestens ein Kontakt vorhanden sein.",
        )
    context = {
        "heute": date.today().isoformat(),
        "kontakte": kontakte,
        "einstellungen": _einstellungen_context(db, auth["mandant_id"]),
        "schema": {
            "kontakt_id": "ID aus kontakte",
            "gueltig_bis": "YYYY-MM-DD",
            "waehrung": "EUR",
            "positionen": [
                {
                    "beschreibung": "Text",
                    "menge": "Decimal > 0",
                    "einzelpreis": "Netto-Decimal",
                    "ust_satz": "Decimal 0-100",
                }
            ],
        },
        "anweisung": payload.anweisung,
    }
    draft = _complete_json(
        ai,
        [
            {"role": "system", "content": QUOTE_DRAFT_SYSTEM},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        QuoteCreate,
    )
    if draft.gueltig_bis < date.today():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="KI-Entwurf ist unplausibel: Angebotsgueltigkeit liegt in der Vergangenheit.",
        )

    get_scoped_or_404(db, Kontakt, draft.kontakt_id, auth["mandant_id"])
    record_audit(
        db,
        aktion="ai_angebotsentwurf_vorgeschlagen",
        mandant_id=auth["mandant_id"],
        user_id=auth["sub"],
        kontext="formularentwurf",
    )
    db.commit()
    return draft


@router.post("/textvorschlag", response_model=TextSuggestionResponse)
def create_text_suggestion(
    payload: TextSuggestionRequest,
    auth=Depends(require_full_auth),
    db: Session = Depends(get_db),
    ai: AiClient = Depends(get_ai_client),
) -> TextSuggestionResponse:
    mandant = _lade_mandant(db, auth)
    context: dict

    if payload.art == "rechnung":
        invoice = get_scoped_or_404(db, Invoice, payload.objekt_id, auth["mandant_id"])
        if invoice.status != "final":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="E-Mail-Text kann erst fuer eine finale Rechnung erzeugt werden.",
            )
        context = {
            "art": "Rechnung",
            "firma": mandant.firmenname,
            "kunde": invoice.kontakt.name,
            "nummer": invoice.nummer,
            "betrag_brutto": str(invoice.brutto_gesamt),
            "waehrung": invoice.waehrung,
            "faelligkeitsdatum": invoice.faelligkeitsdatum.isoformat(),
            "bezahlt": invoice.bezahlt_am is not None,
        }
    elif payload.art == "angebot":
        quote = get_scoped_or_404(db, Quote, payload.objekt_id, auth["mandant_id"])
        if quote.status == "entwurf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="E-Mail-Text kann erst nach Vergabe einer Angebotsnummer erzeugt werden.",
            )
        context = {
            "art": "Angebot",
            "firma": mandant.firmenname,
            "kunde": quote.kontakt.name,
            "nummer": quote.nummer,
            "betrag_brutto": str(quote.brutto_gesamt),
            "waehrung": quote.waehrung,
            "gueltig_bis": quote.gueltig_bis.isoformat(),
        }
    else:
        mahnung = get_scoped_or_404(db, Mahnung, payload.objekt_id, auth["mandant_id"])
        invoice = get_scoped_or_404(db, Invoice, mahnung.invoice_id, auth["mandant_id"])
        context = {
            "art": STUFE_BEZEICHNUNG[mahnung.stufe],
            "firma": mandant.firmenname,
            "kunde": invoice.kontakt.name,
            "rechnung_nummer": invoice.nummer,
            "offener_betrag": str(invoice.brutto_gesamt),
            "waehrung": invoice.waehrung,
            "neue_faelligkeit": mahnung.neue_faelligkeit.isoformat(),
            "mahngebuehr": str(mahnung.mahngebuehr),
        }

    context["ton"] = payload.ton
    context["nutzer_hinweis"] = payload.hinweis
    text = _complete_text(
        ai,
        [
            {"role": "system", "content": TEXT_SYSTEM},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
    )
    record_audit(
        db,
        aktion=f"ai_textvorschlag_{payload.art}",
        mandant_id=auth["mandant_id"],
        user_id=auth["sub"],
        kontext=payload.objekt_id,
    )
    db.commit()
    return TextSuggestionResponse(text=text)
