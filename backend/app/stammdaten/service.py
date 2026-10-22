"""Stammdaten importieren: Probelauf (`pruefe`), Uebernahme (`importiere`) und Rueckgaengig.

Grundsaetze:
- Der Probelauf und der Import laufen ueber denselben Code, das Ergebnis ist identisch.
- Fehler in Pflichtfeldern sperren die Zeile. Fehler in optionalen Feldern lassen nur das
  Feld leer und werden als Hinweis gezeigt.
- Doppelte werden erkannt (Datei und Bestand) und standardmaessig uebersprungen. "Ergaenzen"
  fuellt nur leere Felder und ueberschreibt nie etwas.
- Die Felder sind verschluesselt, deshalb wird der Bestand in Python verglichen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.audit_log import record as record_audit
from app.core.tabelle import Tabelle, schlage_dezimal_vor
from app.invoices.kontakte import kontakt_wird_verwendet, setze_iban
from app.invoices.models import Kontakt
from app.produkte.models import Lagerbewegung, Produkt
from app.stammdaten.felder import FELDER, Feld, normalisiere_kopf
from app.stammdaten.models import Datenimport
from app.stammdaten.werte import WertFehler, wandle

Status = Literal["neu", "ergaenzen", "vorhanden", "doppelt", "fehler"]


class ImportAbgelehnt(ValueError):
    """Der Import kann so nicht ausgefuehrt werden. Die Meldung ist fuer den Nutzer."""


class Optionen(BaseModel):
    zuordnung: dict[str, str] = Field(default_factory=dict)  # Feld -> Spaltenueberschrift
    dezimal: Literal["komma", "punkt"] = "komma"
    doppelte: Literal["ueberspringen", "ergaenzen"] = "ueberspringen"
    fehlerhafte_auslassen: bool = False
    standard_ust_satz: Decimal = Decimal("19")
    # Nur fuer die Rechnungsliste: Zahlungsziel, wenn die Datei keine Faelligkeit enthaelt, und ob
    # Kunden, die es noch nicht gibt, mit angelegt werden.
    zahlungsziel_tage: int = Field(default=14, ge=0, le=365)
    fehlende_kunden_anlegen: bool = False
    blatt: str | None = None
    kodierung: str | None = None
    trennzeichen: str | None = None


@dataclass
class Zeile:
    nummer: int  # Zeilennummer in der Datei, die Kopfzeile ist Zeile 1
    status: Status
    anzeige: str
    werte: dict[str, Any]
    fehler: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    ziel_id: str | None = None
    grund: str | None = None
    ergaenzt: list[str] = field(default_factory=list)


@dataclass
class Bericht:
    ziel: str
    zeilen: list[Zeile]

    def anzahl(self, status: Status) -> int:
        return sum(1 for zeile in self.zeilen if zeile.status == status)


def _felder(ziel: str) -> dict[str, Feld]:
    return {feld.schluessel: feld for feld in FELDER[ziel]}


def _norm(text: str | None) -> str:
    return normalisiere_kopf(text or "")


def _namen_aehnlich(a: str | None, b: str | None) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    kurz, lang = sorted((na, nb), key=len)
    return na == nb or (len(kurz) >= 5 and kurz in lang)


def pruefe_zuordnung(ziel: str, kopf: list[str], zuordnung: dict[str, str]) -> None:
    felder = _felder(ziel)
    unbekannt = [schluessel for schluessel in zuordnung if schluessel not in felder]
    if unbekannt:
        raise ImportAbgelehnt(f"Unbekannte Felder: {', '.join(unbekannt)}.")
    fehlend = [spalte for spalte in zuordnung.values() if spalte not in kopf]
    if fehlend:
        raise ImportAbgelehnt(f"Diese Spalten gibt es in der Datei nicht: {', '.join(fehlend)}.")
    doppelt = {spalte for spalte in zuordnung.values() if list(zuordnung.values()).count(spalte) > 1}
    if doppelt:
        raise ImportAbgelehnt(f"Die Spalte {', '.join(sorted(doppelt))} ist mehreren Feldern zugeordnet.")
    if ziel == "kontakte" and not ({"name", "vorname", "nachname"} & zuordnung.keys()):
        raise ImportAbgelehnt("Bitte eine Spalte für den Namen (oder Vor- und Nachname) zuordnen.")
    if ziel == "produkte" and "bezeichnung" not in zuordnung:
        raise ImportAbgelehnt("Bitte eine Spalte für die Bezeichnung zuordnen.")
    if ziel == "rechnungen":
        for pflicht, text in (("rechnungsnummer", "die Rechnungsnummer"), ("rechnungsdatum", "das Rechnungsdatum")):
            if pflicht not in zuordnung:
                raise ImportAbgelehnt(f"Bitte eine Spalte für {text} zuordnen.")
        if not ({"kunde", "kundennummer"} & zuordnung.keys()):
            raise ImportAbgelehnt("Bitte eine Spalte für den Kunden (Name oder Kundennummer) zuordnen.")
        if not ({"brutto", "netto", "netto_19", "netto_7", "netto_0"} & zuordnung.keys()):
            raise ImportAbgelehnt("Bitte eine Spalte für den Betrag (Brutto oder Netto) zuordnen.")


def schlage_dezimal_fuer_zuordnung_vor(ziel: str, tabelle: Tabelle, zuordnung: dict[str, str]) -> str:
    felder = _felder(ziel)
    index = {name: nummer for nummer, name in enumerate(tabelle.kopf)}
    werte = [
        zeile[index[spalte]]
        for schluessel, spalte in zuordnung.items()
        if felder[schluessel].typ in ("geld", "prozent", "ust_satz") and spalte in index
        for zeile in tabelle.zeilen[:50]
    ]
    return schlage_dezimal_vor(werte)


# ---------------------------------------------------------------------------
# Zeilen lesen


def _lese_zeile(ziel: str, felder: dict[str, Feld], roh: dict[str, str], optionen: Optionen) -> tuple[dict[str, Any], list[str], list[str]]:
    werte: dict[str, Any] = {}
    fehler: list[str] = []
    hinweise: list[str] = []

    def lies(schluessel: str, land: str = "DE") -> None:
        if schluessel not in roh:
            return
        feld = felder[schluessel]
        try:
            wert = wandle(feld, roh[schluessel], dezimal=optionen.dezimal, land=land)
        except WertFehler as exc:
            (fehler if feld.pflicht else hinweise).append(
                str(exc) if feld.pflicht else f"{exc} Das Feld bleibt leer."
            )
            return
        if wert is not None:
            werte[schluessel] = wert

    if ziel == "kontakte":
        lies("land")
        for schluessel in felder:
            if schluessel != "land":
                lies(schluessel, werte.get("land", "DE"))
        _vervollstaendige_kontakt(werte, roh, fehler)
    else:
        for schluessel in felder:
            lies(schluessel)
        _vervollstaendige_produkt(werte, fehler, hinweise, optionen)
    return werte, fehler, hinweise


def _vervollstaendige_kontakt(werte: dict[str, Any], roh: dict[str, str], fehler: list[str]) -> None:
    hausnummer = werte.pop("hausnummer", None)
    if hausnummer:
        werte["strasse"] = f"{werte.get('strasse', '')} {hausnummer}".strip()
    person = " ".join(teil for teil in (werte.get("vorname"), werte.get("nachname")) if teil)
    if not werte.get("name"):
        if person:
            werte["name"] = person
            werte.setdefault("ist_geschaeftskunde", False)
        elif not any(f.startswith("Name") for f in fehler):
            fehler.append("Name fehlt.")
    werte.setdefault("typ", "kunde")
    werte.setdefault("land", "DE")
    werte.setdefault("ist_geschaeftskunde", True)


def _vervollstaendige_produkt(werte: dict[str, Any], fehler: list[str], hinweise: list[str], optionen: Optionen) -> None:
    if not werte.get("bezeichnung") and not any(f.startswith("Bezeichnung") for f in fehler):
        fehler.append("Bezeichnung fehlt.")
    if "ust_satz" not in werte:
        werte["ust_satz"] = optionen.standard_ust_satz
    brutto = werte.pop("bruttopreis", None)
    if "einzelpreis" not in werte:
        if brutto is not None:
            werte["einzelpreis"] = (brutto / (1 + werte["ust_satz"] / 100)).quantize(Decimal("0.01"))
        else:
            werte["einzelpreis"] = Decimal("0.00")
            hinweise.append("Kein Preis angegeben, 0,00 € übernommen.")
    werte.setdefault("einheit", "Stück")
    werte.setdefault("aktiv", True)


# ---------------------------------------------------------------------------
# Doppelte erkennen


@dataclass
class _Treffer:
    eintrag: dict[str, Any] | None = None
    grund: str | None = None
    konflikt: str | None = None


class _Index:
    """Vergleichsschluessel fuer Bestand und bereits gelesene Zeilen derselben Datei."""

    def __init__(self, ziel: str):
        self.ziel = ziel
        self.nummer: dict[str, dict] = {}
        self.ust: dict[str, dict] = {}
        self.email: dict[str, dict] = {}
        self.name_plz: dict[tuple[str, str], dict] = {}
        self.bezeichnung: dict[str, dict] = {}

    def nimm_auf(self, eintrag: dict[str, Any]) -> None:
        if self.ziel == "kontakte":
            if eintrag.get("kundennummer"):
                self.nummer.setdefault(_norm(eintrag["kundennummer"]), eintrag)
            if eintrag.get("ust_id"):
                self.ust.setdefault(eintrag["ust_id"].replace(" ", "").upper(), eintrag)
            if eintrag.get("email"):
                self.email.setdefault(eintrag["email"].casefold(), eintrag)
            self.name_plz.setdefault((_norm(eintrag.get("name")), _norm(eintrag.get("plz"))), eintrag)
        else:
            if eintrag.get("artikelnummer"):
                self.nummer.setdefault(_norm(eintrag["artikelnummer"]), eintrag)
            self.bezeichnung.setdefault(_norm(eintrag.get("bezeichnung")), eintrag)

    def finde(self, werte: dict[str, Any]) -> _Treffer:
        if self.ziel == "kontakte":
            name = werte.get("name")
            nummer = werte.get("kundennummer")
            if nummer and (eintrag := self.nummer.get(_norm(nummer))):
                if _namen_aehnlich(eintrag.get("name"), name):
                    return _Treffer(eintrag, "gleiche Kundennummer")
                return _Treffer(konflikt=f"Die Kundennummer {nummer} gehört bereits zu „{eintrag.get('name')}“.")
            if werte.get("ust_id") and (eintrag := self.ust.get(werte["ust_id"])):
                return _Treffer(eintrag, "gleiche USt-IdNr.")
            if werte.get("email") and (eintrag := self.email.get(werte["email"].casefold())) and _namen_aehnlich(eintrag.get("name"), name):
                return _Treffer(eintrag, "gleiche E-Mail-Adresse")
            if eintrag := self.name_plz.get((_norm(name), _norm(werte.get("plz")))):
                return _Treffer(eintrag, "gleicher Name und gleiche PLZ")
            return _Treffer()
        nummer = werte.get("artikelnummer")
        if nummer and (eintrag := self.nummer.get(_norm(nummer))):
            if _namen_aehnlich(eintrag.get("bezeichnung"), werte.get("bezeichnung")):
                return _Treffer(eintrag, "gleiche Artikelnummer")
            return _Treffer(konflikt=f"Die Artikelnummer {nummer} gehört bereits zu „{eintrag.get('bezeichnung')}“.")
        if eintrag := self.bezeichnung.get(_norm(werte.get("bezeichnung"))):
            return _Treffer(eintrag, "gleiche Bezeichnung")
        return _Treffer()


_KONTAKT_SPALTEN = (
    "name", "strasse", "plz", "ort", "land", "ust_id", "email", "ist_geschaeftskunde", "kundennummer", "typ", "anrede",
    "vorname", "nachname", "telefon", "notiz", "steuernummer", "iban", "bic", "zahlungsziel_tage", "skonto_prozent",
    "skonto_tage", "leitweg_id",
)
_PRODUKT_SPALTEN = ("bezeichnung", "beschreibung", "einzelpreis", "ust_satz", "einheit", "aktiv", "artikelnummer")
# Felder, die "ergaenzen" fuellen darf, wenn sie im Bestand leer sind.
_ERGAENZBAR = {
    "kontakte": ("strasse", "plz", "ort", "ust_id", "email", "kundennummer", "anrede", "vorname", "nachname", "telefon",
                 "notiz", "steuernummer", "iban", "bic", "zahlungsziel_tage", "skonto_prozent", "skonto_tage", "leitweg_id"),
    "produkte": ("beschreibung", "artikelnummer"),
}


def _bestand(db: Session, ziel: str, mandant_id: str) -> list[dict[str, Any]]:
    model, spalten = (Kontakt, _KONTAKT_SPALTEN) if ziel == "kontakte" else (Produkt, _PRODUKT_SPALTEN)
    return [
        {"id": obj.id, **{spalte: getattr(obj, spalte) for spalte in spalten}}
        for obj in db.query(model).filter(model.mandant_id == mandant_id)
    ]


def _ergaenzungen(ziel: str, bestand: dict[str, Any], werte: dict[str, Any]) -> dict[str, Any]:
    neu = {
        schluessel: werte[schluessel]
        for schluessel in _ERGAENZBAR[ziel]
        if werte.get(schluessel) not in (None, "") and bestand.get(schluessel) in (None, "")
    }
    if ziel == "kontakte" and werte.get("typ") and bestand.get("typ") and {werte["typ"], bestand["typ"]} == {"kunde", "lieferant"}:
        neu["typ"] = "beide"
    return neu


# ---------------------------------------------------------------------------
# Probelauf


def pruefe(db: Session, *, mandant_id: str, ziel: str, tabelle: Tabelle, optionen: Optionen) -> Bericht:
    pruefe_zuordnung(ziel, tabelle.kopf, optionen.zuordnung)
    if ziel == "rechnungen":
        from app.altrechnungen import importe  # spaet, importe.py braucht dieses Modul

        return importe.pruefe(db, mandant_id=mandant_id, tabelle=tabelle, optionen=optionen)
    felder = _felder(ziel)
    index_spalte = {name: nummer for nummer, name in enumerate(tabelle.kopf)}

    bestand_index = _Index(ziel)
    for eintrag in _bestand(db, ziel, mandant_id):
        bestand_index.nimm_auf(eintrag)
    datei_index = _Index(ziel)

    zeilen: list[Zeile] = []
    for nummer, zelle in enumerate(tabelle.zeilen, start=2):
        roh = {schluessel: zelle[index_spalte[spalte]] for schluessel, spalte in optionen.zuordnung.items()}
        werte, fehler, hinweise = _lese_zeile(ziel, felder, roh, optionen)
        anzeige = str(werte.get("name") or werte.get("bezeichnung") or next((w for w in roh.values() if w.strip()), ""))
        zeile = Zeile(nummer=nummer, status="neu", anzeige=anzeige, werte=werte, fehler=fehler, hinweise=hinweise)

        if not fehler:
            in_datei = datei_index.finde(werte)
            if in_datei.eintrag is not None:
                zeile.status, zeile.grund = "doppelt", f"wie Zeile {in_datei.eintrag['_zeile']} ({in_datei.grund})"
            else:
                treffer = bestand_index.finde(werte)
                if treffer.konflikt:
                    fehler.append(treffer.konflikt)
                elif treffer.eintrag is not None:
                    zeile.ziel_id, zeile.grund = treffer.eintrag["id"], treffer.grund
                    ergaenzung = _ergaenzungen(ziel, treffer.eintrag, werte) if optionen.doppelte == "ergaenzen" else {}
                    if ergaenzung:
                        zeile.status = "ergaenzen"
                        zeile.werte = ergaenzung
                        zeile.ergaenzt = [felder[s].label for s in ergaenzung]
                    else:
                        zeile.status = "vorhanden"
            # Auch Zeilen, die zum Bestand passen, merken: eine spaetere gleiche Zeile ist doppelt.
            if not fehler and zeile.status != "doppelt":
                datei_index.nimm_auf({**werte, "_zeile": nummer})
        if fehler:
            zeile.status = "fehler"
        zeilen.append(zeile)
    return Bericht(ziel=ziel, zeilen=zeilen)


# ---------------------------------------------------------------------------
# Import


def importiere(
    db: Session, *, mandant_id: str, user_id: str, ziel: str, tabelle: Tabelle, optionen: Optionen,
    dateiname: str, datei_hash: str, datei_inhalt: bytes | None = None,
) -> tuple[Datenimport, Bericht]:
    if ziel == "rechnungen":
        from app.altrechnungen import importe

        pruefe_zuordnung(ziel, tabelle.kopf, optionen.zuordnung)
        return importe.importiere(
            db, mandant_id=mandant_id, user_id=user_id, tabelle=tabelle, optionen=optionen, dateiname=dateiname,
            datei_hash=datei_hash, datei_inhalt=datei_inhalt,
        )
    bericht = pruefe(db, mandant_id=mandant_id, ziel=ziel, tabelle=tabelle, optionen=optionen)
    fehler = bericht.anzahl("fehler")
    if fehler and not optionen.fehlerhafte_auslassen:
        raise ImportAbgelehnt(
            f"{fehler} Zeilen haben Fehler. Bitte korrigieren oder ausdrücklich ohne diese Zeilen importieren."
        )
    neue = [zeile for zeile in bericht.zeilen if zeile.status == "neu"]
    ergaenzte = [zeile for zeile in bericht.zeilen if zeile.status == "ergaenzen"]
    if not neue and not ergaenzte:
        raise ImportAbgelehnt("Nichts zu importieren: Alle Zeilen sind schon vorhanden oder doppelt.")

    protokoll = Datenimport(
        mandant_id=mandant_id, user_id=user_id, ziel=ziel, dateiname=dateiname[:255] or "unbenannt", datei_hash=datei_hash,
        anzahl_neu=len(neue), anzahl_ergaenzt=len(ergaenzte),
        anzahl_uebersprungen=bericht.anzahl("vorhanden") + bericht.anzahl("doppelt"), anzahl_fehler=fehler,
    )
    db.add(protokoll)
    db.flush()

    model = Kontakt if ziel == "kontakte" else Produkt
    spalten = _KONTAKT_SPALTEN if ziel == "kontakte" else _PRODUKT_SPALTEN
    for zeile in neue:
        daten = {schluessel: wert for schluessel, wert in zeile.werte.items() if schluessel in spalten and schluessel != "iban"}
        obj = model(mandant_id=mandant_id, import_id=protokoll.id, **daten)
        if ziel == "kontakte":
            setze_iban(obj, zeile.werte.get("iban"))
        db.add(obj)
    for zeile in ergaenzte:
        obj = db.get(model, zeile.ziel_id)
        if obj is None or obj.mandant_id != mandant_id:
            continue
        for schluessel, wert in zeile.werte.items():
            if schluessel == "iban":
                setze_iban(obj, wert)
            else:
                setattr(obj, schluessel, wert)

    record_audit(
        db, aktion="stammdaten_import", mandant_id=mandant_id, user_id=user_id,
        kontext=f"{protokoll.id} {ziel} neu {len(neue)} ergaenzt {len(ergaenzte)} fehler {fehler}",
    )
    return protokoll, bericht


def mache_rueckgaengig(db: Session, *, mandant_id: str, user_id: str, protokoll: Datenimport) -> tuple[int, int]:
    """Loescht die vom Import angelegten Datensaetze, die noch nirgends verwendet werden.
    Ergaenzte Felder bleiben. Gibt (geloescht, behalten) zurueck."""
    if protokoll.rueckgaengig_am is not None:
        raise ImportAbgelehnt("Dieser Import wurde bereits rückgängig gemacht.")
    if protokoll.ziel == "rechnungen":
        from app.altrechnungen import importe

        return importe.mache_rueckgaengig(db, mandant_id=mandant_id, user_id=user_id, protokoll=protokoll)
    geloescht = behalten = 0
    if protokoll.ziel == "kontakte":
        for kontakt in db.query(Kontakt).filter(Kontakt.mandant_id == mandant_id, Kontakt.import_id == protokoll.id):
            if kontakt_wird_verwendet(db, kontakt.id):
                behalten += 1
            else:
                db.delete(kontakt)
                geloescht += 1
    else:
        for produkt in db.query(Produkt).filter(Produkt.mandant_id == mandant_id, Produkt.import_id == protokoll.id):
            if db.scalar(select(exists().where(Lagerbewegung.produkt_id == produkt.id))):
                behalten += 1
            else:
                db.delete(produkt)
                geloescht += 1
    protokoll.rueckgaengig_am = datetime.now(timezone.utc)
    record_audit(
        db, aktion="stammdaten_import_rueckgaengig", mandant_id=mandant_id, user_id=user_id,
        kontext=f"{protokoll.id} geloescht {geloescht} behalten {behalten}",
    )
    return geloescht, behalten
