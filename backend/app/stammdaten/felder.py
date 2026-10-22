"""Zielfelder fuer den Stammdaten-Import und -Export.

Das Label ist zugleich die Spaltenueberschrift im Export und in der Vorlage, damit eine
exportierte Datei ohne Nacharbeit wieder importiert werden kann. Die Synonyme dienen nur dem
Vorschlag fuer die Spaltenzuordnung, der Nutzer bestaetigt oder aendert sie."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

FeldTyp = Literal[
    "text", "email", "land", "ja_nein", "ganzzahl", "prozent", "geld", "ust_satz", "iban", "bic", "ust_id",
    "leitweg_id", "kontakt_typ", "plz", "datum",
]
Ziel = Literal["kontakte", "produkte", "rechnungen"]


@dataclass(frozen=True)
class Feld:
    schluessel: str
    label: str
    typ: FeldTyp = "text"
    pflicht: bool = False
    max_laenge: int | None = None
    synonyme: tuple[str, ...] = ()
    beispiel: str = ""
    # Nur fuer den Import (z. B. Hausnummer wird an die Strasse angehaengt), nicht im Export.
    nur_import: bool = False


KONTAKT_FELDER: tuple[Feld, ...] = (
    Feld("kundennummer", "Kundennummer", max_laenge=50, beispiel="K-1001", synonyme=(
        "kundennummer", "kundennr", "kunden nr", "kd nr", "kdnr", "debitorennummer", "debitor", "kreditorennummer",
        "lieferantennummer", "kontaktnummer", "kontakt nr", "customer number", "customer id", "nummer",
    )),
    Feld("typ", "Art", typ="kontakt_typ", beispiel="Kunde", synonyme=(
        "art", "typ", "kontaktart", "kontakttyp", "rolle", "kategorie", "type",
    )),
    Feld("name", "Name", pflicht=True, max_laenge=255, beispiel="Muster GmbH", synonyme=(
        "firma", "firmenname", "unternehmen", "organisation", "company", "name", "name 1", "kunde", "kundenname",
        "lieferant", "lieferantenname", "bezeichnung",
    )),
    Feld("anrede", "Anrede", max_laenge=30, beispiel="Frau", synonyme=("anrede", "salutation", "titel")),
    Feld("vorname", "Vorname", max_laenge=100, beispiel="Erika", synonyme=("vorname", "first name", "firstname", "given name")),
    Feld("nachname", "Nachname", max_laenge=100, beispiel="Muster", synonyme=("nachname", "last name", "lastname", "surname", "familienname")),
    Feld("strasse", "Straße", max_laenge=255, beispiel="Hauptstraße 1", synonyme=(
        "strasse", "straße", "str", "strasse und hausnummer", "adresse", "anschrift", "street", "address", "adresszeile 1",
    )),
    Feld("hausnummer", "Hausnummer", max_laenge=20, synonyme=("hausnummer", "hausnr", "haus nr", "house number"), nur_import=True),
    Feld("plz", "PLZ", typ="plz", max_laenge=20, beispiel="10115", synonyme=("plz", "postleitzahl", "zip", "zip code", "postal code", "postcode")),
    Feld("ort", "Ort", max_laenge=255, beispiel="Berlin", synonyme=("ort", "stadt", "city", "wohnort", "town")),
    Feld("land", "Land", typ="land", beispiel="DE", synonyme=("land", "country", "staat", "laenderkennzeichen", "landeskennzeichen", "laendercode")),
    Feld("email", "E-Mail", typ="email", beispiel="info@muster.de", synonyme=("e mail", "email", "mail", "e mail adresse", "emailadresse")),
    Feld("telefon", "Telefon", max_laenge=50, beispiel="+49 30 123456", synonyme=(
        "telefon", "tel", "telefonnummer", "phone", "mobil", "handy", "mobilnummer", "phone number",
    )),
    Feld("ist_geschaeftskunde", "Geschäftskunde", typ="ja_nein", beispiel="ja", synonyme=(
        "geschaeftskunde", "b2b", "firmenkunde", "gewerblich", "kundentyp",
    )),
    Feld("ust_id", "USt-IdNr.", typ="ust_id", beispiel="DE123456789", synonyme=(
        "ust idnr", "ust id", "ustid", "ustidnr", "umsatzsteuer id", "umsatzsteuer identifikationsnummer", "vat",
        "vat id", "vat number",
    )),
    Feld("steuernummer", "Steuernummer", max_laenge=30, synonyme=("steuernummer", "st nr", "steuer nr", "tax number")),
    Feld("iban", "IBAN", typ="iban", beispiel="DE89370400440532013000", synonyme=("iban", "bankverbindung")),
    Feld("bic", "BIC", typ="bic", synonyme=("bic", "swift", "swift code")),
    Feld("zahlungsziel_tage", "Zahlungsziel (Tage)", typ="ganzzahl", beispiel="14", synonyme=(
        "zahlungsziel", "zahlungsziel tage", "zahlungsfrist", "zahlungsbedingung", "payment terms", "faelligkeit tage",
    )),
    Feld("skonto_prozent", "Skonto (%)", typ="prozent", synonyme=("skonto", "skonto prozent", "skontosatz")),
    Feld("skonto_tage", "Skonto (Tage)", typ="ganzzahl", synonyme=("skontotage", "skonto tage", "skontofrist")),
    Feld("leitweg_id", "Leitweg-ID", typ="leitweg_id", synonyme=("leitweg id", "leitwegid", "leitweg", "buyer reference", "kaeuferreferenz")),
    Feld("notiz", "Notiz", max_laenge=2000, synonyme=("notiz", "bemerkung", "bemerkungen", "anmerkung", "kommentar", "notes", "hinweis", "info")),
)

PRODUKT_FELDER: tuple[Feld, ...] = (
    Feld("artikelnummer", "Artikelnummer", max_laenge=50, beispiel="A-100", synonyme=(
        "artikelnummer", "artikel nr", "art nr", "artnr", "produktnummer", "sku", "nummer", "item number",
    )),
    Feld("bezeichnung", "Bezeichnung", pflicht=True, max_laenge=255, beispiel="Beratung", synonyme=(
        "bezeichnung", "artikelbezeichnung", "produktname", "artikelname", "name", "artikel", "produkt", "titel",
        "leistung", "title",
    )),
    Feld("beschreibung", "Beschreibung", max_laenge=500, beispiel="Beratung vor Ort", synonyme=(
        "beschreibung", "langtext", "details", "description", "text",
    )),
    Feld("einzelpreis", "Preis netto", typ="geld", beispiel="90,00", synonyme=(
        "preis netto", "nettopreis", "einzelpreis", "netto", "verkaufspreis netto", "vk netto", "preis", "verkaufspreis",
        "vk", "price",
    )),
    Feld("bruttopreis", "Preis brutto", typ="geld", synonyme=("preis brutto", "bruttopreis", "brutto", "vk brutto"), nur_import=True),
    Feld("ust_satz", "USt-Satz", typ="ust_satz", beispiel="19", synonyme=(
        "ust satz", "ust", "mwst", "mwst satz", "steuersatz", "umsatzsteuer", "umsatzsteuersatz", "vat", "tax rate",
    )),
    Feld("einheit", "Einheit", max_laenge=50, beispiel="Stunde", synonyme=("einheit", "mengeneinheit", "me", "unit")),
    Feld("aktiv", "Aktiv", typ="ja_nein", beispiel="ja", synonyme=("aktiv", "status", "active")),
)

RECHNUNG_FELDER: tuple[Feld, ...] = (
    Feld("rechnungsnummer", "Rechnungsnummer", pflicht=True, max_laenge=60, beispiel="RE-2024-0001", synonyme=(
        "rechnungsnummer", "rechnungsnr", "rechnung nr", "re nr", "renr", "belegnummer", "beleg nr", "belegnr",
        "invoice number", "invoice no", "invoice", "rechnung", "nummer",
    )),
    Feld("rechnungsdatum", "Rechnungsdatum", typ="datum", pflicht=True, beispiel="15.03.2024", synonyme=(
        "rechnungsdatum", "belegdatum", "invoice date", "ausgestellt am", "erstellt am", "rechnung vom", "datum",
    )),
    Feld("kundennummer", "Kundennummer", max_laenge=50, beispiel="K-1001", synonyme=(
        "kundennummer", "kundennr", "kunden nr", "kd nr", "kdnr", "debitorennummer", "customer number", "customer id",
    )),
    Feld("kunde", "Kunde", max_laenge=255, beispiel="Muster GmbH", synonyme=(
        "kunde", "kundenname", "firma", "empfaenger", "rechnungsempfaenger", "customer", "unternehmen", "name",
    )),
    Feld("faelligkeit", "Fälligkeit", typ="datum", beispiel="14.04.2024", synonyme=(
        "faelligkeit", "faelligkeitsdatum", "zahlbar bis", "due date", "faellig am", "faellig",
    )),
    Feld("netto", "Netto", typ="geld", beispiel="1000,00", synonyme=(
        "netto", "nettobetrag", "summe netto", "gesamt netto", "betrag netto", "net amount",
    )),
    Feld("ust", "USt-Betrag", typ="geld", beispiel="190,00", synonyme=(
        "ust betrag", "ustbetrag", "umsatzsteuer", "umsatzsteuerbetrag", "mwst betrag", "mwstbetrag", "steuerbetrag",
        "vat amount", "tax amount", "steuer", "ust", "mwst",
    )),
    Feld("brutto", "Brutto", typ="geld", beispiel="1190,00", synonyme=(
        "brutto", "bruttobetrag", "gesamtbetrag", "rechnungsbetrag", "summe brutto", "gesamt", "total", "betrag", "amount",
    )),
    Feld("ust_satz", "USt-Satz", typ="prozent", beispiel="19", synonyme=(
        "ust satz", "ustsatz", "steuersatz", "mwst satz", "mwstsatz", "umsatzsteuersatz", "vat rate", "tax rate",
        "ust prozent", "mwst prozent",
    )),
    Feld("netto_19", "Netto 19 %", typ="geld", synonyme=("netto 19", "nettobetrag 19", "netto19", "umsatz 19", "19 netto")),
    Feld("netto_7", "Netto 7 %", typ="geld", synonyme=("netto 7", "nettobetrag 7", "netto7", "umsatz 7", "7 netto")),
    Feld("netto_0", "Netto 0 %", typ="geld", synonyme=("netto 0", "nettobetrag 0", "netto0", "umsatz 0", "steuerfrei", "netto steuerfrei")),
    Feld("offener_betrag", "Offener Betrag", typ="geld", beispiel="1190,00", synonyme=(
        "offener betrag", "offen", "restbetrag", "offener posten", "open amount", "saldo", "rest", "ausstehend", "offen betrag",
    )),
    Feld("bezahlt_am", "Bezahlt am", typ="datum", synonyme=(
        "bezahlt am", "zahlungsdatum", "zahlungseingang", "bezahldatum", "payment date", "paid on", "bezahlt",
    )),
    Feld("status", "Status", max_laenge=40, beispiel="offen", synonyme=(
        "status", "zahlstatus", "zahlungsstatus", "rechnungsstatus", "state",
    )),
)

FELDER: dict[str, tuple[Feld, ...]] = {"kontakte": KONTAKT_FELDER, "produkte": PRODUKT_FELDER, "rechnungen": RECHNUNG_FELDER}


def normalisiere_kopf(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("ß", "ss"))
    text = "".join(zeichen for zeichen in text if not unicodedata.combining(zeichen))
    text = text.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return re.sub(r"[^a-z0-9]", "", text)


# Zu allgemeine Begriffe zaehlen nur als exakte Ueberschrift, sonst landet z. B. "Faxnummer"
# bei der Kundennummer, "Bundesland" beim Land oder "Einkaufspreis" beim Verkaufspreis.
_NUR_EXAKT = frozenset((
    "nummer", "name", "kunde", "lieferant", "bezeichnung", "preis", "netto", "brutto", "status", "text", "info",
    "art", "typ", "titel", "adresse", "kategorie", "rolle", "land", "mwst", "ust", "umsatzsteuer", "vat", "artikel",
    "produkt", "leistung", "debitor", "verkaufspreis", "price", "title", "type",
    "datum", "gesamt", "total", "betrag", "amount", "steuer", "rechnung", "bezahlt", "offen", "rest", "saldo", "invoice",
    "state", "kunde",
))


def schlage_zuordnung_vor(ziel: str, kopf: list[str], zeilen: list[list[str]] | None = None) -> dict[str, str]:
    """Feld -> Spalte. Zuerst exakte Treffer fuer alle Felder, danach "Spalte enthaelt
    Synonym" (Synonym mind. 4 Zeichen und nicht zu allgemein). Jede Spalte und jedes Feld
    hoechstens einmal."""
    felder = FELDER[ziel]
    normal = {spalte: normalisiere_kopf(spalte) for spalte in kopf}
    zuordnung: dict[str, str] = {}
    vergeben: set[str] = set()

    for durchgang in ("exakt", "enthalten"):
        for feld in felder:
            if feld.schluessel in zuordnung:
                continue
            for synonym in (feld.label, *feld.synonyme):
                ziel_text = normalisiere_kopf(synonym)
                if durchgang == "enthalten" and (len(ziel_text) < 4 or ziel_text in _NUR_EXAKT_NORMAL):
                    continue
                treffer = next(
                    (
                        spalte for spalte in kopf
                        if spalte not in vergeben and (
                            normal[spalte] == ziel_text if durchgang == "exakt" else ziel_text in normal[spalte]
                        )
                    ),
                    None,
                )
                if treffer:
                    zuordnung[feld.schluessel] = treffer
                    vergeben.add(treffer)
                    break
    if ziel == "rechnungen" and zeilen:
        _unterscheide_ust_satz_und_betrag(zuordnung, kopf, zeilen)
    return zuordnung


_SAETZE = {Decimal(s) for s in ("0", "5", "7", "16", "19")}


def _wie_ein_satz(werte: list[str]) -> bool:
    """True, wenn alle Beispielwerte aussehen wie ein Steuersatz (0, 5, 7, 16, 19 oder 0,19 / 0,07)."""
    zahlen: list[Decimal] = []
    for roh in werte:
        text = roh.replace("%", "").replace(" ", "").replace(",", ".").strip()
        if not text:
            continue
        try:
            zahl = Decimal(text)
        except InvalidOperation:
            return False
        zahlen.append(zahl * 100 if Decimal("0") < zahl < 1 else zahl)
    return bool(zahlen) and all(zahl.normalize() in {s.normalize() for s in _SAETZE} for zahl in zahlen)


def _unterscheide_ust_satz_und_betrag(zuordnung: dict[str, str], kopf: list[str], zeilen: list[list[str]]) -> None:
    """Eine Spalte "USt" oder "MwSt" kann ein Satz (19) oder ein Betrag (190,00) sein. Die Ueberschrift
    allein verraet das nicht, die Beispielwerte schon. Es wird nur korrigiert, wenn genau eine der beiden
    Zuordnungen vergeben ist."""
    if ("ust" in zuordnung) == ("ust_satz" in zuordnung):
        return
    feld = "ust" if "ust" in zuordnung else "ust_satz"
    spalte = zuordnung[feld]
    nummer = kopf.index(spalte)
    werte = [zeile[nummer] for zeile in zeilen[:50] if nummer < len(zeile)]
    richtig = "ust_satz" if _wie_ein_satz(werte) else "ust"
    if richtig != feld:
        zuordnung[richtig] = zuordnung.pop(feld)


_NUR_EXAKT_NORMAL = frozenset(normalisiere_kopf(wort) for wort in _NUR_EXAKT)
