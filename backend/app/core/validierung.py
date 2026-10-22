"""Pruefung und Normalisierung von Stammdaten-Werten (IBAN, USt-IdNr., Leitweg-ID, Land).

Wird vom Kontaktformular (Pydantic-Validatoren) und vom Stammdaten-Import genutzt. Jede
Funktion gibt den normalisierten Wert zurueck oder wirft `UngueltigerWert` mit einer
Meldung, die der Nutzer versteht. Online-Pruefungen (BZSt, VIES) finden hier nicht statt."""
from __future__ import annotations

import re
import unicodedata


class UngueltigerWert(ValueError):
    pass


def _kompakt(wert: str) -> str:
    return re.sub(r"[\s.\-/]", "", wert).upper()


def _mod97(zeichen: str) -> int:
    # Buchstaben werden zu Zahlen (A=10 ... Z=35), wie bei IBAN und Leitweg-ID (ISO 7064 Mod 97-10).
    return int("".join(str(int(c, 36)) for c in zeichen)) % 97


def pruefe_iban(wert: str) -> str:
    iban = _kompakt(wert)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        raise UngueltigerWert("Die IBAN hat nicht das richtige Format.")
    if iban.startswith("DE") and len(iban) != 22:
        raise UngueltigerWert("Eine deutsche IBAN hat 22 Stellen.")
    if _mod97(iban[4:] + iban[:4]) != 1:
        raise UngueltigerWert("Die Prüfziffer der IBAN stimmt nicht. Bitte auf Tippfehler prüfen.")
    return iban


def formatiere_iban(iban: str) -> str:
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def pruefe_bic(wert: str) -> str:
    bic = _kompakt(wert)
    if not re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", bic):
        raise UngueltigerWert("Die BIC hat nicht das richtige Format (8 oder 11 Zeichen).")
    return bic


# Formatregeln der USt-IdNr. je Land. Nur das Format wird geprueft, nicht ob die Nummer
# vergeben ist (das kann nur das BZSt bzw. VIES).
_UST_ID_MUSTER = {
    "DE": r"DE\d{9}",
    "AT": r"ATU\d{8}",
    "BE": r"BE[01]\d{9}",
    "CH": r"CHE\d{9}(MWST|TVA|IVA)?",
    "CZ": r"CZ\d{8,10}",
    "DK": r"DK\d{8}",
    "ES": r"ES[0-9A-Z]\d{7}[0-9A-Z]",
    "FR": r"FR[0-9A-Z]{2}\d{9}",
    "IT": r"IT\d{11}",
    "LU": r"LU\d{8}",
    "NL": r"NL\d{9}B\d{2}",
    "PL": r"PL\d{10}",
    "SE": r"SE\d{12}",
}


def pruefe_ust_id(wert: str) -> str:
    ust_id = _kompakt(wert)
    land = ust_id[:2]
    muster = _UST_ID_MUSTER.get(land)
    if muster is None:
        if not re.fullmatch(r"[A-Z]{2}[0-9A-Z+*]{2,13}", ust_id):
            raise UngueltigerWert("Die USt-IdNr. muss mit dem Länderkürzel beginnen, z. B. DE123456789.")
        return ust_id
    if not re.fullmatch(muster, ust_id):
        beispiel = {"DE": "DE123456789", "AT": "ATU12345678"}.get(land)
        zusatz = f" Beispiel: {beispiel}." if beispiel else ""
        raise UngueltigerWert(f"Die USt-IdNr. hat nicht das Format für {land}.{zusatz}")
    return ust_id


def pruefe_leitweg_id(wert: str) -> str:
    """Leitweg-ID der oeffentlichen Verwaltung: Grobadressierung (2 bis 12 Ziffern),
    optional Feinadressierung (bis 30 Zeichen), Pruefziffer (2 Ziffern, Mod 97-10)."""
    leitweg_id = wert.strip().upper().replace(" ", "")
    treffer = re.fullmatch(r"(\d{2,12})(?:-([A-Z0-9]{1,30}))?-(\d{2})", leitweg_id)
    if not treffer:
        raise UngueltigerWert("Die Leitweg-ID hat nicht das richtige Format, z. B. 04011000-12345-03.")
    if _mod97(leitweg_id.replace("-", "")) != 1:
        raise UngueltigerWert("Die Prüfziffer der Leitweg-ID stimmt nicht. Bitte beim Auftraggeber nachfragen.")
    return leitweg_id


_LAENDER = {
    "DE": ("deutschland", "germany", "bundesrepublik deutschland", "brd", "deu", "d"),
    "AT": ("österreich", "oesterreich", "austria", "aut", "a"),
    "CH": ("schweiz", "switzerland", "suisse", "che"),
    "LI": ("liechtenstein",),
    "LU": ("luxemburg", "luxembourg"),
    "NL": ("niederlande", "netherlands", "holland", "nederland"),
    "BE": ("belgien", "belgium", "belgique"),
    "FR": ("frankreich", "france"),
    "IT": ("italien", "italy", "italia"),
    "ES": ("spanien", "spain", "españa", "espana"),
    "PT": ("portugal",),
    "PL": ("polen", "poland", "polska"),
    "CZ": ("tschechien", "tschechische republik", "czech republic", "czechia"),
    "DK": ("dänemark", "daenemark", "denmark"),
    "SE": ("schweden", "sweden"),
    "NO": ("norwegen", "norway"),
    "FI": ("finnland", "finland"),
    "IE": ("irland", "ireland"),
    "GB": ("großbritannien", "grossbritannien", "vereinigtes königreich", "united kingdom", "uk", "england"),
    "US": ("usa", "vereinigte staaten", "united states"),
    "HU": ("ungarn", "hungary"),
    "SK": ("slowakei", "slovakia"),
    "SI": ("slowenien", "slovenia"),
    "HR": ("kroatien", "croatia"),
    "RO": ("rumänien", "rumaenien", "romania"),
    "BG": ("bulgarien", "bulgaria"),
    "GR": ("griechenland", "greece"),
    "EE": ("estland", "estonia"),
    "LV": ("lettland", "latvia"),
    "LT": ("litauen", "lithuania"),
    "MT": ("malta",),
    "CY": ("zypern", "cyprus"),
    "TR": ("türkei", "tuerkei", "turkey"),
}
_LAND_NACH_NAME = {
    unicodedata.normalize("NFC", name): code for code, namen in _LAENDER.items() for name in namen
}


def land_iso(wert: str | None, *, standard: str = "DE") -> str:
    """Land als ISO-3166-Code. Zweibuchstabige Codes werden uebernommen, gaengige deutsche
    und englische Namen uebersetzt, alles andere ist ein Fehler (nichts wird geraten)."""
    if wert is None or not wert.strip():
        return standard
    roh = unicodedata.normalize("NFC", wert.strip())
    if re.fullmatch(r"[A-Za-z]{2}", roh):
        return roh.upper()
    code = _LAND_NACH_NAME.get(roh.casefold())
    if code is None:
        raise UngueltigerWert(f"Das Land „{wert.strip()}“ kenne ich nicht. Bitte als Kürzel angeben, z. B. DE oder AT.")
    return code
