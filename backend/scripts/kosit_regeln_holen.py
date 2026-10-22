#!/usr/bin/env python3
"""Holt die XRechnung-Pruefregeln und baut sie fuer die Pruefung mit Saxon zusammen.

Was das Skript tut, ehrlich beschrieben:

* Es holt per ``git`` genau die in ``kosit_regeln_pins.json`` festgeschriebenen Staende (Commit-Hash wird geprueft)
  der Regel-Repositories: KoSIT-Konfiguration (Szenarien), CEN-EN16931-Schematron (fertig kompiliertes XSLT),
  XRechnung-Schematron (Quelltext), Peppol-BIS-Schematron, ISO-Schematron-Skeleton und die UBL-2.1-XSD.
* Es baut daraus das XRechnung-Schematron-XSLT. Die KoSIT-Konfiguration macht das mit SchXslt (Ant-Build). SchXslt
  ist hier nicht erreichbar (nicht auf GitHub); stattdessen wird das ISO-Schematron-Skeleton verwendet. Das ist nicht
  dasselbe Programm. Die Ergebnisse wurden gegen die KoSIT-Testsuite abgeglichen (siehe docs/xrechnung-validierung.md).
* Es legt nichts im Repository ab. Ziel ist ein Cache-Ordner (Standard ``backend/.kosit-regeln``, per Git ignoriert).

Aufruf (aus dem Ordner ``backend``)::

    python scripts/kosit_regeln_holen.py                  # holen und bauen
    python scripts/kosit_regeln_holen.py --ziel /pfad     # anderer Ordner (dann XRECHNUNG_REGELN_DIR setzen)
    python scripts/kosit_regeln_holen.py --ohne-testinstanzen
    python scripts/kosit_regeln_holen.py --neu            # vorhandenen Cache verwerfen

Voraussetzungen: ``git`` und das Python-Paket ``saxonche`` (steht in requirements.txt).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
BACKEND = HIER.parent
PINS_DATEI = HIER / "kosit_regeln_pins.json"
STANDARD_ZIEL = BACKEND / ".kosit-regeln"
MANIFEST_NAME = "manifest.json"


class Abbruch(RuntimeError):
    pass


def _git(argumente: list[str], *, cwd: Path) -> str:
    umgebung = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    ergebnis = subprocess.run(
        ["git", *argumente], cwd=cwd, env=umgebung, capture_output=True, text=True, check=False,
    )
    if ergebnis.returncode != 0:
        raise Abbruch(f"git {' '.join(argumente)} fehlgeschlagen:\n{ergebnis.stderr.strip()}")
    return ergebnis.stdout.strip()


def holen(name: str, quelle: dict, ziel: Path) -> Path:
    """Holt genau den gepinnten Commit (flach, nur die benoetigten Pfade) und prueft den Hash."""
    ordner = ziel / name
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    print(f"  {name}: {quelle['url']} @ {quelle['sha'][:12]} ({quelle['ref'].split(' ')[0]})")
    _git(["init", "-q"], cwd=ordner)
    _git(["remote", "add", "origin", quelle["url"]], cwd=ordner)
    _git(["sparse-checkout", "set", "--no-cone", *quelle["pfade"]], cwd=ordner)
    _git(["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", quelle["sha"]], cwd=ordner)
    _git(["checkout", "-q", "FETCH_HEAD"], cwd=ordner)
    ist = _git(["rev-parse", "HEAD"], cwd=ordner)
    if ist != quelle["sha"]:
        raise Abbruch(f"{name}: erwartet {quelle['sha']}, geholt {ist}")
    for relativ, erwartet in quelle.get("datei_sha256", {}).items():
        gelesen = hashlib.sha256((ordner / relativ).read_bytes()).hexdigest()
        if gelesen != erwartet:
            raise Abbruch(f"{name}: Pruefsumme von {relativ} stimmt nicht ({gelesen} statt {erwartet})")
    return ordner


def _sha256(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def bauen(quellen: dict[str, Path], pins: dict, ziel: Path) -> dict:
    try:
        from saxonche import PySaxonProcessor
    except ImportError as exc:  # pragma: no cover - Umgebungsfehler
        raise Abbruch("Das Python-Paket 'saxonche' fehlt (pip install -r requirements.txt).") from exc

    # 1. UBL-XSD aus dem offiziellen OASIS-Paket
    with zipfile.ZipFile(quellen["ubl_xsd"] / "docs" / "UBL-2.1.zip") as paket:
        mitglieder = [m for m in paket.namelist() if m.startswith("xsd/") and m.endswith(".xsd")]
        paket.extractall(ziel / "ubl", members=mitglieder)

    # 2. CEN-Schematron (fertig kompiliertes XSLT aus dem CEN-Repository)
    (ziel / "en16931").mkdir()
    shutil.copy(quellen["en16931_schematron"] / "ubl" / "xslt" / "EN16931-UBL-validation.xslt", ziel / "en16931")

    # 3. KoSIT-Szenarien (liefern die Severity-Ueberschreibungen)
    shutil.copy(quellen["kosit_konfiguration"] / "scenarios.xml", ziel / "scenarios.xml")

    # 4. XRechnung-Schematron: Peppol-Regeln einmischen (wie build.xml), dann mit dem ISO-Skeleton zu XSLT
    xrs = quellen["xrechnung_schematron"]
    bau = xrs / "build"
    for unter in ("schematron/tmp", "schematron/ubl", "bis"):
        (bau / unter).mkdir(parents=True, exist_ok=True)
    shutil.copy(xrs / "src/validation/schematron/common.sch", bau / "schematron/common.sch")
    text = (xrs / "src/validation/schematron/ubl/XRechnung-UBL-validation.sch").read_text(encoding="utf-8")
    text = text.replace("@xr-schematron.version.full@", "2.6.0").replace("@xrechnung.version@", pins["xrechnung_version"])
    (bau / "schematron/tmp/XRechnung-UBL-validation.sch").write_text(text, encoding="utf-8")
    shutil.copy(quellen["peppol_bis"] / "rules/sch/PEPPOL-EN16931-UBL.sch", bau / "bis")

    code = quellen["iso_schematron"] / "trunk/schematron/code"
    with PySaxonProcessor(license=False) as prozessor:
        xslt = prozessor.new_xslt30_processor()
        merge = xslt.compile_stylesheet(stylesheet_file=str(xrs / "src/xsl/peppol-into-xr.xsl"))
        merge.set_parameter("syntax", prozessor.make_string_value("UBL"))
        gemischt = bau / "schematron/ubl/XRechnung-UBL-validation.sch"
        merge.transform_to_file(source_file=str(bau / "schematron/tmp/XRechnung-UBL-validation.sch"), output_file=str(gemischt))

        aktuell = gemischt
        for nr, schritt in enumerate(("iso_dsdl_include.xsl", "iso_abstract_expand.xsl", "iso_svrl_for_xslt2.xsl")):
            stufe = xslt.compile_stylesheet(stylesheet_file=str(code / schritt))
            ausgabe = bau / f"schritt{nr}.xml"
            stufe.transform_to_file(source_file=str(aktuell), output_file=str(ausgabe))
            aktuell = ausgabe
        (ziel / "xrechnung").mkdir()
        shutil.copy(aktuell, ziel / "xrechnung" / "XRechnung-UBL-validation.xsl")
        saxon_version = prozessor.version

    # 5. Lizenztexte der Quellen mitliefern
    (ziel / "lizenzen").mkdir()
    for name, ordner in quellen.items():
        for kandidat in ("LICENSE", "LICENSE.txt", "NOTICE"):
            if (ordner / kandidat).is_file():
                shutil.copy(ordner / kandidat, ziel / "lizenzen" / f"{name}-{kandidat}")

    # 6. Testinstanzen (optional)
    if "testinstanzen" in quellen:
        test = quellen["testinstanzen"] / "src" / "test"
        for dateiname in sorted(test.rglob("*.xml")):
            relativ = dateiname.relative_to(test)
            (ziel / "testinstanzen" / relativ.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy(dateiname, ziel / "testinstanzen" / relativ)
        # Beispiele aus dem CEN-Repository (EN16931, keine XRechnung): nur fuer Lese-Tests
        beispiele = quellen["en16931_schematron"] / "ubl" / "examples"
        if beispiele.is_dir():
            (ziel / "testinstanzen" / "en16931-ubl-beispiele").mkdir(parents=True)
            for dateiname in sorted(beispiele.glob("*.xml")) + sorted(beispiele.glob("*.XML")):
                shutil.copy(dateiname, ziel / "testinstanzen" / "en16931-ubl-beispiele" / dateiname.name.replace(" ", "_"))

    return {"saxon_version": saxon_version}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ziel", type=Path, default=Path(os.environ.get("XRECHNUNG_REGELN_DIR") or STANDARD_ZIEL))
    parser.add_argument("--ohne-testinstanzen", action="store_true")
    parser.add_argument("--neu", action="store_true", help="vorhandenen Cache verwerfen und neu bauen")
    argumente = parser.parse_args()

    pins = json.loads(PINS_DATEI.read_text(encoding="utf-8"))
    ziel: Path = argumente.ziel.resolve()
    manifest_pfad = ziel / MANIFEST_NAME
    if manifest_pfad.is_file() and not argumente.neu:
        vorhanden = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        if vorhanden.get("pins") == pins["quellen"]:
            print(f"Regeln sind schon vorhanden: {ziel} ({vorhanden['bezeichnung']})")
            return 0
        print("Der Cache gehoert zu anderen Pins und wird neu gebaut.")

    arbeit = ziel.parent / (ziel.name + ".arbeit")
    if arbeit.exists():
        shutil.rmtree(arbeit)
    arbeit.mkdir(parents=True)
    neu = ziel.parent / (ziel.name + ".neu")
    if neu.exists():
        shutil.rmtree(neu)
    neu.mkdir(parents=True)
    try:
        print("Hole Quellen ...")
        quellen: dict[str, Path] = {}
        for name, quelle in pins["quellen"].items():
            if name == "testinstanzen" and argumente.ohne_testinstanzen:
                continue
            quellen[name] = holen(name, quelle, arbeit)
        print("Baue Regeln ...")
        info = bauen(quellen, pins, neu)
        xsl = neu / "xrechnung" / "XRechnung-UBL-validation.xsl"
        manifest = {
            "schema": 1,
            "bezeichnung": pins["bezeichnung"],
            "xrechnung_version": pins["xrechnung_version"],
            "kosit_konfiguration_version": pins["kosit_konfiguration_version"],
            "customization_id": pins["customization_id"],
            "pins": pins["quellen"],
            "gebaut_am": dt.date.today().isoformat(),
            "saxon": info["saxon_version"],
            "ausfuehrung": "Saxon (saxonche) mit XSD (lxml) und Schematron-XSLT; nicht das KoSIT-Validator-Programm",
            "schematron_compiler": "ISO-Schematron-Skeleton (nicht SchXslt wie in der KoSIT-Konfiguration)",
            "sha256": {
                "xrechnung/XRechnung-UBL-validation.xsl": _sha256(xsl),
                "en16931/EN16931-UBL-validation.xslt": _sha256(neu / "en16931" / "EN16931-UBL-validation.xslt"),
                "scenarios.xml": _sha256(neu / "scenarios.xml"),
            },
            "testinstanzen": "testinstanzen" in quellen,
        }
        (neu / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if ziel.exists():
            shutil.rmtree(ziel)
        neu.rename(ziel)
    except Abbruch as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
        if neu.exists():
            shutil.rmtree(neu, ignore_errors=True)
    print(f"Fertig: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
