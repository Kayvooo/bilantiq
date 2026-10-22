"""Fachlogik fuer Kontoauszug-Import und Zuordnung."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, defer, selectinload

from app.altrechnungen import service as alt_service
from app.altrechnungen.models import Altrechnung
from app.bank import matching
from app.bank.models import Bankimport, Bankkonto, Bankumsatz
from app.bank.parser_camt import lese_camt
from app.bank.parser_csv import CsvProfil, lese_csv
from app.bank.rohdaten import ImportFehler, RohAuszug, RohUmsatz
from app.config import settings
from app.core.audit_log import record as record_audit
from app.core.key_management import blind_index
from app.core.secure_storage import write_encrypted
from app.invoices import zahlungen
from app.invoices.kontakte import kontakt_iban_hash
from app.invoices.models import Invoice, Kontakt
from app.receipts import storage
from app.receipts.models import Ausgabe, Receipt

ABFRAGE_BLOCK = 500


class ZuordnungsFehler(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def iban_hash(mandant_id: str, iban: str) -> str:
    return blind_index(iban.replace(" ", ""), purpose=f"bank-iban:{mandant_id}")


def _umsatz_hashes(konto_id: str, umsaetze: list[RohUmsatz]) -> list[str]:
    """Gleiche Zeilen innerhalb einer Datei (zwei identische Zahlungen am selben Tag) bekommen
    eine laufende Nummer. So bleiben sie getrennt, und ein erneuter Import desselben Zeitraums
    erkennt sie trotzdem wieder."""
    vorkommen: dict[str, int] = {}
    hashes = []
    for u in umsaetze:
        basis = "|".join([
            u.buchungsdatum.isoformat(), f"{u.betrag:.2f}", (u.gegenpartei_iban or "").replace(" ", ""),
            u.gegenpartei_name or "", u.verwendungszweck, u.end_to_end_id or "",
        ])
        nummer = vorkommen.get(basis, 0) + 1
        vorkommen[basis] = nummer
        hashes.append(blind_index(f"{basis}|{nummer}", purpose=f"bank-umsatz:{konto_id}"))
    return hashes


def lese_auszug(daten: bytes, format_: str, profil: CsvProfil | None) -> RohAuszug:
    if format_ == "camt":
        return lese_camt(daten)
    if profil is None:
        raise ImportFehler("Für CSV-Dateien wird ein Spaltenprofil benötigt.")
    return lese_csv(daten, profil)


def importiere(
    db: Session,
    *,
    mandant_id: str,
    konto: Bankkonto,
    daten: bytes,
    dateiname: str,
    format_: str,
    profil: CsvProfil | None,
    user_id: str | None,
) -> Bankimport:
    auszug = lese_auszug(daten, format_, profil)

    if auszug.konto_iban:
        datei_hash = iban_hash(mandant_id, auszug.konto_iban)
        if konto.iban_hash and konto.iban_hash != datei_hash:
            raise ImportFehler("Die Datei gehört zu einem anderen Konto (die IBAN stimmt nicht überein).")
        if not konto.iban_hash:
            konto.iban, konto.iban_hash = auszug.konto_iban, datei_hash

    hashes = _umsatz_hashes(konto.id, auszug.umsaetze)
    bekannt: set[str] = set()
    for start in range(0, len(hashes), ABFRAGE_BLOCK):
        block = hashes[start:start + ABFRAGE_BLOCK]
        bekannt.update(db.scalars(select(Bankumsatz.dedupe_hash).where(
            Bankumsatz.bankkonto_id == konto.id, Bankumsatz.dedupe_hash.in_(block))))

    datei_hash_inhalt = storage.hash_bytes(daten)
    endung = "xml" if format_ == "camt" else "csv"
    relativ = f"{mandant_id}/{datei_hash_inhalt}.{endung}"
    write_encrypted(settings.bank_storage_dir, relativ, daten, purpose_prefix="bank-file")

    daten_import = Bankimport(
        mandant_id=mandant_id, bankkonto_id=konto.id, format=format_, dateiname=dateiname[:200],
        datei_hash=datei_hash_inhalt, datei_referenz=relativ, anzahl_neu=0, anzahl_doppelt=0,
        zeitraum_von=min(u.buchungsdatum for u in auszug.umsaetze),
        zeitraum_bis=max(u.buchungsdatum for u in auszug.umsaetze),
    )
    db.add(daten_import)
    db.flush()

    neu = doppelt = 0
    for roh, hash_ in zip(auszug.umsaetze, hashes):
        if hash_ in bekannt:
            doppelt += 1
            continue
        db.add(Bankumsatz(
            mandant_id=mandant_id, bankkonto_id=konto.id, import_id=daten_import.id,
            buchungsdatum=roh.buchungsdatum, wertstellung=roh.wertstellung, betrag=roh.betrag, waehrung=roh.waehrung,
            gegenpartei_name=roh.gegenpartei_name, gegenpartei_iban=roh.gegenpartei_iban,
            verwendungszweck=roh.verwendungszweck, end_to_end_id=roh.end_to_end_id, dedupe_hash=hash_,
        ))
        neu += 1
    daten_import.anzahl_neu, daten_import.anzahl_doppelt = neu, doppelt
    if format_ == "csv" and profil is not None:
        konto.csv_profil = profil.model_dump_json()
    record_audit(
        db, aktion="bank_import", mandant_id=mandant_id, user_id=user_id,
        kontext=f"{daten_import.id} {format_} neu {neu} doppelt {doppelt}",
    )
    return daten_import


# ---------------------------------------------------------------------------
# Vorschlaege


def _als_umsatz(zeile: Bankumsatz, iban_kontakte: dict[str, list[Kontakt]] | None = None) -> matching.Umsatz:
    bekannte = (iban_kontakte or {}).get(_iban_kompakt(zeile.gegenpartei_iban), [])
    return matching.Umsatz(
        id=zeile.id, buchungsdatum=zeile.buchungsdatum, betrag=zeile.betrag,
        gegenpartei=zeile.gegenpartei_name, verwendungszweck=zeile.verwendungszweck or "",
        iban_kontakt_ids=frozenset(k.id for k in bekannte),
        iban_lieferanten=tuple(k.name for k in bekannte if k.typ in ("lieferant", "beide")),
    )


def _iban_kompakt(iban: str | None) -> str:
    return (iban or "").replace(" ", "").upper()


def _kontakte_nach_iban(db: Session, mandant_id: str, umsaetze: list[Bankumsatz]) -> dict[str, list[Kontakt]]:
    """Kontakte mit hinterlegter IBAN, gesucht ueber den Blind-Index statt alle zu entschluesseln."""
    ibans = {_iban_kompakt(u.gegenpartei_iban) for u in umsaetze if u.gegenpartei_iban}
    if not ibans:
        return {}
    nach_hash = {kontakt_iban_hash(mandant_id, iban): iban for iban in ibans}
    ergebnis: dict[str, list[Kontakt]] = {}
    for kontakt in db.query(Kontakt).filter(Kontakt.mandant_id == mandant_id, Kontakt.iban_hash.in_(nach_hash)):
        ergebnis.setdefault(nach_hash[kontakt.iban_hash], []).append(kontakt)
    return ergebnis


def verknuepfte_ziele(db: Session, mandant_id: str, typ: str) -> set[str]:
    return set(db.scalars(select(Bankumsatz.zuordnung_id).where(
        Bankumsatz.mandant_id == mandant_id, Bankumsatz.status == "zugeordnet", Bankumsatz.zuordnung_typ == typ)))


def berechne_vorschlaege(db: Session, mandant_id: str, offene: list[Bankumsatz]) -> dict[str, matching.Vorschlag]:
    eingaenge = [u for u in offene if u.betrag > 0]
    ausgaenge = [u for u in offene if u.betrag < 0]
    ergebnis: dict[str, matching.Vorschlag] = {}
    iban_kontakte = _kontakte_nach_iban(db, mandant_id, offene)

    if eingaenge:
        rechnungen = [
            matching.RechnungKandidat(
                id=r.id, nummer=r.nummer, brutto=r.brutto_gesamt, kunde=r.kontakt.name, faelligkeit=r.faelligkeitsdatum,
                kontakt_id=r.kontakt_id,
            )
            for r in db.query(Invoice).options(selectinload(Invoice.kontakt)).filter(
                Invoice.mandant_id == mandant_id, Invoice.status == "final", Invoice.bezahlt_am.is_(None),
                Invoice.nummer.is_not(None))
        ]
        # Offene Rechnungen aus dem Altsystem: Betrag ist der Restbetrag, ein Teilbetrag darf zahlen.
        for alt in db.query(Altrechnung).options(
            selectinload(Altrechnung.zahlungen), selectinload(Altrechnung.kontakt), defer(Altrechnung.steueranteile),
        ).filter(Altrechnung.mandant_id == mandant_id, Altrechnung.war_offen.is_(True)):
            rest = alt_service.restbetrag(alt)
            if rest > 0:
                rechnungen.append(matching.RechnungKandidat(
                    id=alt.id, nummer=alt.nummer, brutto=rest, kunde=alt.kontakt.name,
                    faelligkeit=alt.faelligkeit or alt.rechnungsdatum, kontakt_id=alt.kontakt_id, typ="altrechnung",
                ))
        for umsatz in eingaenge:
            if vorschlag := matching.vorschlag_fuer_eingang(_als_umsatz(umsatz, iban_kontakte), rechnungen):
                ergebnis[umsatz.id] = vorschlag

    if ausgaenge:
        belege_verknuepft = verknuepfte_ziele(db, mandant_id, "beleg")
        ausgaben_verknuepft = verknuepfte_ziele(db, mandant_id, "ausgabe")
        kandidaten = [
            matching.BelegKandidat(id=b.id, typ="beleg", betrag=b.betrag, anbieter=b.anbieter, datum=b.datum, zahlungsdatum=None)
            for b in db.query(Receipt).filter(Receipt.mandant_id == mandant_id, Receipt.status != "gebucht")
            if b.id not in belege_verknuepft
        ] + [
            matching.BelegKandidat(
                id=a.id, typ="ausgabe", betrag=a.betrag, anbieter=a.anbieter, datum=a.datum, zahlungsdatum=a.zahlungsdatum,
            )
            for a in db.query(Ausgabe).filter(Ausgabe.mandant_id == mandant_id).order_by(Ausgabe.erstellt_am.desc()).limit(1000)
            if a.id not in ausgaben_verknuepft
        ]
        for umsatz in ausgaenge:
            if vorschlag := matching.vorschlag_fuer_ausgang(_als_umsatz(umsatz, iban_kontakte), kandidaten):
                ergebnis[umsatz.id] = vorschlag
    return ergebnis


def anzeige_fuer_zuordnung(db: Session, mandant_id: str, typ: str | None, ziel_id: str | None) -> str | None:
    if typ is None or ziel_id is None:
        return None
    if typ == "rechnung":
        rechnung = db.get(Invoice, ziel_id)
        return f"{rechnung.nummer}" if rechnung and rechnung.mandant_id == mandant_id else None
    if typ == "altrechnung":
        alt = db.get(Altrechnung, ziel_id)
        return alt.nummer if alt and alt.mandant_id == mandant_id else None
    modell = Receipt if typ == "beleg" else Ausgabe
    ziel = db.get(modell, ziel_id)
    return ziel.anbieter if ziel is not None and ziel.mandant_id == mandant_id else None


# ---------------------------------------------------------------------------
# Zuordnen


def _lade_umsatz(db: Session, mandant_id: str, umsatz_id: str) -> Bankumsatz:
    umsatz = db.get(Bankumsatz, umsatz_id)
    if umsatz is None or umsatz.mandant_id != mandant_id:
        raise ZuordnungsFehler(404, "Umsatz nicht gefunden.")
    return umsatz


def ordne_zu(db: Session, *, mandant_id: str, umsatz_id: str, typ: str, ziel_id: str, user_id: str | None) -> Bankumsatz:
    umsatz = _lade_umsatz(db, mandant_id, umsatz_id)
    if umsatz.status != "offen":
        raise ZuordnungsFehler(400, "Dieser Umsatz ist schon zugeordnet oder ignoriert. Bitte zuerst aufheben.")

    if typ == "rechnung":
        if umsatz.betrag <= 0:
            raise ZuordnungsFehler(400, "Nur ein Zahlungseingang kann zu einer Rechnung gehören.")
        rechnung = db.get(Invoice, ziel_id)
        if rechnung is None or rechnung.mandant_id != mandant_id:
            raise ZuordnungsFehler(404, "Rechnung nicht gefunden.")
        if abs(umsatz.betrag - rechnung.brutto_gesamt) >= matching.BETRAGS_TOLERANZ:
            raise ZuordnungsFehler(
                400, "Der Betrag der Zahlung stimmt nicht mit der Rechnung überein. "
                     "Teilzahlungen werden noch nicht unterstützt.",
            )
        try:
            zahlungen.markiere_rechnung_bezahlt(db, rechnung, bezahlt_am=umsatz.buchungsdatum, user_id=user_id)
        except ValueError as exc:
            raise ZuordnungsFehler(400, str(exc)) from exc
    elif typ == "altrechnung":
        if umsatz.betrag <= 0:
            raise ZuordnungsFehler(400, "Nur ein Zahlungseingang kann zu einer Rechnung gehören.")
        alt = db.get(Altrechnung, ziel_id)
        if alt is None or alt.mandant_id != mandant_id:
            raise ZuordnungsFehler(404, "Rechnung nicht gefunden.")
        try:
            alt_service.erfasse_zahlung(
                db, alt, datum=umsatz.buchungsdatum, betrag=umsatz.betrag, quelle="bankabgleich", user_id=user_id,
            )
        except alt_service.ZahlungAbgelehnt as exc:
            raise ZuordnungsFehler(400, str(exc)) from exc
    else:
        if umsatz.betrag >= 0:
            raise ZuordnungsFehler(400, "Nur eine Zahlung (Ausgang) kann zu einem Beleg oder einer Ausgabe gehören.")
        modell = Receipt if typ == "beleg" else Ausgabe
        ziel = db.get(modell, ziel_id)
        if ziel is None or ziel.mandant_id != mandant_id:
            raise ZuordnungsFehler(404, "Beleg bzw. Ausgabe nicht gefunden.")
        if typ == "beleg" and ziel.status == "gebucht":
            raise ZuordnungsFehler(400, "Dieser Beleg ist schon gebucht. Bitte die Ausgabe zuordnen.")
        if ziel_id in verknuepfte_ziele(db, mandant_id, typ):
            raise ZuordnungsFehler(400, "Diesem Beleg bzw. dieser Ausgabe ist schon eine Zahlung zugeordnet.")

    umsatz.status, umsatz.zuordnung_typ, umsatz.zuordnung_id = "zugeordnet", typ, ziel_id
    umsatz.zugeordnet_am = datetime.now(timezone.utc)
    record_audit(db, aktion="bank_zuordnung", mandant_id=mandant_id, user_id=user_id, kontext=f"{umsatz.id} {typ} {ziel_id}")
    return umsatz


def ignoriere(db: Session, *, mandant_id: str, umsatz_id: str, grund: str, user_id: str | None) -> Bankumsatz:
    umsatz = _lade_umsatz(db, mandant_id, umsatz_id)
    if umsatz.status != "offen":
        raise ZuordnungsFehler(400, "Dieser Umsatz ist schon zugeordnet oder ignoriert.")
    umsatz.status, umsatz.ignoriert_grund = "ignoriert", grund
    record_audit(db, aktion="bank_ignoriert", mandant_id=mandant_id, user_id=user_id, kontext=umsatz.id)
    return umsatz


def hebe_auf(db: Session, *, mandant_id: str, umsatz_id: str, user_id: str | None) -> Bankumsatz:
    umsatz = _lade_umsatz(db, mandant_id, umsatz_id)
    if umsatz.status == "offen":
        raise ZuordnungsFehler(400, "Dieser Umsatz ist nicht zugeordnet.")
    if umsatz.zuordnung_typ in ("rechnung", "altrechnung"):
        raise ZuordnungsFehler(
            400, "Die Rechnung ist durch diese Zahlung als bezahlt gebucht. Das lässt sich nicht zurücknehmen.",
        )
    umsatz.status, umsatz.zuordnung_typ, umsatz.zuordnung_id = "offen", None, None
    umsatz.zugeordnet_am, umsatz.ignoriert_grund = None, None
    record_audit(db, aktion="bank_zuordnung_aufgehoben", mandant_id=mandant_id, user_id=user_id, kontext=umsatz.id)
    return umsatz


# ---------------------------------------------------------------------------
# Verbindung zu Belegen (wird von app/receipts aufgerufen)


def zahlungsdatum_fuer_beleg(db: Session, mandant_id: str, receipt_id: str) -> date | None:
    return db.scalar(select(Bankumsatz.buchungsdatum).where(
        Bankumsatz.mandant_id == mandant_id, Bankumsatz.zuordnung_typ == "beleg",
        Bankumsatz.zuordnung_id == receipt_id, Bankumsatz.status == "zugeordnet"))


def zahlungsdaten_fuer_belege(db: Session, mandant_id: str) -> dict[str, date]:
    zeilen = db.execute(select(Bankumsatz.zuordnung_id, Bankumsatz.buchungsdatum).where(
        Bankumsatz.mandant_id == mandant_id, Bankumsatz.zuordnung_typ == "beleg", Bankumsatz.status == "zugeordnet"))
    return {zuordnung: datum for zuordnung, datum in zeilen}


def verknuepfe_beleg_mit_ausgabe(db: Session, mandant_id: str, receipt_id: str, ausgabe_id: str) -> None:
    """Wird der Beleg gebucht, zeigt die zugeordnete Zahlung auf die neue Ausgabe."""
    for umsatz in db.query(Bankumsatz).filter(
        Bankumsatz.mandant_id == mandant_id, Bankumsatz.zuordnung_typ == "beleg", Bankumsatz.zuordnung_id == receipt_id,
    ):
        umsatz.zuordnung_typ, umsatz.zuordnung_id = "ausgabe", ausgabe_id


def loese_beleg_zuordnung(db: Session, mandant_id: str, receipt_id: str) -> None:
    """Wird ein Beleg geloescht, wird die zugeordnete Zahlung wieder offen."""
    for umsatz in db.query(Bankumsatz).filter(
        Bankumsatz.mandant_id == mandant_id, Bankumsatz.zuordnung_typ == "beleg", Bankumsatz.zuordnung_id == receipt_id,
    ):
        umsatz.status, umsatz.zuordnung_typ, umsatz.zuordnung_id, umsatz.zugeordnet_am = "offen", None, None, None


def profil_aus_json(wert: str | None) -> CsvProfil | None:
    return CsvProfil.model_validate(json.loads(wert)) if wert else None
