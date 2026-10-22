"""Nummernkreis der Bilantiq-Rechnungen fortsetzen (Umzug aus einem anderen Programm).

Rechnungsnummern sind `RE-JJJJ-NNNN`, je Jahr, ohne Luecken. Wer mitten im Jahr wechselt, hat im alten
Programm schon Nummern desselben Formats vergeben. Bekaeme er in Bilantiq noch einmal `RE-2026-0001`,
waere das eine doppelte Nummer (§ 14 UStG verlangt eindeutige). Deshalb laesst sich die naechste Nummer
anheben, nur nach oben und nur ueber der hoechsten schon vergebenen Nummer, auch der aus dem Altsystem."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.altrechnungen.models import Altrechnung
from app.altrechnungen.nummer import laufnummer_im_jahr
from app.core.audit_log import record as record_audit
from app.db import IS_POSTGRES
from app.invoices.models import Invoice, Rechnungsnummernkreis

PRAEFIX = "RE"
MAX_NUMMER = 999_999


class NummernkreisFehler(ValueError):
    """Meldung fuer den Nutzer."""


@dataclass
class Stand:
    jahr: int
    naechste_nummer: int
    hoechste_bilantiq: int
    hoechste_altsystem: int | None

    @property
    def naechste_rechnungsnummer(self) -> str:
        return formatiere(self.jahr, self.naechste_nummer)

    @property
    def mindestens(self) -> int:
        """Kleinster Wert, auf den sich die naechste Nummer setzen laesst."""
        return max(self.naechste_nummer, self.hoechste_bilantiq + 1, (self.hoechste_altsystem or 0) + 1)

    @property
    def kollision(self) -> bool:
        """Die naechste Bilantiq-Nummer waere schon im Altsystem vergeben."""
        return self.hoechste_altsystem is not None and self.naechste_nummer <= self.hoechste_altsystem


def aktuelles_jahr() -> int:
    return datetime.now(timezone.utc).year  # wie bei der Vergabe in app/invoices/routes.py


def formatiere(jahr: int, nummer: int) -> str:
    return f"{PRAEFIX}-{jahr}-{nummer:04d}"


def _zaehler(db: Session, mandant_id: str, jahr: int, *, sperren: bool = False) -> Rechnungsnummernkreis | None:
    anfrage = select(Rechnungsnummernkreis).where(Rechnungsnummernkreis.mandant_id == mandant_id, Rechnungsnummernkreis.jahr == jahr)
    if sperren and IS_POSTGRES:
        anfrage = anfrage.with_for_update()
    return db.scalars(anfrage).first()


def lese_stand(db: Session, mandant_id: str, jahr: int | None = None) -> Stand:
    jahr = jahr or aktuelles_jahr()
    zaehler = _zaehler(db, mandant_id, jahr)
    naechste = zaehler.naechste_nummer if zaehler else 1
    # Der Zaehler ist die Wahrheit, die vergebenen Nummern sind die Gegenprobe.
    hoechste_bilantiq = naechste - 1
    for nummer in db.scalars(select(Invoice.nummer).where(Invoice.mandant_id == mandant_id, Invoice.nummer.like(f"{PRAEFIX}-{jahr}-%"))):
        laufnummer = laufnummer_im_jahr(nummer, jahr, PRAEFIX)
        if laufnummer is not None:
            hoechste_bilantiq = max(hoechste_bilantiq, laufnummer)
    hoechste_alt = None
    for nummer in db.scalars(select(Altrechnung.nummer).where(Altrechnung.mandant_id == mandant_id)):
        laufnummer = laufnummer_im_jahr(nummer, jahr, PRAEFIX)
        if laufnummer is not None:
            hoechste_alt = max(hoechste_alt or 0, laufnummer)
    return Stand(jahr=jahr, naechste_nummer=naechste, hoechste_bilantiq=hoechste_bilantiq, hoechste_altsystem=hoechste_alt)


def setze_naechste_nummer(db: Session, *, mandant_id: str, user_id: str | None, wert: int) -> Stand:
    jahr = aktuelles_jahr()
    zaehler = _zaehler(db, mandant_id, jahr, sperren=True)
    stand = lese_stand(db, mandant_id, jahr)
    if not 1 <= wert <= MAX_NUMMER:
        raise NummernkreisFehler(f"Die Nummer muss zwischen 1 und {MAX_NUMMER} liegen.")
    if wert < stand.naechste_nummer:
        raise NummernkreisFehler(
            f"Der Nummernkreis lässt sich nur erhöhen, nicht senken. Die nächste Nummer ist {formatiere(jahr, stand.naechste_nummer)}."
        )
    if wert <= stand.hoechste_bilantiq:
        raise NummernkreisFehler(f"Die Nummer {formatiere(jahr, stand.hoechste_bilantiq)} ist in Bilantiq schon vergeben.")
    if stand.hoechste_altsystem is not None and wert <= stand.hoechste_altsystem:
        raise NummernkreisFehler(
            f"Im alten Programm gibt es schon Rechnungen bis {formatiere(jahr, stand.hoechste_altsystem)}. "
            f"Die nächste Nummer muss mindestens {formatiere(jahr, stand.hoechste_altsystem + 1)} sein."
        )
    alt = stand.naechste_nummer
    if zaehler is None:
        zaehler = Rechnungsnummernkreis(mandant_id=mandant_id, jahr=jahr, naechste_nummer=wert)
        db.add(zaehler)
    else:
        zaehler.naechste_nummer = wert
    record_audit(db, aktion="nummernkreis_gesetzt", mandant_id=mandant_id, user_id=user_id, kontext=f"{jahr} {alt} -> {wert}")
    db.flush()
    return lese_stand(db, mandant_id, jahr)
