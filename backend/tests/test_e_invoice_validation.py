"""Die Pruefung selbst (app/invoices/e_invoice_validation.py), unabhaengig vom Generator.

Die meisten Tests brauchen die Regeln aus ``scripts/kosit_regeln_holen.py`` und werden ohne sie mit einer klaren
Meldung uebersprungen. In CI laufen sie nach dem Holen der Regeln (Job xrechnung-validierung in backend-ci.yml)."""
from pathlib import Path

import pytest

from app.invoices import e_invoice_validation as val
from app.invoices.e_invoice_validation import (
    STATUS_BESTANDEN,
    STATUS_NICHT_BESTANDEN,
    STATUS_NICHT_GEPRUEFT,
    pruef_header,
    validate_xrechnung,
)

REGELN = val.regeln_ordner()
REGELN_DA = (REGELN / "manifest.json").is_file()
braucht_regeln = pytest.mark.skipif(
    not REGELN_DA, reason="XRechnung-Regeln fehlen: 'python scripts/kosit_regeln_holen.py' im Ordner backend ausfuehren"
)
TESTSUITE = REGELN / "testinstanzen"
STANDARDFAELLE = sorted((TESTSUITE / "business-cases" / "standard").glob("*ubl.xml"))
STANDARDFAELLE = [f for f in STANDARDFAELLE if "uncefact" not in f.name]

braucht_testinstanzen = pytest.mark.skipif(
    not STANDARDFAELLE, reason="KoSIT-Testinstanzen fehlen (Skript ohne --ohne-testinstanzen ausfuehren)"
)


def test_ohne_regeln_ist_das_ergebnis_nicht_geprueft_und_nie_bestanden(tmp_path: Path):
    ergebnis = validate_xrechnung(b"<x/>", regeln_dir=tmp_path)
    assert ergebnis.status == STATUS_NICHT_GEPRUEFT
    assert not ergebnis.bestanden
    assert "kosit_regeln_holen" in ergebnis.grund
    assert pruef_header(ergebnis)["X-Xrechnung-Pruefung"] == "nicht_geprueft"


def test_stufen_wie_im_kosit_report():
    assert val._stufe("fatal", None) == "error"
    assert val._stufe("warning", None) == "warning"
    assert val._stufe("information", None) == "information"
    assert val._stufe(None, "warn") == "warning"
    assert val._stufe(None, None) == "error"  # ohne Angabe gilt Fehler


@braucht_regeln
def test_manifest_nennt_versionen_und_ehrliche_ausfuehrung():
    beschreibung = val.regeln_beschreibung()
    assert beschreibung["xrechnung_version"] == "3.0.2"
    assert beschreibung["kosit_konfiguration"] == "2026-08-31"
    assert "nicht das KoSIT-Validator-Programm" in beschreibung["ausfuehrung"]


@braucht_regeln
def test_custom_levels_kommen_aus_den_kosit_szenarien():
    regeln = val._regeln_laden(REGELN)
    assert regeln.stufen[val.SZENARIO_RECHNUNG]["BR-CL-23"] == "warning"
    assert regeln.stufen[val.SZENARIO_RECHNUNG]["UBL-CR-646"] == "error"


@braucht_regeln
@braucht_testinstanzen
@pytest.mark.parametrize("datei", STANDARDFAELLE, ids=lambda p: p.name)
def test_offizielle_testinstanzen_der_kosit_bestehen(datei: Path):
    """Schutz gegen falsch gebaute Regeln: Die Standard-Geschaeftsfaelle der KoSIT-Testsuite sind gueltig."""
    ergebnis = validate_xrechnung(datei.read_bytes())
    assert ergebnis.status == STATUS_BESTANDEN, ergebnis.kurztext(max_fehler=10)


@braucht_regeln
@braucht_testinstanzen
def test_fehlende_kaeuferreferenz_wird_gefunden():
    xml = STANDARDFAELLE[0].read_text(encoding="utf-8")
    import re

    kaputt = re.sub(r"<cbc:BuyerReference>.*?</cbc:BuyerReference>", "", xml, flags=re.S)
    assert kaputt != xml
    ergebnis = validate_xrechnung(kaputt.encode("utf-8"))
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert "BR-DE-15" in {b.regel_id for b in ergebnis.fehler}


@braucht_regeln
@braucht_testinstanzen
def test_falsche_summe_wird_von_den_en16931_regeln_gefunden():
    xml = STANDARDFAELLE[0].read_text(encoding="utf-8")
    import re

    kaputt = re.sub(r"(<cbc:PayableAmount[^>]*>)[^<]*", r"\g<1>1.00", xml, count=1)
    ergebnis = validate_xrechnung(kaputt.encode("utf-8"))
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert any(b.quelle == "en16931" for b in ergebnis.fehler)


@braucht_regeln
@braucht_testinstanzen
def test_falsche_customization_id_findet_kein_szenario():
    xml = STANDARDFAELLE[0].read_text(encoding="utf-8")
    kaputt = xml.replace("xeinkauf.de:kosit:xrechnung_3.0", "xoev-de:kosit:standard:xrechnung_3.0")
    ergebnis = validate_xrechnung(kaputt.encode("utf-8"))
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert ergebnis.fehler[0].quelle == "szenario"


@braucht_regeln
def test_schemafehler_werden_gemeldet_und_schematron_laeuft_dann_nicht():
    xml = (
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        f"<cbc:CustomizationID>{val._regeln_laden(REGELN).customization_id}</cbc:CustomizationID>"
        "<cbc:Unsinn>x</cbc:Unsinn></Invoice>"
    )
    ergebnis = validate_xrechnung(xml.encode("utf-8"))
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert {b.quelle for b in ergebnis.befunde} == {"xsd"}


@braucht_regeln
def test_kein_xml_und_doctype_werden_abgelehnt():
    assert validate_xrechnung(b"das ist kein xml").status == STATUS_NICHT_BESTANDEN
    mit_doctype = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>'
    ergebnis = validate_xrechnung(mit_doctype)
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert "DOCTYPE" in ergebnis.fehler[0].text


@braucht_regeln
def test_fremdes_xml_ist_kein_pruefbares_szenario():
    ergebnis = validate_xrechnung(b"<a/>")
    assert ergebnis.status == STATUS_NICHT_BESTANDEN
    assert ergebnis.fehler[0].quelle == "szenario"
