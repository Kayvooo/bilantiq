"""CAMT.053 (ISO 20022 Kontoauszug) lesen.

Namespace-unabhaengig ueber local-name(), weil Banken verschiedene Versionen
(camt.053.001.02, .04, .08 ...) ausliefern. Gelesen werden nur gebuchte Eintraege (BOOK).
Mehrere Einzeltransaktionen in einem Sammeleintrag werden zu einzelnen Umsaetzen, wenn
jede einen eigenen Betrag traegt."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

from app.bank.rohdaten import ImportFehler, RohAuszug, RohUmsatz
from app.core.xml_safe import UngueltigesXml, parse_xml_sicher

MAX_UMSAETZE = 20000


def _pfad(*namen: str) -> str:
    return "./" + "/".join(f"*[local-name()='{name}']" for name in namen)


def _tief(*namen: str) -> str:
    return ".//" + "/".join(f"*[local-name()='{name}']" for name in namen)


def _erster(knoten: etree._Element, ausdruck: str) -> etree._Element | None:
    treffer = knoten.xpath(ausdruck)
    return treffer[0] if treffer else None


def _text(knoten: etree._Element, ausdruck: str) -> str | None:
    element = _erster(knoten, ausdruck)
    if element is None or element.text is None:
        return None
    wert = element.text.strip()
    return wert or None


def _datum(knoten: etree._Element, *namen: str) -> date | None:
    wert = _text(knoten, _pfad(*namen, "Dt")) or _text(knoten, _pfad(*namen, "DtTm"))
    if wert is None:
        return None
    try:
        return datetime.fromisoformat(wert.replace("Z", "+00:00")).date() if "T" in wert else date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _betrag(element: etree._Element | None) -> tuple[Decimal, str] | None:
    if element is None or element.text is None:
        return None
    try:
        return Decimal(element.text.strip()), element.get("Ccy") or "EUR"
    except InvalidOperation:
        return None


def _gegenpartei(transaktion: etree._Element, eingang: bool) -> tuple[str | None, str | None]:
    """Bei einem Eingang ist der Zahlende (Debtor) die Gegenpartei, bei einem Ausgang der Empfaenger (Creditor)."""
    seite, konto = ("Dbtr", "DbtrAcct") if eingang else ("Cdtr", "CdtrAcct")
    name = _text(transaktion, _tief("RltdPties", seite, "Nm")) or _text(transaktion, _tief("RltdPties", seite, "Pty", "Nm"))
    iban = _text(transaktion, _tief("RltdPties", konto, "Id", "IBAN"))
    return name, iban


def _verwendungszweck(transaktion: etree._Element | None, eintrag: etree._Element) -> str:
    teile: list[str] = []
    if transaktion is not None:
        teile += [e.text.strip() for e in transaktion.xpath(_tief("RmtInf", "Ustrd")) if e.text and e.text.strip()]
        teile += [e.text.strip() for e in transaktion.xpath(_tief("RmtInf", "Strd", "CdtrRefInf", "Ref")) if e.text and e.text.strip()]
        if not teile:
            zusatz = _text(transaktion, _pfad("AddtlTxInf"))
            if zusatz:
                teile.append(zusatz)
    if not teile:
        zusatz = _text(eintrag, _pfad("AddtlNtryInf"))
        if zusatz:
            teile.append(zusatz)
    return " ".join(teile)


def _ende_zu_ende(transaktion: etree._Element | None) -> str | None:
    if transaktion is None:
        return None
    wert = _text(transaktion, _tief("Refs", "EndToEndId"))
    return None if wert in (None, "NOTPROVIDED") else wert


def lese_camt(daten: bytes) -> RohAuszug:
    try:
        wurzel = parse_xml_sicher(daten)
    except UngueltigesXml as exc:
        raise ImportFehler(str(exc)) from exc

    eintraege = wurzel.xpath("//*[local-name()='Ntry']")
    if not eintraege:
        raise ImportFehler("In der Datei wurden keine Umsätze gefunden. Ist es ein Kontoauszug im Format CAMT.053?")

    konto_iban = _text(wurzel, "//*[local-name()='Stmt']/*[local-name()='Acct']/*[local-name()='Id']/*[local-name()='IBAN']")
    umsaetze: list[RohUmsatz] = []
    for eintrag in eintraege:
        status = _text(eintrag, _pfad("Sts")) or _text(eintrag, _pfad("Sts", "Cd"))
        if status is not None and status != "BOOK":
            continue  # vorgemerkte oder reine Info-Eintraege sind keine Buchungen

        eintrag_betrag = _betrag(_erster(eintrag, _pfad("Amt")))
        richtung = _text(eintrag, _pfad("CdtDbtInd"))
        if eintrag_betrag is None or richtung not in {"CRDT", "DBIT"}:
            raise ImportFehler("Ein Umsatz hat keinen lesbaren Betrag oder keine Soll/Haben-Kennung.")
        buchungsdatum = _datum(eintrag, "BookgDt") or _datum(eintrag, "ValDt")
        if buchungsdatum is None:
            raise ImportFehler("Ein Umsatz hat kein Buchungsdatum.")
        wertstellung = _datum(eintrag, "ValDt")
        storno = (_text(eintrag, _pfad("RvslInd")) or "").lower() == "true"

        transaktionen = eintrag.xpath(_tief("NtryDtls", "TxDtls"))
        einzelbetraege = [_betrag(_erster(t, _tief("AmtDtls", "TxAmt", "Amt")) or _erster(t, _pfad("Amt"))) for t in transaktionen]
        aufteilen = len(transaktionen) > 1 and all(b is not None for b in einzelbetraege)

        if aufteilen:
            quellen = list(zip(transaktionen, einzelbetraege))
            eintrag_richtung = richtung
        else:
            quellen = [(transaktionen[0] if len(transaktionen) == 1 else None, eintrag_betrag)]
            eintrag_richtung = richtung

        for transaktion, betrag in quellen:
            betrag_wert, waehrung = betrag
            eingang = (eintrag_richtung == "CRDT") != storno
            name, gegen_iban = _gegenpartei(transaktion, eingang) if transaktion is not None else (None, None)
            umsaetze.append(
                RohUmsatz(
                    buchungsdatum=buchungsdatum,
                    wertstellung=wertstellung,
                    betrag=betrag_wert if eingang else -betrag_wert,
                    waehrung=waehrung,
                    gegenpartei_name=name,
                    gegenpartei_iban=gegen_iban,
                    verwendungszweck=_verwendungszweck(transaktion, eintrag),
                    end_to_end_id=_ende_zu_ende(transaktion),
                )
            )
        if len(umsaetze) > MAX_UMSAETZE:
            raise ImportFehler(f"Die Datei enthält mehr als {MAX_UMSAETZE} Umsätze. Bitte in kleinere Zeiträume teilen.")

    if not umsaetze:
        raise ImportFehler("Die Datei enthält keine gebuchten Umsätze.")
    return RohAuszug(umsaetze=umsaetze, konto_iban=konto_iban)
