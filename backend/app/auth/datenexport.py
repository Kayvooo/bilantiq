"""DSGVO-Datenauskunft / -export (Art. 15 Auskunft, Art. 20 Datenuebertragbarkeit).

Stellt alle zu einem Mandanten gespeicherten Daten strukturiert und maschinenlesbar
(JSON) bereit. Verschluesselte personenbezogene Felder (E-Mail, Mitarbeiternamen)
werden entschluesselt ausgegeben; reines Sicherheitsmaterial (Passwort-Hashes,
MFA-Secrets, Lookup-Hashes) wird bewusst NICHT exportiert -- es ist keine an die
betroffene Person herauszugebende Information und wuerde die Kontosicherheit schwaechen.

Der Export ist bewusst Owner-only (siehe Route in app/auth/routes.py): er enthaelt die
gesamten Daten des Mandanten inkl. aller Mitglieder und aller Kontakte, nicht nur die
des aufrufenden Nutzers.

Hochgeladene Dateien (Belege, Logo, Briefpapier) sind hier nur ueber ihre Referenz
enthalten, nicht als Bytes -- eine spaetere ZIP-Variante mit den Originaldateien ist ein
moeglicher Ausbau.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.altrechnungen.models import Altrechnung, AltrechnungZahlung
from app.anlagen.models import Anlage
from app.auftraege.models import (
    Auftragsbestaetigung,
    Auftragsbestaetigungsnummernkreis,
    Lieferschein,
    Lieferscheinnummernkreis,
)
from app.auth.models import AuthSession, Briefpapier, EmailAenderung, Einladung, Mandant, Mitgliedschaft, User
from app.buchhaltungseinstellungen.models import Buchhaltungseinstellungen
from app.core.audit_log import AuditLogEintrag
from app.core.crypto import decrypt_field
from app.einnahmen.models import SonstigeEinnahme
from app.bank.models import Bankimport, Bankkonto, Bankumsatz
from app.stammdaten.models import Datenimport
from app.invoices.models import Invoice, Kontakt, Positionskategorie, Rechnungsnummernkreis
from app.kassenbuch.models import KassenbuchEintrag
from app.mahnwesen.models import Mahnung
from app.payroll.models import LohnMonatsentwurf, Mitarbeiter
from app.produkte.models import Lagerbewegung, Produkt
from app.quotes.models import Angebotsnummernkreis, Quote
from app.receipts.models import Ausgabe, AusgabeSteueranteil, Receipt
from app.wiederkehrend.models import WiederkehrendeAusgabe, WiederkehrendeRechnung


# Reines Sicherheitsmaterial -- niemals exportieren.
_GEHEIM = {
    "dedupe_key",  # interner Blind-Index, kein Inhalt
    "iban_hash",
    "dedupe_hash",
    "nummer_hash",
    "passwort_hash",
    "mfa_secret_encrypted",
    "mfa_pending_secret_encrypted",
    "mfa_letzter_zeitschritt",
    "email_lookup_hash",
    "code_hash",
    "neue_email_lookup_hash",
}
_ENCRYPTED_SUFFIX = "_encrypted"


def _wert(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialize(obj: Any) -> dict[str, Any]:
    daten: dict[str, Any] = {}
    for spalte in sa_inspect(obj).mapper.column_attrs:
        name = spalte.key
        if name in _GEHEIM:
            continue
        wert = getattr(obj, name)
        if name.endswith(_ENCRYPTED_SUFFIX):
            klarname = name[: -len(_ENCRYPTED_SUFFIX)]
            daten[klarname] = decrypt_field(wert) if wert is not None else None
        else:
            daten[name] = _wert(wert)
    return daten


def _mit_positionen(obj: Any) -> dict[str, Any]:
    daten = _serialize(obj)
    daten["positionen"] = [_serialize(p) for p in obj.positionen]
    return daten


def _liste(db: Session, model: Any, mandant_id: str) -> list[dict[str, Any]]:
    zeilen = db.query(model).filter(model.mandant_id == mandant_id).all()
    return [_serialize(z) for z in zeilen]


def _liste_mit_positionen(db: Session, model: Any, mandant_id: str) -> list[dict[str, Any]]:
    zeilen = db.query(model).filter(model.mandant_id == mandant_id).all()
    return [_mit_positionen(z) for z in zeilen]


def erstelle_datenexport(db: Session, mandant_id: str) -> dict[str, Any]:
    """Baut die vollstaendige, entschluesselte JSON-Struktur aller Mandantendaten."""
    mandant = db.get(Mandant, mandant_id)

    mitgliedschaften = db.query(Mitgliedschaft).filter(Mitgliedschaft.mandant_id == mandant_id).all()
    user_ids = [m.user_id for m in mitgliedschaften]
    nutzer = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []

    return {
        "export_erstellt_am": datetime.now().astimezone().isoformat(),
        "hinweis": (
            "DSGVO-Datenexport (Art. 15/20). Enthaelt alle zum Mandanten gespeicherten "
            "Daten in entschluesselter Form. Passwort-Hashes, MFA-Secrets und "
            "Lookup-Hashes sind aus Sicherheitsgruenden nicht enthalten. Hochgeladene "
            "Dateien sind ueber ihre Referenz genannt, nicht als Datei-Inhalt."
        ),
        "mandant": _serialize(mandant) if mandant is not None else None,
        "nutzer": [_serialize(u) for u in nutzer],
        "mitgliedschaften": [_serialize(m) for m in mitgliedschaften],
        "auth_sessions": _liste(db, AuthSession, mandant_id),
        "email_aenderungen": _liste(db, EmailAenderung, mandant_id),
        "einladungen": _liste(db, Einladung, mandant_id),
        "briefpapiere": _liste(db, Briefpapier, mandant_id),
        "buchhaltungseinstellungen": _liste(db, Buchhaltungseinstellungen, mandant_id),
        "kontakte": _liste(db, Kontakt, mandant_id),
        "rechnungen": _liste_mit_positionen(db, Invoice, mandant_id),
        "rechnungsnummernkreise": _liste(db, Rechnungsnummernkreis, mandant_id),
        "positionskategorien": _liste(db, Positionskategorie, mandant_id),
        "angebote": _liste_mit_positionen(db, Quote, mandant_id),
        "angebotsnummernkreise": _liste(db, Angebotsnummernkreis, mandant_id),
        "auftragsbestaetigungen": _liste_mit_positionen(db, Auftragsbestaetigung, mandant_id),
        "auftragsbestaetigungsnummernkreise": _liste(db, Auftragsbestaetigungsnummernkreis, mandant_id),
        "lieferscheine": _liste_mit_positionen(db, Lieferschein, mandant_id),
        "lieferscheinnummernkreise": _liste(db, Lieferscheinnummernkreis, mandant_id),
        "wiederkehrende_rechnungen": _liste_mit_positionen(db, WiederkehrendeRechnung, mandant_id),
        "wiederkehrende_ausgaben": _liste(db, WiederkehrendeAusgabe, mandant_id),
        "belege": _liste(db, Receipt, mandant_id),
        "ausgaben": _liste(db, Ausgabe, mandant_id),
        "ausgabe_steueranteile": _liste(db, AusgabeSteueranteil, mandant_id),
        "sonstige_einnahmen": _liste(db, SonstigeEinnahme, mandant_id),
        "mahnungen": _liste(db, Mahnung, mandant_id),
        "kassenbuch": _liste(db, KassenbuchEintrag, mandant_id),
        "bankkonten": _liste(db, Bankkonto, mandant_id),
        "bankimporte": _liste(db, Bankimport, mandant_id),
        "bankumsaetze": _liste(db, Bankumsatz, mandant_id),
        "datenimporte": _liste(db, Datenimport, mandant_id),
        "altrechnungen": _liste(db, Altrechnung, mandant_id),
        "altrechnung_zahlungen": _liste(db, AltrechnungZahlung, mandant_id),
        "produkte": _liste(db, Produkt, mandant_id),
        "lagerbewegungen": _liste(db, Lagerbewegung, mandant_id),
        "anlagen": _liste(db, Anlage, mandant_id),
        "mitarbeitende": _liste(db, Mitarbeiter, mandant_id),
        "lohn_monatsentwuerfe": _liste(db, LohnMonatsentwurf, mandant_id),
        "audit_log": _liste(db, AuditLogEintrag, mandant_id),
    }
