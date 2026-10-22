"""Prueft erzeugte XRechnungen (UBL) gegen die XRechnung-Regeln: XSD plus Schematron (EN16931 und XRechnung-CIUS).

Was hier wirklich passiert, ohne Beschoenigung:

* Das ist NICHT das KoSIT-Validator-Programm (Java) und keine Zertifizierung. Es werden dieselben Regeldateien
  verwendet, die die KoSIT-Konfiguration "validator-configuration-xrechnung" verwendet (UBL-2.1-XSD, CEN-EN16931-
  Schematron, XRechnung-Schematron mit Peppol-Regeln), ausgefuehrt mit lxml (XSD) und Saxon (Schematron-XSLT). Die
  Einstufung der Meldungen (Fehler/Warnung/Hinweis, Ueberschreibungen je Regel) wird aus der ``scenarios.xml`` der
  KoSIT-Konfiguration gelesen und wie im Validator angewendet.
* Das XRechnung-Schematron wird beim Holen der Regeln mit dem ISO-Schematron-Skeleton statt mit SchXslt zu XSLT
  uebersetzt (siehe scripts/kosit_regeln_holen.py). Das ist ein anderer Compiler als in der KoSIT-Konfiguration.
* Geprueft wird nur die Syntax XRechnung als UBL (Invoice und CreditNote). CII (UN/CEFACT) wird nicht erzeugt und
  nicht geprueft; ZUGFeRD/Factur-X und PDF/A-3 werden nicht geprueft.
* Die Regeln liegen nicht im Repository. Fehlen sie, ist das Ergebnis "nicht_geprueft", nie "bestanden".

Die Regeln und ihre Versionen stehen in ``backend/.kosit-regeln/manifest.json`` (Ort per XRECHNUNG_REGELN_DIR).
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from app.config import settings
from app.core.xml_safe import UngueltigesXml, parse_xml_sicher

STANDARD_REGELN_DIR = Path(__file__).resolve().parents[2] / ".kosit-regeln"

UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDITNOTE_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
SVRL_NS = "http://purl.oclc.org/dsdl/svrl"
SCENARIO_NS = "http://www.xoev.de/de/validator/framework/1/scenarios"

SZENARIO_RECHNUNG = "EN16931 XRechnung (UBL Invoice)"
SZENARIO_GUTSCHRIFT = "EN16931 XRechnung (UBL CreditNote)"

STATUS_BESTANDEN = "bestanden"
STATUS_NICHT_BESTANDEN = "nicht_bestanden"
STATUS_NICHT_GEPRUEFT = "nicht_geprueft"

# Obergrenze fuer Meldungen im Ergebnis: Eine kaputte Datei kann tausende gleichartige Treffer erzeugen.
MAX_BEFUNDE = 200

_STUFE_NACH_KOSIT = {"error": "fehler", "warning": "warnung", "information": "hinweis"}


@dataclass(frozen=True)
class Befund:
    stufe: str  # fehler | warnung | hinweis
    regel_id: str | None
    text: str
    quelle: str  # xml | xsd | en16931 | xrechnung | szenario
    ort: str | None = None

    def als_dict(self) -> dict[str, str | None]:
        return {"stufe": self.stufe, "regel_id": self.regel_id, "text": self.text, "quelle": self.quelle, "ort": self.ort}


@dataclass(frozen=True)
class Pruefergebnis:
    status: str
    befunde: tuple[Befund, ...] = ()
    regeln: dict | None = None
    grund: str | None = None  # nur bei nicht_geprueft
    abgeschnitten: bool = False

    @property
    def fehler(self) -> tuple[Befund, ...]:
        return tuple(b for b in self.befunde if b.stufe == "fehler")

    @property
    def warnungen(self) -> tuple[Befund, ...]:
        return tuple(b for b in self.befunde if b.stufe == "warnung")

    @property
    def hinweise(self) -> tuple[Befund, ...]:
        return tuple(b for b in self.befunde if b.stufe == "hinweis")

    @property
    def bestanden(self) -> bool:
        return self.status == STATUS_BESTANDEN

    def kurztext(self, *, max_fehler: int = 3) -> str:
        if self.status == STATUS_NICHT_GEPRUEFT:
            return f"Nicht geprueft: {self.grund}"
        if self.status == STATUS_BESTANDEN:
            return f"Bestanden ({len(self.warnungen)} Warnungen)"
        zeilen = [f"[{b.regel_id}] {b.text}" if b.regel_id else b.text for b in self.fehler[:max_fehler]]
        rest = len(self.fehler) - len(zeilen)
        if rest > 0:
            zeilen.append(f"... und {rest} weitere Fehler")
        return "; ".join(zeilen)

    def als_dict(self) -> dict:
        return {
            "status": self.status,
            "bestanden": self.bestanden,
            "grund": self.grund,
            "anzahl_fehler": len(self.fehler),
            "anzahl_warnungen": len(self.warnungen),
            "anzahl_hinweise": len(self.hinweise),
            "befunde": [b.als_dict() for b in self.befunde],
            "abgeschnitten": self.abgeschnitten,
            "regeln": self.regeln,
            "hinweis": HINWEIS_GRENZE,
        }


HINWEIS_GRENZE = (
    "Geprueft mit den Regeldateien der KoSIT-XRechnung-Konfiguration, ausgefuehrt mit Saxon. Das ist nicht das "
    "KoSIT-Validator-Programm und keine Zertifizierung. Nur XRechnung als UBL, kein ZUGFeRD/Factur-X."
)


def nicht_geprueft(grund: str, regeln: dict | None = None) -> Pruefergebnis:
    return Pruefergebnis(status=STATUS_NICHT_GEPRUEFT, grund=grund, regeln=regeln)


class _Regeln:
    """Geladene und kompilierte Regeln (einmal je Ordner, danach im Speicher)."""

    def __init__(self, ordner: Path) -> None:
        from saxonche import PySaxonProcessor  # erst hier, damit die App auch ohne saxonche startet

        self.ordner = ordner
        manifest = json.loads((ordner / "manifest.json").read_text(encoding="utf-8"))
        self.customization_id: str = manifest["customization_id"]
        self.beschreibung = {
            "bezeichnung": manifest["bezeichnung"],
            "xrechnung_version": manifest["xrechnung_version"],
            "kosit_konfiguration": manifest["kosit_konfiguration_version"],
            "cen_schematron": manifest["pins"]["en16931_schematron"]["ref"],
            "xrechnung_schematron": manifest["pins"]["xrechnung_schematron"]["ref"],
            "peppol_bis": manifest["pins"]["peppol_bis"]["sha"][:12],
            "ubl": "2.1",
            "ausfuehrung": manifest["ausfuehrung"],
            "schematron_compiler": manifest["schematron_compiler"],
            "gebaut_am": manifest["gebaut_am"],
            "saxon": manifest["saxon"],
        }
        xsd_ordner = ordner / "ubl" / "xsd" / "maindoc"
        self.xsd = {
            UBL_INVOICE_NS: etree.XMLSchema(etree.parse(str(xsd_ordner / "UBL-Invoice-2.1.xsd"))),
            UBL_CREDITNOTE_NS: etree.XMLSchema(etree.parse(str(xsd_ordner / "UBL-CreditNote-2.1.xsd"))),
        }
        self.stufen = {
            SZENARIO_RECHNUNG: _lese_custom_levels(ordner / "scenarios.xml", SZENARIO_RECHNUNG),
            SZENARIO_GUTSCHRIFT: _lese_custom_levels(ordner / "scenarios.xml", SZENARIO_GUTSCHRIFT),
        }
        self.sperre = threading.Lock()  # SaxonC-Prozessoren sind nicht thread-sicher
        self.prozessor = PySaxonProcessor(license=False)
        xslt = self.prozessor.new_xslt30_processor()
        self.en16931 = xslt.compile_stylesheet(stylesheet_file=str(ordner / "en16931" / "EN16931-UBL-validation.xslt"))
        self.xrechnung = xslt.compile_stylesheet(stylesheet_file=str(ordner / "xrechnung" / "XRechnung-UBL-validation.xsl"))


def _lese_custom_levels(scenarios: Path, szenario: str) -> dict[str, str]:
    """Regel-ID -> Stufe (error/warning/information) aus den customLevel-Eintraegen des Szenarios."""
    baum = etree.parse(str(scenarios))
    ns = {"s": SCENARIO_NS}
    ergebnis: dict[str, str] = {}
    for knoten in baum.xpath("//s:scenario[s:name=$name]//s:customLevel", namespaces=ns, name=szenario):
        for code in (knoten.text or "").split():
            ergebnis[code] = knoten.get("level")
    return ergebnis


_cache: dict[Path, _Regeln] = {}
_cache_sperre = threading.Lock()


def regeln_ordner(regeln_dir: str | Path | None = None) -> Path:
    if regeln_dir:
        return Path(regeln_dir)
    if settings.xrechnung_regeln_dir:
        return Path(settings.xrechnung_regeln_dir)
    return STANDARD_REGELN_DIR


def _regeln_laden(ordner: Path) -> _Regeln:
    ordner = ordner.resolve()
    with _cache_sperre:
        if ordner not in _cache:
            _cache[ordner] = _Regeln(ordner)
        return _cache[ordner]


def regeln_beschreibung(regeln_dir: str | Path | None = None) -> dict | None:
    """Version der vorhandenen Regeln oder None, wenn sie fehlen oder nicht ladbar sind."""
    try:
        return _regeln_laden(regeln_ordner(regeln_dir)).beschreibung
    except Exception:  # noqa: BLE001 - fehlende Regeln und fehlendes saxonche sind erwartete Zustaende
        return None


def _stufe(flag: str | None, rolle: str | None) -> str:
    """Wie default-report.xsl der KoSIT-Konfiguration: fatal/error -> Fehler, warning -> Warnung, sonst Fehler."""
    werte = {w for w in (flag, rolle) if w}
    if werte & {"fatal", "error"}:
        return "error"
    if werte & {"warning", "warn"}:
        return "warning"
    if werte & {"information", "info"}:
        return "information"
    return "error"


def _svrl_befunde(svrl_text: str, quelle: str, ueberschreibungen: dict[str, str]) -> list[Befund]:
    wurzel = etree.fromstring(svrl_text.encode("utf-8"))
    ergebnis: list[Befund] = []
    for knoten in wurzel.iter(f"{{{SVRL_NS}}}failed-assert", f"{{{SVRL_NS}}}successful-report"):
        regel_id = knoten.get("id")
        stufe = ueberschreibungen.get(regel_id or "") or _stufe(knoten.get("flag"), knoten.get("role"))
        text = " ".join("".join(knoten.findtext(f"{{{SVRL_NS}}}text") or "").split())
        ergebnis.append(
            Befund(stufe=_STUFE_NACH_KOSIT[stufe], regel_id=regel_id, text=text, quelle=quelle, ort=knoten.get("location"))
        )
    return ergebnis


def validate_xrechnung(xml_bytes: bytes, *, regeln_dir: str | Path | None = None) -> Pruefergebnis:
    """Prueft eine XRechnung (UBL). Wirft nie wegen fehlender Regeln: dann ist der Status "nicht_geprueft"."""
    ordner = regeln_ordner(regeln_dir)
    if not (ordner / "manifest.json").is_file():
        return nicht_geprueft(
            "Die Pruefregeln fehlen. Mit 'python scripts/kosit_regeln_holen.py' holen, siehe "
            "docs/xrechnung-validierung.md."
        )
    try:
        regeln = _regeln_laden(ordner)
    except ImportError:
        return nicht_geprueft("Das Python-Paket 'saxonche' ist nicht installiert.")
    except Exception as fehler:  # noqa: BLE001
        return nicht_geprueft(f"Die Pruefregeln lassen sich nicht laden: {type(fehler).__name__}: {fehler}")

    try:
        wurzel = parse_xml_sicher(xml_bytes)
    except UngueltigesXml as fehler:
        return Pruefergebnis(
            status=STATUS_NICHT_BESTANDEN, regeln=regeln.beschreibung,
            befunde=(Befund("fehler", None, str(fehler), "xml"),),
        )

    name = etree.QName(wurzel)
    if name.namespace not in regeln.xsd:
        return Pruefergebnis(
            status=STATUS_NICHT_BESTANDEN, regeln=regeln.beschreibung,
            befunde=(Befund("fehler", None, "Kein UBL-Dokument (erwartet: Invoice oder CreditNote).", "szenario"),),
        )
    szenario = SZENARIO_RECHNUNG if name.namespace == UBL_INVOICE_NS else SZENARIO_GUTSCHRIFT
    customization = wurzel.findtext(f"{{{CBC_NS}}}CustomizationID")
    befunde: list[Befund] = []
    if (customization or "").strip() != regeln.customization_id:
        # Der KoSIT-Validator findet dann kein Szenario und weist das Dokument zurueck.
        return Pruefergebnis(
            status=STATUS_NICHT_BESTANDEN, regeln=regeln.beschreibung,
            befunde=(Befund(
                "fehler", None,
                f"Kein passendes Pruefszenario: CustomizationID (BT-24) ist '{customization}', "
                f"erwartet '{regeln.customization_id}'.",
                "szenario",
            ),),
        )

    schema = regeln.xsd[name.namespace]
    if not schema.validate(wurzel.getroottree()):
        for eintrag in list(schema.error_log)[:MAX_BEFUNDE]:
            befunde.append(Befund("fehler", None, eintrag.message, "xsd", f"Zeile {eintrag.line}"))
    else:
        # Wie der KoSIT-Validator: Schematron laeuft nur auf schemagueltigen Dokumenten.
        sauber = etree.tostring(wurzel, encoding="unicode")
        try:
            with regeln.sperre:
                dokument = regeln.prozessor.parse_xml(xml_text=sauber)
                svrl_en = regeln.en16931.transform_to_string(xdm_node=dokument)
                svrl_xr = regeln.xrechnung.transform_to_string(xdm_node=dokument)
        except Exception as fehler:  # noqa: BLE001
            return nicht_geprueft(f"Die Schematron-Pruefung ist fehlgeschlagen: {type(fehler).__name__}: {fehler}", regeln.beschreibung)
        ueberschreibungen = regeln.stufen[szenario]
        befunde.extend(_svrl_befunde(svrl_en, "en16931", ueberschreibungen))
        befunde.extend(_svrl_befunde(svrl_xr, "xrechnung", ueberschreibungen))

    abgeschnitten = len(befunde) > MAX_BEFUNDE
    befunde = befunde[:MAX_BEFUNDE]
    status = STATUS_NICHT_BESTANDEN if any(b.stufe == "fehler" for b in befunde) else STATUS_BESTANDEN
    return Pruefergebnis(status=status, befunde=tuple(befunde), regeln=regeln.beschreibung, abgeschnitten=abgeschnitten)


class PruefungBlockiert(Exception):
    """Im Modus "blockieren" besteht die XRechnung die Pruefung nicht (oder konnte nicht geprueft werden)."""

    def __init__(self, ergebnis: Pruefergebnis) -> None:
        super().__init__(ergebnis.kurztext())
        self.ergebnis = ergebnis


def pruefe_vor_auslieferung(xml_bytes: bytes) -> Pruefergebnis | None:
    """Wendet den konfigurierten Modus an. None heisst: Pruefung ausgeschaltet."""
    modus = settings.xrechnung_pruefung
    if modus == "aus":
        return None
    ergebnis = validate_xrechnung(xml_bytes)
    if modus == "blockieren" and not ergebnis.bestanden:
        raise PruefungBlockiert(ergebnis)
    return ergebnis


def pruef_header(ergebnis: Pruefergebnis | None) -> dict[str, str]:
    """Antwort-Header, damit ein nicht bestandenes oder ungepruefte XML nicht still als fertig durchgeht."""
    if ergebnis is None:
        return {"X-Xrechnung-Pruefung": "aus"}
    header = {
        "X-Xrechnung-Pruefung": ergebnis.status,
        "X-Xrechnung-Fehler": str(len(ergebnis.fehler)),
        "X-Xrechnung-Warnungen": str(len(ergebnis.warnungen)),
    }
    if ergebnis.regeln:
        header["X-Xrechnung-Regeln"] = (
            f"KoSIT-Konfiguration {ergebnis.regeln['kosit_konfiguration']} / XRechnung "
            f"{ergebnis.regeln['xrechnung_version']} (Saxon, kein Original-Validator)"
        )
    return header
