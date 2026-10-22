"""Kontakte und Produkte als CSV oder Excel exportieren, dazu leere Importvorlagen.

Die Spalten heissen wie die Importfelder, eine exportierte Datei laesst sich also ohne
Zuordnungsarbeit wieder importieren. Zellen, die eine Tabellenkalkulation als Formel lesen
wuerde, werden entschaerft (Formel-Injection)."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.invoices.models import Kontakt
from app.produkte.models import Produkt
from app.stammdaten.felder import FELDER, Feld

Format = Literal["csv", "xlsx"]
_FORMEL_ANFANG = ("=", "+", "-", "@", "\t", "\r")
_TYP_LABEL = {"kunde": "Kunde", "lieferant": "Lieferant", "beide": "Kunde und Lieferant"}
MEDIA_TYPEN = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def export_felder(ziel: str) -> list[Feld]:
    return [feld for feld in FELDER[ziel] if not feld.nur_import]


def _zahl_de(zahl: Decimal) -> str:
    return format(zahl.normalize(), "f").replace(".", ",") if zahl == zahl.to_integral_value() else f"{zahl:.2f}".replace(".", ",")


def _als_text(feld: Feld, wert: Any) -> str:
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, date):
        return wert.strftime("%d.%m.%Y")
    if feld.typ == "kontakt_typ":
        return _TYP_LABEL.get(wert, str(wert))
    if isinstance(wert, Decimal):
        # Geldbetraege immer mit Cent ("0,00", "1190,00"), andere Zahlen ohne ueberfluessige Nullen.
        return f"{wert:.2f}".replace(".", ",") if feld.typ == "geld" else _zahl_de(wert)
    return str(wert)


def entschaerfe(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMEL_ANFANG) else text


def _zeilen(db: Session, ziel: str, mandant_id: str) -> tuple[list[str], list[list[Any]]]:
    felder = export_felder(ziel)
    kopf = [feld.label for feld in felder]
    if ziel == "kontakte":
        objekte = db.query(Kontakt).filter(Kontakt.mandant_id == mandant_id).all()
        objekte.sort(key=lambda k: k.name.casefold())
        kopf.append("Archiviert")
        zeilen = [[getattr(k, feld.schluessel) for feld in felder] + [k.archiviert_am is not None] for k in objekte]
    else:
        objekte = db.query(Produkt).filter(Produkt.mandant_id == mandant_id).all()
        objekte.sort(key=lambda p: p.bezeichnung.casefold())
        zeilen = [[getattr(p, feld.schluessel) for feld in felder] for p in objekte]
    return kopf, zeilen


def _csv(kopf: list[str], zeilen: list[list[Any]], felder: list[Feld | None]) -> bytes:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow(kopf)
    for zeile in zeilen:
        schreiber.writerow([
            entschaerfe(_als_text(feld, wert)) if feld else ("ja" if wert else "nein")
            for feld, wert in zip(felder, zeile)
        ])
    # BOM, damit Excel die Datei als UTF-8 erkennt (Umlaute).
    return ("﻿" + puffer.getvalue()).encode("utf-8")


def _xlsx(kopf: list[str], zeilen: list[list[Any]], felder: list[Feld | None], blattname: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    mappe = Workbook(write_only=True)
    blatt = mappe.create_sheet(blattname)
    fett = Font(bold=True)
    kopfzellen = []
    for titel in kopf:
        zelle = WriteOnlyCell(blatt, value=titel)
        zelle.font = fett
        kopfzellen.append(zelle)
    blatt.append(kopfzellen)
    for zeile in zeilen:
        zellen = []
        for feld, wert in zip(felder, zeile):
            if feld is None:
                zelle = WriteOnlyCell(blatt, value="ja" if wert else "nein")
            elif isinstance(wert, (Decimal, int)) and not isinstance(wert, bool) and feld.typ != "kontakt_typ":
                zelle = WriteOnlyCell(blatt, value=wert)
            else:
                zelle = WriteOnlyCell(blatt, value=_als_text(feld, wert))
                # openpyxl haelt Texte mit "=" am Anfang fuer Formeln. Ausdruecklich als Text schreiben.
                zelle.data_type = "s"
            zellen.append(zelle)
        blatt.append(zellen)
    puffer = io.BytesIO()
    mappe.save(puffer)
    return puffer.getvalue()


def exportiere(db: Session, *, mandant_id: str, ziel: str, format_: Format) -> tuple[bytes, str]:
    kopf, zeilen = _zeilen(db, ziel, mandant_id)
    felder: list[Feld | None] = [*export_felder(ziel)] + ([None] if ziel == "kontakte" else [])
    inhalt = _csv(kopf, zeilen, felder) if format_ == "csv" else _xlsx(kopf, zeilen, felder, ziel.capitalize())
    return inhalt, f"bilantiq-{ziel}-{date.today().isoformat()}.{format_}"


def vorlage(*, ziel: str, format_: Format) -> tuple[bytes, str]:
    felder = export_felder(ziel)
    kopf = [feld.label for feld in felder]
    beispiel: list[Any] = [feld.beispiel or None for feld in felder]
    inhalt = _csv(kopf, [beispiel], list(felder)) if format_ == "csv" else _xlsx(kopf, [beispiel], list(felder), ziel.capitalize())
    return inhalt, f"bilantiq-vorlage-{ziel}.{format_}"
