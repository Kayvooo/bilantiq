"""Import der Rechnungsliste aus dem Altsystem (Stammdaten-Ziel "rechnungen").

Probelauf und Import laufen ueber denselben Code. Grundsaetze:
- Betraege und Steuersaetze werden nicht neu berechnet, nur auf Stimmigkeit geprueft. Ist der
  Steuersatz nicht eindeutig (gemischte Saetze), wird die Zeile abgelehnt statt zu raten.
- Fehler in Betrags-, Datums- und Statusfeldern sperren die Zeile, weil davon abhaengt, was als
  offen gilt. Fehler in Kundenfeldern sind nur Hinweise.
- Negative Betraege (Gutschriften), Stornos ohne Betrag und Entwuerfe werden nicht uebernommen.
- Bereits bezahlte Altrechnungen sind reines Archiv. Offene zaehlen erst, wenn die Zahlung in
  Bilantiq erfasst wird."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.altrechnungen import storage
from app.altrechnungen.models import Altrechnung
from app.altrechnungen.nummer import alnum as _alnum, nummer_hash
from app.altrechnungen.steuer import Anteil, SteuerFehler, anteile_als_json, bestimme_anteile
from app.core.audit_log import record as record_audit
from app.core.tabelle import Tabelle
from app.invoices.kontakte import kontakt_wird_verwendet
from app.invoices.models import Invoice, Kontakt
from app.stammdaten.felder import FELDER, Feld, normalisiere_kopf
from app.stammdaten.models import Datenimport
from app.stammdaten.service import Bericht, ImportAbgelehnt, Optionen, Zeile
from app.stammdaten.werte import WertFehler, wandle

ZIEL = "rechnungen"
# Betrag, Datum und Status bestimmen, was offen ist: ein Fehler dort sperrt die Zeile.
_STRIKT = frozenset((
    "rechnungsnummer", "rechnungsdatum", "netto", "ust", "brutto", "ust_satz", "netto_19", "netto_7", "netto_0",
    "offener_betrag", "bezahlt_am", "status",
))
_NETTO_JE_SATZ = {"netto_19": Decimal("19"), "netto_7": Decimal("7"), "netto_0": Decimal("0")}

_STATUS = {
    **dict.fromkeys(("bezahlt", "beglichen", "erledigt", "paid", "closed", "gezahlt", "ausgeglichen", "komplett bezahlt", "vollstaendig bezahlt"), "bezahlt"),
    **dict.fromkeys(("offen", "unbezahlt", "open", "ausstehend", "unpaid", "faellig", "ueberfaellig", "versendet", "gesendet", "sent"), "offen"),
    **dict.fromkeys(("teilbezahlt", "teilweise bezahlt", "teilzahlung", "partially paid", "anzahlung"), "teil"),
    **dict.fromkeys(("storniert", "storno", "cancelled", "canceled", "gestrichen"), "storniert"),
    **dict.fromkeys(("entwurf", "draft"), "entwurf"),
}
_STATUS = {normalisiere_kopf(schluessel): wert for schluessel, wert in _STATUS.items()}


@dataclass
class RechnungsBericht(Bericht):
    # Kunden, die der Import neu anlegen wuerde (Schluessel: Kundennummer oder Name, normalisiert).
    neue_kontakte: dict[str, dict[str, Any]] = field(default_factory=dict)


def _norm(text: str | None) -> str:
    return normalisiere_kopf(text or "")


def _namen_aehnlich(a: str | None, b: str | None) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    kurz, lang = sorted((na, nb), key=len)
    return na == nb or (len(kurz) >= 5 and kurz in lang)


# ---------------------------------------------------------------------------
# Zeilen lesen


def _lies_felder(felder: dict[str, Feld], roh: dict[str, str], optionen: Optionen) -> tuple[dict[str, Any], list[str], list[str]]:
    werte: dict[str, Any] = {}
    fehler: list[str] = []
    hinweise: list[str] = []
    for schluessel, feld in felder.items():
        if schluessel not in roh:
            continue
        try:
            wert = wandle(feld, roh[schluessel], dezimal=optionen.dezimal)
        except WertFehler as exc:
            text = str(exc)
            if "negativ" in text:
                text += " Gutschriften und Stornorechnungen werden in dieser Version nicht übernommen."
            if schluessel in _STRIKT:
                fehler.append(text)
            else:
                hinweise.append(f"{text} Das Feld bleibt leer.")
            continue
        if wert is not None:
            werte[schluessel] = wert
    return werte, fehler, hinweise


def _status(werte: dict[str, Any], fehler: list[str]) -> str | None:
    roh = werte.get("status")
    if roh is None:
        return None
    status = _STATUS.get(normalisiere_kopf(roh))
    if status is None:
        fehler.append(f"Status „{roh}“ kenne ich nicht (erkannt: offen, bezahlt, teilbezahlt, storniert).")
    elif status == "entwurf":
        fehler.append("Entwürfe sind noch keine Rechnungen und werden nicht übernommen.")
    return status


def _betraege(werte: dict[str, Any], fehler: list[str]) -> tuple[Decimal, list[Anteil]] | None:
    netto_je_satz = {satz: werte[name] for name, satz in _NETTO_JE_SATZ.items() if name in werte}
    try:
        brutto, anteile = bestimme_anteile(
            netto=werte.get("netto"), ust=werte.get("ust"), brutto=werte.get("brutto"), satz=werte.get("ust_satz"),
            netto_je_satz=netto_je_satz,
        )
    except SteuerFehler as exc:
        fehler.append(str(exc))
        return None
    if brutto <= 0:
        fehler.append("Der Rechnungsbetrag muss größer als 0 sein.")
        return None
    return brutto, anteile


def _offener_betrag(werte: dict[str, Any], status: str | None, brutto: Decimal, fehler: list[str]) -> Decimal | None:
    offen = werte.get("offener_betrag")
    erledigt = status in ("bezahlt", "storniert") or werte.get("bezahlt_am") is not None
    if offen is not None:
        if offen > brutto:
            fehler.append(f"Der offene Betrag ({offen:.2f} €) ist größer als der Rechnungsbetrag ({brutto:.2f} €).")
            return None
        if offen > 0 and erledigt:
            fehler.append("Die Zeile ist als bezahlt oder storniert markiert, hat aber einen offenen Betrag.")
            return None
        return offen
    if erledigt:
        return Decimal("0.00")
    if status == "teil":
        fehler.append("Status „teilbezahlt“ ohne Spalte „Offener Betrag“: Bitte den offenen Betrag zuordnen.")
        return None
    return brutto


# ---------------------------------------------------------------------------
# Kunden zuordnen


@dataclass
class _KontaktZeile:
    id: str
    name: str
    kundennummer: str | None


class _KontaktIndex:
    def __init__(self, db: Session, mandant_id: str):
        self.nach_nummer: dict[str, list[_KontaktZeile]] = {}
        self.nach_name: dict[str, list[_KontaktZeile]] = {}
        spalten = select(Kontakt.id, Kontakt.name, Kontakt.kundennummer).where(Kontakt.mandant_id == mandant_id)
        for kontakt_id, name, nummer in db.execute(spalten):
            zeile = _KontaktZeile(kontakt_id, name, nummer)
            if nummer:
                self.nach_nummer.setdefault(_norm(nummer), []).append(zeile)
            self.nach_name.setdefault(_norm(name), []).append(zeile)


def _kunde_zuordnen(
    index: _KontaktIndex, werte: dict[str, Any], optionen: Optionen, neue: dict[str, dict[str, Any]],
    fehler: list[str], hinweise: list[str],
) -> None:
    """Setzt werte["_kontakt_id"] (vorhandener Kontakt) oder werte["_neuer_kontakt"] (Schluessel)."""
    nummer, name = werte.get("kundennummer"), werte.get("kunde")
    if not nummer and not name:
        fehler.append("Kunde fehlt: Bitte Kundenname oder Kundennummer zuordnen.")
        return
    if nummer and (treffer := index.nach_nummer.get(_norm(nummer))):
        if len(treffer) > 1:
            fehler.append(f"Die Kundennummer {nummer} gehört mehreren Kontakten. Bitte die Kontakte bereinigen.")
        elif name and not _namen_aehnlich(treffer[0].name, name):
            fehler.append(f"Die Kundennummer {nummer} gehört zu „{treffer[0].name}“, in der Datei steht „{name}“.")
        else:
            werte["_kontakt_id"] = treffer[0].id
        return
    if name:
        treffer = index.nach_name.get(_norm(name), [])
        if len(treffer) == 1:
            werte["_kontakt_id"] = treffer[0].id
            if nummer:
                hinweise.append(f"Die Kundennummer {nummer} ist bei „{treffer[0].name}“ nicht hinterlegt. Zuordnung über den Namen.")
            return
        if len(treffer) > 1:
            fehler.append(f"Mehrere Kontakte heißen „{name}“. Bitte die Kundennummer zuordnen.")
            return
    if not optionen.fehlende_kunden_anlegen:
        fehler.append(
            f"Kunde „{name or nummer}“ gibt es noch nicht. Bitte zuerst die Kontakte importieren "
            "oder „Fehlende Kunden anlegen“ wählen."
        )
        return
    schluessel = _norm(nummer) or _norm(name)
    eintrag = neue.setdefault(schluessel, {"name": name, "kundennummer": nummer})
    eintrag["name"] = eintrag.get("name") or name
    eintrag["kundennummer"] = eintrag.get("kundennummer") or nummer
    werte["_neuer_kontakt"] = schluessel
    hinweise.append(f"Kunde „{name or nummer}“ wird neu angelegt.")


# ---------------------------------------------------------------------------
# Probelauf


def pruefe(db: Session, *, mandant_id: str, tabelle: Tabelle, optionen: Optionen) -> RechnungsBericht:
    felder = {feld.schluessel: feld for feld in FELDER[ZIEL]}
    spalte = {name: nummer for nummer, name in enumerate(tabelle.kopf)}
    index = _KontaktIndex(db, mandant_id)
    eigene_nummern = {_alnum(n) for n in db.scalars(
        select(Invoice.nummer).where(Invoice.mandant_id == mandant_id, Invoice.nummer.is_not(None))
    )}
    bekannt = set(db.scalars(select(Altrechnung.nummer_hash).where(Altrechnung.mandant_id == mandant_id)))
    in_datei: dict[str, int] = {}
    neue: dict[str, dict[str, Any]] = {}
    heute = date.today()

    zeilen: list[Zeile] = []
    for nummer, zelle in enumerate(tabelle.zeilen, start=2):
        roh = {schluessel: zelle[spalte[name]] for schluessel, name in optionen.zuordnung.items()}
        werte, fehler, hinweise = _lies_felder(felder, roh, optionen)
        rechnungsnummer = werte.get("rechnungsnummer")
        kunde = werte.get("kunde") or werte.get("kundennummer")
        anzeige = " · ".join(str(t) for t in (rechnungsnummer, kunde) if t) or next((w for w in roh.values() if w.strip()), "")
        zeile = Zeile(nummer=nummer, status="neu", anzeige=anzeige, werte=werte, fehler=fehler, hinweise=hinweise)
        zeilen.append(zeile)

        if not rechnungsnummer:
            if not any("Rechnungsnummer" in f for f in fehler):
                fehler.append("Rechnungsnummer fehlt.")
        elif not _alnum(rechnungsnummer):
            fehler.append("Die Rechnungsnummer enthält weder Ziffern noch Buchstaben.")
        elif _alnum(rechnungsnummer) in eigene_nummern:
            fehler.append(f"Die Nummer {rechnungsnummer} gibt es schon als Rechnung in Bilantiq.")
        else:
            hash_ = nummer_hash(mandant_id, rechnungsnummer)
            werte["_hash"] = hash_
            if hash_ in bekannt:
                zeile.status, zeile.grund = "vorhanden", "gleiche Rechnungsnummer"
                zeile.fehler.clear()  # schon im Archiv: Rest der Zeile ist egal
                continue
            if hash_ in in_datei:
                zeile.status, zeile.grund = "doppelt", f"wie Zeile {in_datei[hash_]} (gleiche Rechnungsnummer)"
                zeile.fehler.clear()
                continue

        if "rechnungsdatum" not in werte and not any("Rechnungsdatum" in f for f in fehler):
            fehler.append("Rechnungsdatum fehlt.")
        if "rechnungsdatum" in werte and werte["rechnungsdatum"] > heute + timedelta(days=1):
            fehler.append("Das Rechnungsdatum liegt in der Zukunft.")

        status = _status(werte, fehler)
        betraege = _betraege(werte, fehler)
        if betraege is not None:
            brutto, anteile = betraege
            werte["_brutto"], werte["_anteile"] = brutto, anteile
            offen = _offener_betrag(werte, status, brutto, fehler)
            if offen is not None:
                werte["_offen"] = offen
                werte["brutto"], werte["offener_betrag"] = brutto, offen
                if status == "storniert":
                    hinweise.append("Status „storniert“: wird als erledigt archiviert, offener Betrag 0,00 €.")
        _faelligkeit(werte, optionen, hinweise)
        _kunde_zuordnen(index, werte, optionen, neue, fehler, hinweise)

        if fehler:
            zeile.status = "fehler"
        elif "_hash" in werte:
            in_datei[werte["_hash"]] = nummer
    return RechnungsBericht(ziel=ZIEL, zeilen=zeilen, neue_kontakte=neue)


def _faelligkeit(werte: dict[str, Any], optionen: Optionen, hinweise: list[str]) -> None:
    rechnungsdatum = werte.get("rechnungsdatum")
    offen = werte.get("_offen")
    if rechnungsdatum is None or offen is None or offen <= 0:
        return
    if werte.get("faelligkeit") is None:
        werte["faelligkeit"] = rechnungsdatum + timedelta(days=optionen.zahlungsziel_tage)
        hinweise.append(f"Keine Fälligkeit angegeben: Rechnungsdatum plus {optionen.zahlungsziel_tage} Tage übernommen.")
    elif werte["faelligkeit"] < rechnungsdatum:
        hinweise.append("Die Fälligkeit liegt vor dem Rechnungsdatum.")


# ---------------------------------------------------------------------------
# Import


def importiere(
    db: Session, *, mandant_id: str, user_id: str, tabelle: Tabelle, optionen: Optionen, dateiname: str,
    datei_hash: str, datei_inhalt: bytes | None,
) -> tuple[Datenimport, RechnungsBericht]:
    bericht = pruefe(db, mandant_id=mandant_id, tabelle=tabelle, optionen=optionen)
    fehler = bericht.anzahl("fehler")
    if fehler and not optionen.fehlerhafte_auslassen:
        raise ImportAbgelehnt(
            f"{fehler} Zeilen haben Fehler. Bitte korrigieren oder ausdrücklich ohne diese Zeilen importieren."
        )
    neue = [zeile for zeile in bericht.zeilen if zeile.status == "neu"]
    if not neue:
        raise ImportAbgelehnt("Nichts zu importieren: Alle Zeilen sind schon vorhanden, doppelt oder fehlerhaft.")

    protokoll = Datenimport(
        mandant_id=mandant_id, user_id=user_id, ziel=ZIEL, dateiname=dateiname[:255] or "unbenannt", datei_hash=datei_hash,
        anzahl_neu=len(neue), anzahl_ergaenzt=0,
        anzahl_uebersprungen=bericht.anzahl("vorhanden") + bericht.anzahl("doppelt"), anzahl_fehler=fehler,
    )
    if datei_inhalt is not None:
        # Die Quelldatei bleibt als Nachweis der Uebernahme verschluesselt erhalten.
        protokoll.datei_referenz = storage.speichere_importdatei(mandant_id, datei_hash, tabelle.format, datei_inhalt)
    db.add(protokoll)
    db.flush()

    benoetigt = {zeile.werte["_neuer_kontakt"] for zeile in neue if "_neuer_kontakt" in zeile.werte}
    neue_ids: dict[str, str] = {}
    for schluessel in benoetigt:
        daten = bericht.neue_kontakte[schluessel]
        name = daten.get("name") or f"Kunde {daten['kundennummer']}"
        kontakt = Kontakt(
            mandant_id=mandant_id, import_id=protokoll.id, name=name, kundennummer=daten.get("kundennummer"),
            typ="kunde", land="DE", ist_geschaeftskunde=True,
        )
        db.add(kontakt)
        db.flush()
        neue_ids[schluessel] = kontakt.id

    try:
        for zeile in neue:
            w = zeile.werte
            db.add(Altrechnung(
                mandant_id=mandant_id, import_id=protokoll.id, kontakt_id=w.get("_kontakt_id") or neue_ids[w["_neuer_kontakt"]],
                nummer=w["rechnungsnummer"], nummer_hash=w["_hash"], rechnungsdatum=w["rechnungsdatum"],
                faelligkeit=w.get("faelligkeit"), brutto=w["_brutto"], offen_beim_import=w["_offen"], war_offen=w["_offen"] > 0,
                steueranteile=anteile_als_json(w["_anteile"]), bezahlt_im_altsystem_am=w.get("bezahlt_am"),
            ))
        db.flush()
    except IntegrityError as exc:
        raise ImportAbgelehnt(
            "Eine der Rechnungsnummern wurde gerade von einem anderen Import angelegt. Bitte den Probelauf wiederholen."
        ) from exc

    record_audit(
        db, aktion="stammdaten_import", mandant_id=mandant_id, user_id=user_id,
        kontext=f"{protokoll.id} {ZIEL} neu {len(neue)} neue_kontakte {len(neue_ids)} fehler {fehler}",
    )
    return protokoll, bericht


def mache_rueckgaengig(db: Session, *, mandant_id: str, user_id: str, protokoll: Datenimport) -> tuple[int, int]:
    """Entfernt die angelegten Altrechnungen, die noch unberuehrt sind (keine in Bilantiq erfasste Zahlung,
    kein PDF), danach die angelegten Kunden, die nirgends verwendet werden."""
    geloescht = behalten = 0
    for altrechnung in db.query(Altrechnung).filter(Altrechnung.mandant_id == mandant_id, Altrechnung.import_id == protokoll.id):
        if altrechnung.zahlungen or altrechnung.datei_referenz:
            behalten += 1
        else:
            db.delete(altrechnung)
            geloescht += 1
    db.flush()
    for kontakt in db.query(Kontakt).filter(Kontakt.mandant_id == mandant_id, Kontakt.import_id == protokoll.id):
        if kontakt_wird_verwendet(db, kontakt.id):
            behalten += 1
        else:
            db.delete(kontakt)
            geloescht += 1
    if protokoll.datei_referenz and not db.scalar(
        select(Altrechnung.id).where(Altrechnung.import_id == protokoll.id).limit(1)
    ):
        storage.loesche_importdatei(protokoll.datei_referenz)
        protokoll.datei_referenz = None
    protokoll.rueckgaengig_am = datetime.now(timezone.utc)
    record_audit(
        db, aktion="stammdaten_import_rueckgaengig", mandant_id=mandant_id, user_id=user_id,
        kontext=f"{protokoll.id} geloescht {geloescht} behalten {behalten}",
    )
    return geloescht, behalten
