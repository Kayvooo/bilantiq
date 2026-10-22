"""Suche ueber Kontakte, Rechnungen, Angebote, Belege und Produkte.

Die durchsuchten Felder sind groesstenteils verschluesselt, deshalb kann die Datenbank nicht
selbst suchen: Es werden pro Typ die neuesten Zeilen geladen und in Python verglichen. Geladen
werden nur die Spalten, die zum Vergleichen und Anzeigen gebraucht werden (Entschluesselung
ist der teure Teil). Ueber der Obergrenze wird nicht mehr alles durchsucht, das meldet die
Antwort ehrlich in `unvollstaendig`, statt Treffer stillschweigend zu verschweigen."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.altrechnungen.models import Altrechnung
from app.invoices.models import Invoice, Kontakt
from app.produkte.models import Produkt
from app.quotes.models import Quote
from app.receipts.models import Receipt

MAX_ZEILEN_PRO_TYP = 5000
MIN_ZEICHEN = 2

TYP_LABEL = {"kunde": "Kunde", "lieferant": "Lieferant", "beide": "Kunde und Lieferant"}
RECHNUNG_STATUS = {"entwurf": "Entwurf", "final": "offen", "storniert": "storniert"}
ANGEBOT_STATUS = {"entwurf": "Entwurf", "versendet": "versendet", "angenommen": "angenommen", "abgelehnt": "abgelehnt"}
BELEG_STATUS = {"neu": "neu", "geprueft": "geprüft", "unklar": "unklar", "gebucht": "gebucht"}


@dataclass
class Treffer:
    id: str
    titel: str
    untertitel: str | None
    ziel: str


@dataclass
class Gruppe:
    typ: str
    label: str
    treffer: list[Treffer]
    gesamt: int


_KOMBINIERENDE_ZEICHEN = re.compile("[\u0300-\u036f]")


def normalisiere(text: str) -> str:
    """Kleinschreibung ohne Akzente und Umlaut-Punkte ("Müller" findet "muller" und "Muller"),
    ss statt scharfem s."""
    klein = text.casefold()
    if klein.isascii():  # haeufigster Fall, ohne Unicode-Zerlegung
        return klein
    return _KOMBINIERENDE_ZEICHEN.sub("", unicodedata.normalize("NFKD", klein))


def zerlege_suchbegriff(roh: str) -> list[str]:
    return [t for t in normalisiere(roh).split() if t]


# Ein Feld ist (normalisierter Text, nur_anfang). Betraege zaehlen nur vom Anfang her: "119"
# soll 119,00 und 1.190,00 finden, aber nicht 2.119,00.
Feld = tuple[str, bool]


def text_feld(wert: str | None) -> Feld | None:
    return (normalisiere(wert), False) if wert else None


def betrag_felder(betrag: Decimal | None) -> list[Feld]:
    if betrag is None:
        return []
    mit_tausender = f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    ohne_tausender = f"{betrag:.2f}".replace(".", ",")
    englisch = f"{betrag:.2f}"
    return [(v, True) for v in (mit_tausender, ohne_tausender, englisch)]


def _rang_im_feld(token: str, wert: str, nur_anfang: bool) -> int | None:
    if nur_anfang:
        return 1 if wert.startswith(token) else None
    if wert.startswith(token):
        return 0
    if re.search(r"(?<![a-z0-9])" + re.escape(token), wert):
        return 1
    if token in wert:
        return 2
    return None


def bewerte(tokens: list[str], felder: list[Feld | None]) -> int | None:
    """Kleinere Zahl = besserer Treffer; None = kein Treffer. Jeder Suchbegriff muss in
    mindestens einem Feld vorkommen (UND), der beste Rang je Begriff wird addiert."""
    gesamt = 0
    for token in tokens:
        bester: int | None = None
        for feld in felder:
            if feld is None:
                continue
            rang = _rang_im_feld(token, feld[0], feld[1])
            if rang is not None and (bester is None or rang < bester):
                bester = rang
                if bester == 0:
                    break
        if bester is None:
            return None
        gesamt += bester
    return gesamt


def _geld(betrag: Decimal | None) -> str | None:
    if betrag is None:
        return None
    return f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _datum(wert: date | None) -> str | None:
    return wert.strftime("%d.%m.%Y") if wert else None


def _verbinde(*teile: str | None) -> str | None:
    text = " · ".join(t for t in teile if t)
    return text or None


def _auswahl(kandidaten: list[tuple[int, int, Treffer]], limit: int, typ: str, label: str) -> Gruppe:
    # nach Rang, bei Gleichstand neueste zuerst (Reihenfolge der Abfrage)
    kandidaten.sort(key=lambda k: (k[0], k[1]))
    return Gruppe(typ=typ, label=label, treffer=[k[2] for k in kandidaten[:limit]], gesamt=len(kandidaten))


def _kontakte(db: Session, mandant_id: str, tokens: list[str], limit: int):
    zeilen = db.execute(
        select(
            Kontakt.id, Kontakt.name, Kontakt.vorname, Kontakt.nachname, Kontakt.kundennummer, Kontakt.email,
            Kontakt.ort, Kontakt.typ, Kontakt.archiviert_am,
        )
        .where(Kontakt.mandant_id == mandant_id)
        .order_by(Kontakt.erstellt_am.desc())
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    zeilen = zeilen[:MAX_ZEILEN_PRO_TYP]
    namen = {z.id: z.name for z in zeilen}
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen):
        ansprechpartner = " ".join(t for t in (z.vorname, z.nachname) if t)
        rang = bewerte(tokens, [
            text_feld(z.name), text_feld(ansprechpartner), text_feld(z.kundennummer), text_feld(z.email), text_feld(z.ort),
        ])
        if rang is None:
            continue
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.name,
            untertitel=_verbinde(TYP_LABEL.get(z.typ), z.kundennummer, z.ort, "archiviert" if z.archiviert_am else None),
            ziel="contacts",
        )))
    return _auswahl(kandidaten, limit, "kontakte", "Kontakte"), abgeschnitten, namen


def _rechnungsstatus(status: str, bezahlt_am: date | None, faelligkeitsdatum: date) -> str:
    """Gleiche Unterscheidung wie die Rechnungsliste (anzeige_status): bezahlt, ueberfaellig, offen."""
    if status == "final":
        if bezahlt_am is not None:
            return "bezahlt"
        if faelligkeitsdatum < date.today():
            return "überfällig"
    return RECHNUNG_STATUS.get(status, status)


def _rechnungen(db: Session, mandant_id: str, tokens: list[str], limit: int, namen: dict[str, str]):
    zeilen = db.execute(
        select(
            Invoice.id, Invoice.nummer, Invoice.status, Invoice.kontakt_id, Invoice.brutto_gesamt, Invoice.betreff,
            Invoice.referenznummer, Invoice.bezahlt_am, Invoice.faelligkeitsdatum,
        )
        .where(Invoice.mandant_id == mandant_id)
        .order_by(Invoice.erstellt_am.desc())
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen[:MAX_ZEILEN_PRO_TYP]):
        kunde = namen.get(z.kontakt_id)
        rang = bewerte(tokens, [
            text_feld(z.nummer), text_feld(kunde), text_feld(z.betreff), text_feld(z.referenznummer), *betrag_felder(z.brutto_gesamt),
        ])
        if rang is None:
            continue
        status = _rechnungsstatus(z.status, z.bezahlt_am, z.faelligkeitsdatum)
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.nummer or "Rechnungsentwurf",
            untertitel=_verbinde(kunde, _geld(z.brutto_gesamt), status), ziel="invoices",
        )))
    return _auswahl(kandidaten, limit, "rechnungen", "Rechnungen"), abgeschnitten


def _altrechnungen(db: Session, mandant_id: str, tokens: list[str], limit: int, namen: dict[str, str]):
    zeilen = db.execute(
        select(Altrechnung.id, Altrechnung.nummer, Altrechnung.kontakt_id, Altrechnung.brutto)
        .where(Altrechnung.mandant_id == mandant_id)
        .order_by(Altrechnung.rechnungsdatum.desc(), Altrechnung.erstellt_am.desc())
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen[:MAX_ZEILEN_PRO_TYP]):
        kunde = namen.get(z.kontakt_id)
        rang = bewerte(tokens, [text_feld(z.nummer), text_feld(kunde), *betrag_felder(z.brutto)])
        if rang is None:
            continue
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.nummer, untertitel=_verbinde(kunde, _geld(z.brutto), "aus dem Altsystem"), ziel="invoices",
        )))
    return _auswahl(kandidaten, limit, "altrechnungen", "Rechnungen aus dem Altsystem"), abgeschnitten


def _angebote(db: Session, mandant_id: str, tokens: list[str], limit: int, namen: dict[str, str]):
    zeilen = db.execute(
        select(Quote.id, Quote.nummer, Quote.status, Quote.kontakt_id, Quote.brutto_gesamt)
        .where(Quote.mandant_id == mandant_id)
        .order_by(Quote.erstellt_am.desc())
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen[:MAX_ZEILEN_PRO_TYP]):
        kunde = namen.get(z.kontakt_id)
        rang = bewerte(tokens, [text_feld(z.nummer), text_feld(kunde), *betrag_felder(z.brutto_gesamt)])
        if rang is None:
            continue
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.nummer or "Angebotsentwurf",
            untertitel=_verbinde(kunde, _geld(z.brutto_gesamt), ANGEBOT_STATUS.get(z.status, z.status)), ziel="quotes",
        )))
    return _auswahl(kandidaten, limit, "angebote", "Angebote"), abgeschnitten


def _belege(db: Session, mandant_id: str, tokens: list[str], limit: int):
    zeilen = db.execute(
        select(Receipt.id, Receipt.anbieter, Receipt.betrag, Receipt.datum, Receipt.rechnungsnummer, Receipt.status)
        .where(Receipt.mandant_id == mandant_id)
        .order_by(Receipt.hochgeladen_am.desc())
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen[:MAX_ZEILEN_PRO_TYP]):
        rang = bewerte(tokens, [text_feld(z.anbieter), text_feld(z.rechnungsnummer), *betrag_felder(z.betrag)])
        if rang is None:
            continue
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.anbieter or "Beleg ohne erkannten Anbieter",
            untertitel=_verbinde(_geld(z.betrag), _datum(z.datum), BELEG_STATUS.get(z.status, z.status)), ziel="receipts",
        )))
    return _auswahl(kandidaten, limit, "belege", "Belege"), abgeschnitten


def _produkte(db: Session, mandant_id: str, tokens: list[str], limit: int):
    zeilen = db.execute(
        select(Produkt.id, Produkt.bezeichnung, Produkt.artikelnummer, Produkt.beschreibung, Produkt.einzelpreis)
        .where(Produkt.mandant_id == mandant_id)
        .order_by(Produkt.id)  # bezeichnung ist verschluesselt, Sortierung nach Namen folgt in Python
        .limit(MAX_ZEILEN_PRO_TYP + 1)
    ).all()
    abgeschnitten = len(zeilen) > MAX_ZEILEN_PRO_TYP
    zeilen = sorted(zeilen[:MAX_ZEILEN_PRO_TYP], key=lambda z: normalisiere(z.bezeichnung))
    kandidaten: list[tuple[int, int, Treffer]] = []
    for position, z in enumerate(zeilen):
        rang = bewerte(tokens, [text_feld(z.bezeichnung), text_feld(z.artikelnummer), text_feld(z.beschreibung)])
        if rang is None:
            continue
        kandidaten.append((rang, position, Treffer(
            id=z.id, titel=z.bezeichnung, untertitel=_verbinde(z.artikelnummer, _geld(z.einzelpreis)), ziel="produkte",
        )))
    return _auswahl(kandidaten, limit, "produkte", "Produkte"), abgeschnitten


def suche(db: Session, mandant_id: str, begriff: str, limit: int) -> tuple[list[Gruppe], list[str]]:
    """Gibt nur Gruppen mit Treffern zurueck sowie die Typen, bei denen die Obergrenze erreicht wurde."""
    tokens = zerlege_suchbegriff(begriff)
    if not tokens:
        return [], []
    kontakte, k_unvollstaendig, namen = _kontakte(db, mandant_id, tokens, limit)
    rechnungen, r_unvollstaendig = _rechnungen(db, mandant_id, tokens, limit, namen)
    altrechnungen, alt_unvollstaendig = _altrechnungen(db, mandant_id, tokens, limit, namen)
    angebote, a_unvollstaendig = _angebote(db, mandant_id, tokens, limit, namen)
    belege, b_unvollstaendig = _belege(db, mandant_id, tokens, limit)
    produkte, p_unvollstaendig = _produkte(db, mandant_id, tokens, limit)
    unvollstaendig = [
        typ for typ, flag in (
            ("kontakte", k_unvollstaendig), ("rechnungen", r_unvollstaendig), ("altrechnungen", alt_unvollstaendig),
            ("angebote", a_unvollstaendig),
            ("belege", b_unvollstaendig), ("produkte", p_unvollstaendig),
        ) if flag
    ]
    gruppen = [g for g in (kontakte, rechnungen, altrechnungen, angebote, belege, produkte) if g.gesamt]
    return gruppen, unvollstaendig
