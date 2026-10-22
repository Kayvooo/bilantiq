"""Zellwerte aus Fremddateien in Bilantiq-Werte umwandeln.

`wandle` gibt den Wert zurueck oder wirft `WertFehler` mit einer Meldung fuer den Nutzer.
Ob ein Fehler die ganze Zeile sperrt (Pflichtfeld) oder nur das Feld leer bleibt, entscheidet
der Aufrufer."""
from __future__ import annotations

import re
from decimal import Decimal

from email_validator import EmailNotValidError, validate_email

from app.core.tabelle import DATUMSFORMATE, parse_betrag, parse_datum
from app.core.validierung import UngueltigerWert, land_iso, pruefe_bic, pruefe_iban, pruefe_leitweg_id, pruefe_ust_id
from app.stammdaten.felder import Feld


class WertFehler(ValueError):
    pass


_JA = {"ja", "j", "x", "1", "true", "wahr", "yes", "y", "aktiv", "b2b", "firma", "geschaeftlich", "geschäftlich", "gewerblich", "unternehmen"}
_NEIN = {"nein", "n", "0", "false", "falsch", "no", "inaktiv", "archiviert", "b2c", "privat", "privatkunde", "privatperson"}
_TYPEN = {
    "kunde": "kunde", "kunden": "kunde", "debitor": "kunde", "debitoren": "kunde", "customer": "kunde", "client": "kunde",
    "lieferant": "lieferant", "lieferanten": "lieferant", "kreditor": "lieferant", "kreditoren": "lieferant",
    "supplier": "lieferant", "vendor": "lieferant",
    "beide": "beide", "kunde und lieferant": "beide", "kunde/lieferant": "beide", "lieferant und kunde": "beide",
    "both": "beide", "debitor und kreditor": "beide",
}
_UST_SAETZE = (Decimal("0"), Decimal("7"), Decimal("19"))


def ent_escape(wert: str) -> str:
    """Unser eigener CSV-Export entschaerft Formeln mit einem Apostroph davor. Beim Reimport
    wird genau dieses Apostroph wieder entfernt."""
    if len(wert) > 1 and wert[0] == "'" and wert[1] in "=+-@\t\r":
        return wert[1:]
    return wert


def _zahl(wert: str, dezimal: str) -> Decimal | None:
    """Wie parse_betrag, aber eindeutige Einzelwerte im jeweils anderen Format werden richtig
    gelesen: "90.00" in einer Datei mit Dezimalkomma ist 90, nicht 9000."""
    kompakt = wert.strip().replace(" ", "")
    if dezimal == "komma" and re.fullmatch(r"-?\d+\.\d{1,2}", kompakt):
        return parse_betrag(kompakt, "punkt")
    if dezimal == "punkt" and re.fullmatch(r"-?\d+,\d{1,2}", kompakt):
        return parse_betrag(kompakt, "komma")
    return parse_betrag(wert, dezimal)


def _datum(wert: str, feld: Feld):
    for format_ in DATUMSFORMATE:
        datum = parse_datum(wert, format_)
        if datum is not None:
            if not 1990 <= datum.year <= 2100:
                raise WertFehler(f"{feld.label}: „{wert}“ ist kein glaubwürdiges Datum.")
            return datum
    raise WertFehler(f"{feld.label}: „{wert}“ ist kein Datum.")


def _ja_nein(wert: str) -> bool:
    klein = wert.strip().casefold()
    if klein in _JA:
        return True
    if klein in _NEIN:
        return False
    raise WertFehler(f"„{wert}“ ist weder ja noch nein.")


def _ganzzahl(wert: str, feld: Feld) -> int:
    treffer = re.fullmatch(r"\s*(\d{1,3})(?:[.,]0+)?\s*(tage?|days?|d)?\s*", wert.casefold())
    if not treffer:
        raise WertFehler(f"{feld.label}: „{wert}“ ist keine ganze Zahl.")
    zahl = int(treffer.group(1))
    if zahl > 365:
        raise WertFehler(f"{feld.label}: höchstens 365.")
    return zahl


def _prozent(wert: str, dezimal: str, feld: Feld) -> Decimal:
    zahl = _zahl(wert.replace("%", ""), dezimal)
    if zahl is None or zahl < 0:
        raise WertFehler(f"{feld.label}: „{wert}“ ist keine Prozentangabe.")
    if Decimal("0") < zahl < Decimal("1") and "%" not in wert:
        zahl = zahl * 100  # 0,19 steht fuer 19 %
    if zahl > 100:
        raise WertFehler(f"{feld.label}: höchstens 100 %.")
    return zahl.quantize(Decimal("0.01"))


def _ust_satz(wert: str, dezimal: str, feld: Feld) -> Decimal:
    satz = _prozent(wert, dezimal, feld)
    if satz.normalize() not in [s.normalize() for s in _UST_SAETZE]:
        raise WertFehler(f"USt-Satz {satz.normalize()} % ist kein deutscher Steuersatz (0, 7 oder 19 %).")
    return satz


def wandle(feld: Feld, roh: str, *, dezimal: str = "komma", land: str = "DE"):
    """Gibt None fuer leere Zellen zurueck."""
    wert = ent_escape(roh.strip())
    if not wert:
        return None
    try:
        match feld.typ:
            case "text":
                if feld.max_laenge and len(wert) > feld.max_laenge:
                    raise WertFehler(f"{feld.label} ist zu lang (höchstens {feld.max_laenge} Zeichen).")
                return wert
            case "plz":
                # Excel speichert PLZ gern als Zahl und verliert die fuehrende Null (01067 -> 1067).
                if land == "DE" and re.fullmatch(r"\d{4}", wert):
                    return wert.zfill(5)
                if feld.max_laenge and len(wert) > feld.max_laenge:
                    raise WertFehler(f"{feld.label} ist zu lang.")
                return wert
            case "email":
                try:
                    return validate_email(wert, check_deliverability=False).normalized
                except EmailNotValidError as exc:
                    raise WertFehler(f"E-Mail-Adresse „{wert}“ ist ungültig.") from exc
            case "land":
                return land_iso(wert)
            case "ja_nein":
                return _ja_nein(wert)
            case "datum":
                return _datum(wert, feld)
            case "ganzzahl":
                return _ganzzahl(wert, feld)
            case "prozent":
                return _prozent(wert, dezimal, feld)
            case "ust_satz":
                return _ust_satz(wert, dezimal, feld)
            case "geld":
                betrag = _zahl(wert, dezimal)
                if betrag is None:
                    raise WertFehler(f"{feld.label}: „{wert}“ ist kein Betrag.")
                if betrag < 0:
                    raise WertFehler(f"{feld.label} darf nicht negativ sein.")
                return betrag.quantize(Decimal("0.01"))
            case "iban":
                return pruefe_iban(wert)
            case "bic":
                return pruefe_bic(wert)
            case "ust_id":
                return pruefe_ust_id(wert)
            case "leitweg_id":
                return pruefe_leitweg_id(wert)
            case "kontakt_typ":
                typ = _TYPEN.get(re.sub(r"\s+", " ", wert.casefold()))
                if typ is None:
                    raise WertFehler(f"Art „{wert}“ ist unbekannt. Erlaubt: Kunde, Lieferant, beide.")
                return typ
    except UngueltigerWert as exc:
        raise WertFehler(str(exc)) from exc
    raise WertFehler(f"Unbekannter Feldtyp {feld.typ}.")
