from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class EuerResponse(BaseModel):
    jahr: int
    zeitraum_von: date
    zeitraum_bis: date
    betriebseinnahmen_netto: Decimal
    anzahl_einnahmen: int
    betriebsausgaben_netto: Decimal
    anzahl_ausgaben: int
    ueberschuss_netto: Decimal
    offene_forderungen_brutto: Decimal
    hinweis: str


class WochenprognoseResponse(BaseModel):
    woche_start: date
    woche_ende: date
    erwarteter_zufluss: Decimal
    anzahl_faellige_rechnungen: int
    geschaetzter_abfluss: Decimal
    saldo_veraenderung: Decimal
    kumulierter_saldo: Decimal


class CashflowResponse(BaseModel):
    heute: date
    wochen: list[WochenprognoseResponse]
    ueberfaellige_rechnungen_betrag: Decimal
    ueberfaellige_rechnungen_anzahl: int
    durchschnittliche_wochenausgabe: Decimal
    warnung: str | None
    hinweis: str


class SusaKontoResponse(BaseModel):
    konto: str
    bezeichnung: str
    soll: Decimal
    haben: Decimal
    saldo: Decimal


class SusaResponse(BaseModel):
    jahr: int
    konten: list[SusaKontoResponse]
    summe_soll: Decimal
    summe_haben: Decimal
    hinweis: str


class BwaPostenResponse(BaseModel):
    konto: str
    bezeichnung: str
    betrag: Decimal


class BwaResponse(BaseModel):
    jahr: int
    erloes_posten: list[BwaPostenResponse]
    kosten_posten: list[BwaPostenResponse]
    erloese_gesamt: Decimal
    kosten_gesamt: Decimal
    vorlaeufiges_ergebnis: Decimal
    hinweis: str


class UstvaResponse(BaseModel):
    jahr: int
    zeitraum_typ: str
    periode: int
    zeitraum_von: date
    zeitraum_bis: date
    umsatz_19_netto: Decimal
    umsatzsteuer_19: Decimal
    umsatz_7_netto: Decimal
    umsatzsteuer_7: Decimal
    umsatz_sonstige_netto: Decimal
    umsatzsteuer_gesamt: Decimal
    vorsteuer_gesamt: Decimal
    zahllast: Decimal
    anzahl_rechnungen: int
    anzahl_ausgaben: int
    hinweis: str


class MonatswertResponse(BaseModel):
    monat: int
    einnahmen: Decimal
    ausgaben: Decimal


class OffenePostenResponse(BaseModel):
    anzahl: int
    betrag: Decimal


class NamedBetragResponse(BaseModel):
    name: str
    betrag: Decimal


class VerlaufEintragResponse(BaseModel):
    aktion: str
    kontext: str
    zeitpunkt: datetime


class DashboardResponse(BaseModel):
    jahr: int
    gewinn_vor_steuern: Decimal
    einnahmen: Decimal
    ausgaben: Decimal
    monatswerte: list[MonatswertResponse]
    faellige_rechnungen: OffenePostenResponse
    offene_rechnungen: OffenePostenResponse
    kleinunternehmergrenze: Decimal
    umsatz_brutto_jahr: Decimal
    kassenbestand: Decimal
    top_kunden: list[NamedBetragResponse]
    top_ausgaben_kategorien: list[NamedBetragResponse]
    verlauf: list[VerlaufEintragResponse]
    hinweis: str
