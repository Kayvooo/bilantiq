"""DATEV EXTF "Buchungsstapel" export (Kategorie 21).

Honest limitation, same shape as the XRechnung caveat in app/invoices/e_invoice.py:
this follows the commonly documented EXTF Buchungsstapel layout (a technical header
line, a column-name line, then one row per booking) and the standard SKR03 automatic
Steuerschluessel (BU-Schluessel 3/2 for 19%/7% Umsatzsteuer on revenue, 9/8 for the
matching Vorsteuer on expenses). It has NOT been test-imported into a real DATEV
Kanzlei-Rechnungswesen. DATEV's own spec has accumulated many more optional header and
data columns over the years than are reproduced here (postal codes, cost centres,
locking flags, ...) — treat this as a good first cut, and test-import it with the
Steuerberater's DATEV before relying on it for a real Abgabe.

Cash-basis simplification: payment bookings clear against a single "Bank" account
(SKR03 1200) rather than tracking per-customer Debitoren/Kreditoren accounts — matches
how app/reports/euer.py treats income/expense (Zufluss-/Abflussprinzip). Annual AfA is
the explicit non-cash exception and books expense against the asset account.
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.altrechnungen.auswertung import ZahlungsAnteil, zahlungsanteile
from app.anlagen.models import Anlage
from app.auth.models import Mandant
from app.core.kontenrahmen import erloes_konto
from app.einnahmen.models import SonstigeEinnahme
from app.invoices.models import Invoice, Kontakt
from app.receipts.accounting import steueraufteilung
from app.receipts.models import Ausgabe
from app.reports.afa import sammle_afa_jahreswerte

BANK_KONTO = "1200"  # SKR03 "Bank" — assumption, see module docstring
SONSTIGE_ERTRAEGE_KONTO = "2700"  # Annahme, nicht mit einem Steuerberater abgeglichen
AFA_AUFWAND_KONTO = "4830"  # Annahme, nicht mit einem Steuerberater abgeglichen
ANLAGEN_BESTANDSKONTO = "0490"  # Annahme, nicht mit einem Steuerberater abgeglichen

BU_SCHLUESSEL_ERLOES = {Decimal("19.00"): "3", Decimal("7.00"): "2", Decimal("0.00"): ""}
BU_SCHLUESSEL_VORSTEUER = {Decimal("19.00"): "9", Decimal("7.00"): "8", Decimal("0.00"): ""}

COLUMN_HEADER = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs", "Basis-Umsatz",
    "WKZ Basis-Umsatz", "Konto", "Gegenkonto (ohne BU-Schluessel)", "BU-Schluessel", "Belegdatum",
    "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext",
]


@dataclass
class Buchungszeile:
    umsatz: Decimal
    soll_haben: str  # "S" oder "H"
    konto: str
    gegenkonto: str
    bu_schluessel: str
    belegdatum: date
    belegfeld1: str
    buchungstext: str

    def as_row(self) -> list:
        # Belegdatum stays a zero-padded "TTMM" string on purpose: int() would strip a
        # leading zero (day/month 1-9) and silently corrupt the date — e.g. "0509"
        # (5 Sept) becoming 509, which is not a valid TTMM value at all.
        return [
            _de_decimal(self.umsatz), self.soll_haben, "EUR", "", "", "",
            self.konto, self.gegenkonto, self.bu_schluessel, self.belegdatum.strftime("%d%m"),
            self.belegfeld1[:36], "", "", self.buchungstext[:60],
        ]


def _de_decimal(value: Decimal) -> str:
    return f"{abs(value):.2f}".replace(".", ",")


def _tax_breakdown(invoice: Invoice) -> list[tuple[Decimal, Decimal]]:
    by_rate: dict[Decimal, Decimal] = {}
    for position in invoice.positionen:
        brutto = (position.menge * position.einzelpreis * (Decimal("1") + position.ust_satz / Decimal("100"))).quantize(Decimal("0.01"))
        by_rate[position.ust_satz] = by_rate.get(position.ust_satz, Decimal("0")) + brutto
    return sorted(by_rate.items())


def _invoice_buchungen(invoice: Invoice) -> list[Buchungszeile]:
    zeilen = []
    for satz, brutto_teilbetrag in _tax_breakdown(invoice):
        zeilen.append(Buchungszeile(
            umsatz=brutto_teilbetrag, soll_haben="S", konto=BANK_KONTO, gegenkonto=erloes_konto(satz),
            bu_schluessel=BU_SCHLUESSEL_ERLOES.get(satz, ""), belegdatum=invoice.bezahlt_am,
            belegfeld1=invoice.nummer or invoice.id[:8],
            buchungstext=f"Rechnung {invoice.nummer} {invoice.kontakt.name}",
        ))
    return zeilen


def _altrechnung_buchung(anteil: ZahlungsAnteil, kontakt_name: str) -> Buchungszeile:
    """Zahlung auf eine Rechnung aus dem Altsystem: Erloes mit der alten Nummer im Belegfeld, je Steuersatz eine Zeile."""
    return Buchungszeile(
        umsatz=anteil.brutto, soll_haben="S", konto=BANK_KONTO, gegenkonto=erloes_konto(anteil.satz),
        bu_schluessel=BU_SCHLUESSEL_ERLOES.get(anteil.satz, ""), belegdatum=anteil.datum, belegfeld1=anteil.nummer,
        buchungstext=f"Altrechnung {anteil.nummer} {kontakt_name}",
    )


def _ausgabe_buchungen(ausgabe: Ausgabe) -> list[Buchungszeile]:
    """Eine DATEV-Zeile je USt-Anteil; dadurch bleiben gemischte Belege steuerlich getrennt."""
    return [
        Buchungszeile(
            umsatz=brutto,
            soll_haben="S",
            konto=ausgabe.konto,
            gegenkonto=BANK_KONTO,
            bu_schluessel=BU_SCHLUESSEL_VORSTEUER.get(satz, ""),
            # Der aktuelle Export ist eine zahlungsbasierte Vereinfachung; deshalb
            # dient das Zahlungsdatum auch als Buchungsdatum im Stapel.
            belegdatum=ausgabe.zahlungsdatum,
            belegfeld1=ausgabe.id[:8],
            buchungstext=f"{ausgabe.anbieter} ({ausgabe.kategorie})",
        )
        for satz, brutto in steueraufteilung(ausgabe)
    ]


def _sonstige_einnahme_buchung(einnahme: SonstigeEinnahme) -> Buchungszeile:
    return Buchungszeile(
        umsatz=einnahme.betrag_brutto,
        soll_haben="S",
        konto=BANK_KONTO,
        gegenkonto=SONSTIGE_ERTRAEGE_KONTO,
        bu_schluessel=BU_SCHLUESSEL_ERLOES.get(einnahme.ust_satz, ""),
        belegdatum=einnahme.datum,
        belegfeld1=einnahme.id[:8],
        buchungstext=einnahme.bezeichnung,
    )


def _afa_buchung(anlage: Anlage, *, betrag: Decimal, jahr: int) -> Buchungszeile:
    return Buchungszeile(
        umsatz=betrag,
        soll_haben="S",
        konto=AFA_AUFWAND_KONTO,
        gegenkonto=ANLAGEN_BESTANDSKONTO,
        bu_schluessel="",
        belegdatum=date(jahr, 12, 31),
        belegfeld1=anlage.id[:8],
        buchungstext=f"AfA {anlage.bezeichnung}",
    )


def sammle_buchungszeilen(db: Session, *, mandant_id: str, jahr: int) -> list[Buchungszeile]:
    """Alle Buchungszeilen eines Jahres — von build_datev_export UND compute_susa
    genutzt, damit Export und Summen-/Saldenliste garantiert dieselben Zahlen zeigen."""
    von = date(jahr, 1, 1)
    bis = date(jahr, 12, 31)

    bezahlte_rechnungen = (
        db.query(Invoice)
        .filter(
            Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.isnot(None),
            Invoice.bezahlt_am >= von, Invoice.bezahlt_am <= bis,
        )
        .all()
    )
    ausgaben = db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id, Ausgabe.zahlungsdatum >= von, Ausgabe.zahlungsdatum <= bis).all()
    sonstige_einnahmen = (
        db.query(SonstigeEinnahme)
        .filter(
            SonstigeEinnahme.mandant_id == mandant_id,
            SonstigeEinnahme.datum >= von,
            SonstigeEinnahme.datum <= bis,
        )
        .all()
    )
    afa_jahreswerte = sammle_afa_jahreswerte(db, mandant_id=mandant_id, jahr=jahr)

    zeilen: list[Buchungszeile] = []
    for rechnung in bezahlte_rechnungen:
        zeilen.extend(_invoice_buchungen(rechnung))
    alt_anteile = zahlungsanteile(db, mandant_id=mandant_id, von=von, bis=bis)
    if alt_anteile:
        namen = dict(db.query(Kontakt.id, Kontakt.name).filter(Kontakt.mandant_id == mandant_id))
        zeilen.extend(_altrechnung_buchung(a, namen.get(a.kontakt_id, "")) for a in alt_anteile)
    for ausgabe in ausgaben:
        zeilen.extend(_ausgabe_buchungen(ausgabe))
    for einnahme in sonstige_einnahmen:
        zeilen.append(_sonstige_einnahme_buchung(einnahme))
    for anlage, betrag in afa_jahreswerte:
        zeilen.append(_afa_buchung(anlage, betrag=betrag, jahr=jahr))
    return zeilen


def build_datev_export(db: Session, *, mandant: Mandant, jahr: int) -> bytes:
    von = date(jahr, 1, 1)
    bis = date(jahr, 12, 31)
    zeilen = sammle_buchungszeilen(db, mandant_id=mandant.id, jahr=jahr)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_NONNUMERIC, lineterminator="\r\n")

    erzeugt_am = int(datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S000"))
    beraternummer = _as_int_or_str(mandant.datev_beraternummer or "1001")
    mandantennummer = _as_int_or_str(mandant.datev_mandantennummer or "1")
    writer.writerow([
        "EXTF", 700, 21, "Buchungsstapel", 7, erzeugt_am, "", "", "", "",
        beraternummer, mandantennummer, int(f"{jahr}0101"), 4, int(von.strftime("%Y%m%d")), int(bis.strftime("%Y%m%d")),
        f"Bilantiq {jahr}", "", 1, "", 0, "EUR",
    ])
    writer.writerow(COLUMN_HEADER)
    for zeile in zeilen:
        writer.writerow(zeile.as_row())

    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _as_int_or_str(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value
