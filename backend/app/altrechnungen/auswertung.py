"""Altrechnungen in den Auswertungen (Einnahmen-Ueberschuss-Rechnung, Umsatzsteuer, Dashboard,
Cashflow, DATEV).

Regeln (siehe docs/specs/rechnungshistorie.md):
- Was im Altsystem bezahlt wurde, zaehlt nie: das steht dort in den Buechern.
- Zahlungen, die in Bilantiq erfasst werden, zaehlen im Zeitraum ihres Zahlungsdatums
  (Zufluss-/Abflussprinzip, Ist-Versteuerung), und die Umsatzsteuer anteilig nach dem gezahlten
  Betrag je Steuersatz.
- Offene Altrechnungen zaehlen als offene Forderung, bis sie bezahlt sind."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, defer, joinedload, selectinload

from app.altrechnungen import service
from app.altrechnungen.models import Altrechnung, AltrechnungZahlung
from app.altrechnungen.steuer import anteile_aus_json, verteile_zahlung


@dataclass(frozen=True)
class ZahlungsAnteil:
    """Ein Steuersatz-Anteil einer Zahlung."""
    zahlung_id: str
    altrechnung_id: str
    datum: date
    nummer: str
    kontakt_id: str
    satz: Decimal
    netto: Decimal
    ust: Decimal

    @property
    def brutto(self) -> Decimal:
        return self.netto + self.ust


@dataclass(frozen=True)
class OffenerPosten:
    altrechnung_id: str
    kontakt_id: str
    faelligkeit: date | None
    betrag: Decimal


def zahlungsanteile(db: Session, *, mandant_id: str, von: date | None = None, bis: date | None = None) -> list[ZahlungsAnteil]:
    anfrage = (
        db.query(AltrechnungZahlung)
        .options(joinedload(AltrechnungZahlung.altrechnung))
        .filter(AltrechnungZahlung.mandant_id == mandant_id)
    )
    if von is not None:
        anfrage = anfrage.filter(AltrechnungZahlung.datum >= von)
    if bis is not None:
        anfrage = anfrage.filter(AltrechnungZahlung.datum <= bis)
    ergebnis: list[ZahlungsAnteil] = []
    for zahlung in anfrage.order_by(AltrechnungZahlung.datum, AltrechnungZahlung.erstellt_am):
        altrechnung = zahlung.altrechnung
        for anteil in verteile_zahlung(anteile_aus_json(altrechnung.steueranteile), zahlung.betrag):
            ergebnis.append(ZahlungsAnteil(
                zahlung_id=zahlung.id, altrechnung_id=altrechnung.id, datum=zahlung.datum, nummer=altrechnung.nummer,
                kontakt_id=altrechnung.kontakt_id, satz=anteil.satz, netto=anteil.netto, ust=anteil.ust,
            ))
    return ergebnis


def offene_posten(db: Session, *, mandant_id: str) -> list[OffenerPosten]:
    """Altrechnungen mit Restbetrag. Geladen werden nur die, die beim Umzug offen waren."""
    zeilen = (
        db.query(Altrechnung)
        .options(selectinload(Altrechnung.zahlungen), defer(Altrechnung.steueranteile), defer(Altrechnung.nummer))
        .filter(Altrechnung.mandant_id == mandant_id, Altrechnung.war_offen.is_(True))
        .all()
    )
    posten = []
    for zeile in zeilen:
        rest = service.restbetrag(zeile)
        if rest > 0:
            posten.append(OffenerPosten(zeile.id, zeile.kontakt_id, zeile.faelligkeit, rest))
    return posten


def zahlungen_je_kontakt(db: Session, *, mandant_id: str) -> dict[str, Decimal]:
    """Alle in Bilantiq erfassten Zahlungen auf Altrechnungen, je Kontakt summiert (brutto)."""
    summen: dict[str, Decimal] = {}
    zeilen = (
        db.query(Altrechnung.kontakt_id, AltrechnungZahlung.betrag)
        .join(AltrechnungZahlung, AltrechnungZahlung.altrechnung_id == Altrechnung.id)
        .filter(AltrechnungZahlung.mandant_id == mandant_id)
    )
    for kontakt_id, betrag in zeilen:
        summen[kontakt_id] = summen.get(kontakt_id, Decimal("0")) + betrag
    return summen
