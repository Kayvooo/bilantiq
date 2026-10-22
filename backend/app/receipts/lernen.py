"""Kategorien lernen: Was ein Nutzer bei einem Anbieter bestaetigt hat, wird beim naechsten
Beleg dieses Anbieters vorgeschlagen.

Bewusst ohne KI und ohne neue Tabelle: Die Historie sind die gebuchten Ausgaben des
eigenen Mandanten. Ihre Felder sind verschluesselt, deshalb wird in Python gruppiert
statt in SQL. Vorschlaege entstehen erst beim Lesen, damit sie auch fuer bereits
hochgeladene, noch offene Belege sofort gelten."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.core.kontenrahmen import ausgaben_konto
from app.receipts.ai_extraction import _COMPANY_SUFFIX
from app.receipts.models import Ausgabe, Receipt
from app.receipts.service import ist_unklar

HISTORIE_LIMIT = 500
MIN_TEILNAME_LAENGE = 5


def normalisiere_anbieter(name: str | None) -> str:
    """Vergleichsschluessel: klein geschrieben, ohne Rechtsform und Satzzeichen."""
    if not name:
        return ""
    text = _COMPANY_SUFFIX.sub(" ", name.casefold())
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _gleicher_anbieter(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    kurz, lang = (a, b) if len(a) <= len(b) else (b, a)
    return len(kurz) >= MIN_TEILNAME_LAENGE and re.search(rf"(?<!\w){re.escape(kurz)}(?!\w)", lang) is not None


@dataclass(frozen=True)
class LernVorschlag:
    kategorie: str
    konto: str
    ust_satz: Decimal | None
    confidence: float
    begruendung: str


@dataclass(frozen=True)
class _Eintrag:
    schluessel: str
    anbieter: str
    kategorie: str
    konto: str
    ust_satz: Decimal | None  # None bei gemischten Steuersaetzen


class HistorieIndex:
    def __init__(self, eintraege: list[_Eintrag]) -> None:
        self._eintraege = eintraege  # neueste zuerst

    @classmethod
    def laden(cls, db: Session, mandant_id: str, limit: int = HISTORIE_LIMIT) -> "HistorieIndex":
        zeilen = (
            db.query(Ausgabe)
            .options(selectinload(Ausgabe.steueranteile))
            .filter(Ausgabe.mandant_id == mandant_id)
            .order_by(Ausgabe.erstellt_am.desc())
            .limit(limit)
            .all()
        )
        eintraege = []
        for zeile in zeilen:
            schluessel = normalisiere_anbieter(zeile.anbieter)
            if schluessel:
                eintraege.append(_Eintrag(schluessel, zeile.anbieter, zeile.kategorie, zeile.konto, zeile.ust_satz))
        return cls(eintraege)

    def vorschlag(self, anbieter: str | None) -> LernVorschlag | None:
        schluessel = normalisiere_anbieter(anbieter)
        passend = [e for e in self._eintraege if _gleicher_anbieter(schluessel, e.schluessel)]
        if not passend:
            return None

        haeufigkeit: dict[tuple[str, str], int] = {}
        for eintrag in passend:  # neueste zuerst: bei Gleichstand gewinnt die zuerst gesehene Kombination
            kombi = (eintrag.kategorie, eintrag.konto)
            haeufigkeit[kombi] = haeufigkeit.get(kombi, 0) + 1
        rangfolge = sorted(haeufigkeit.items(), key=lambda paar: -paar[1])
        (kategorie, konto), anzahl = rangfolge[0]
        gesamt = len(passend)
        name = passend[0].anbieter

        if len(rangfolge) == 1:
            confidence = 0.85 if anzahl == 1 else 0.9 if anzahl == 2 else 0.95
            begruendung = f"Gelernt aus {anzahl} früherer Buchung bei {name}." if anzahl == 1 else (
                f"Gelernt aus {anzahl} früheren Buchungen bei {name}."
            )
        else:
            # Widerspruechliche Historie: nur eine klare Mehrheit ist ein Vorschlag.
            if anzahl < 2 or anzahl == rangfolge[1][1]:
                return None
            confidence = 0.65
            begruendung = f"Überwiegend gelernt: {anzahl} von {gesamt} früheren Buchungen bei {name}."

        saetze = {e.ust_satz for e in passend if (e.kategorie, e.konto) == (kategorie, konto)}
        ust_satz = next(iter(saetze)) if len(saetze) == 1 and None not in saetze else None
        return LernVorschlag(kategorie, konto, ust_satz, confidence, begruendung)


@dataclass(frozen=True)
class EffektiveVorschlaege:
    """Die fuer Anzeige und Buchung gueltigen Vorschlaege: OCR-Heuristik oder Gelerntes,
    je nachdem, was verlaesslicher ist."""

    kategorie: str | None
    kategorie_confidence: float | None
    konto: str
    ust_satz: Decimal | None
    ust_confidence: float | None
    begruendung: str | None
    gelernt: bool


def effektive_vorschlaege(receipt: Receipt, historie: HistorieIndex | None) -> EffektiveVorschlaege:
    kategorie = receipt.kategorie_vorschlag
    kategorie_conf = receipt.kategorie_vorschlag_confidence
    konto = ausgaben_konto(kategorie if not ist_unklar(kategorie_conf) else None)
    ust_satz, ust_conf = receipt.ust_satz, receipt.ust_satz_confidence
    begruendung = receipt.begruendung
    gelernt = False

    if historie is not None and not ist_unklar(receipt.anbieter_confidence):
        lern = historie.vorschlag(receipt.anbieter)
        if lern is not None and (ist_unklar(kategorie_conf) or lern.confidence > (kategorie_conf or 0.0)):
            kategorie, kategorie_conf, konto = lern.kategorie, lern.confidence, lern.konto
            begruendung = lern.begruendung
            gelernt = True
        if lern is not None and lern.ust_satz is not None and ist_unklar(ust_conf):
            ust_satz, ust_conf = lern.ust_satz, min(lern.confidence, 0.9)

    return EffektiveVorschlaege(kategorie, kategorie_conf, konto, ust_satz, ust_conf, begruendung, gelernt)
