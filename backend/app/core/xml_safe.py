"""Sicherer Leser fuer XML aus nicht vertrauenswuerdigen Quellen (E-Rechnung, Kontoauszug).

Hochgeladene XML-Dateien duerfen weder Entitaeten expandieren (Billion Laughs), noch
externe Ressourcen laden (XXE) oder Dateien des Servers lesen. Deshalb werden
DOCTYPE-Deklarationen und Entitaeten grundsaetzlich abgelehnt: Weder XRechnung noch
CAMT.053 brauchen sie."""
from __future__ import annotations

from lxml import etree

MAX_XML_BYTES = 5 * 1024 * 1024


class UngueltigesXml(ValueError):
    """Die Datei ist kein sicher lesbares XML."""


def parse_xml_sicher(daten: bytes, *, max_bytes: int = MAX_XML_BYTES) -> etree._Element:
    if len(daten) > max_bytes:
        raise UngueltigesXml(f"Die XML-Datei ist zu groß (maximal {max_bytes // (1024 * 1024)} MB).")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    try:
        wurzel = etree.fromstring(daten, parser)
    except etree.XMLSyntaxError as exc:
        raise UngueltigesXml("Die Datei ist kein gültiges XML.") from exc

    baum = wurzel.getroottree()
    if baum.docinfo.doctype or baum.docinfo.internalDTD is not None or baum.docinfo.externalDTD is not None:
        raise UngueltigesXml("XML mit DOCTYPE-Deklaration wird aus Sicherheitsgründen nicht akzeptiert.")
    if any(True for _ in wurzel.iter(etree.Entity)):
        raise UngueltigesXml("XML mit Entitäten wird aus Sicherheitsgründen nicht akzeptiert.")
    return wurzel
