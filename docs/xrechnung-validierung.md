# XRechnung-Validierung

Stand: Oktober 2026. Dieses Dokument beschreibt, was Bilantiq an der erzeugten XRechnung prüft, was nicht, und wie Sie
die Prüfung mit dem echten KoSIT-Validator gegenprüfen können.

## Was geprüft wird

Jede erzeugte XRechnung (UBL 2.1, Invoice oder CreditNote) kann vor der Auslieferung gegen die Regeln der
**KoSIT-Validator-Konfiguration XRechnung** geprüft werden:

| Bestandteil | Version | Quelle (fester Commit in `backend/scripts/kosit_regeln_pins.json`) |
|---|---|---|
| XRechnung | 3.0.2 | Konfiguration Release 2026-08-31 (itplr-kosit/validator-configuration-xrechnung) |
| UBL-2.1-XSD | 2.1 | OASIS UBL-2.1.zip (SHA-256 festgeschrieben) |
| EN16931-Schematron | 1.3.16 | ConnectingEurope/eInvoicing-EN16931 (vorkompiliertes XSLT) |
| XRechnung-Schematron | 2.6.0 | itplr-kosit/xrechnung-schematron |
| Peppol BIS Billing | 3.0.21 | OpenPEPPOL/peppol-bis-invoice-3, Commit des Branches 2026-Q2-QA2 (es gibt dazu keinen Release-Tag) |

Ablauf wie im KoSIT-Validator: Szenario über die CustomizationID wählen, XSD prüfen, Schematron (EN16931, XRechnung,
Peppol) nur auf XSD-gültigen Dokumenten ausführen, die Stufen (fatal/error → Fehler, warning → Warnung) aus der
`scenarios.xml` übernehmen. Das Ergebnis enthält Fehler, Warnungen, Regel-IDs (z. B. `BR-DE-15`) und die Regelversion.

## Was damit nicht gesagt ist

- Es ist **nicht der KoSIT-Validator**, sondern dessen Regeln, ausgeführt mit `lxml` (XSD) und `saxonche` (Saxon,
  Schematron als XSLT). Korrekt ist die Formulierung „geprüft gegen die KoSIT-XRechnung-Konfiguration vX mit Saxon“. Von
  „KoSIT-zertifiziert“ oder „vom KoSIT-Validator bestätigt“ ist keine Rede.
- Das XRechnung-Schematron wird mit dem ISO-Schematron-Skeleton übersetzt (nach dem Zusammenführen der Peppol-Regeln),
  nicht mit SchXslt wie in der KoSIT-Konfiguration. Das ist ein Unterschied im Werkzeug. Auf den 33 UBL-Standardfällen der
  KoSIT-Testsuite stimmt das Ergebnis, mehr ist nicht belegt.
- Nicht geprüft werden ZUGFeRD/Factur-X (kein CII-Generator, kein PDF/A-3-Test mit veraPDF), der DATEV-Export und die
  Annahme beim Empfänger (Behörden-Portale, Peppol-Netz).
- Nicht erzeugt werden: Reverse-Charge, innergemeinschaftliche Lieferungen, Befreiungen außer § 19 UStG, Anzahlungen,
  Rabatte/Zuschläge auf Dokumentebene, Anhänge, Verkäufer außerhalb Deutschlands.
- Die Prüfung ist ein Gegencheck, keine Rechtsberatung.

## Regeln holen

Die Regeln liegen nicht im Repository (Lizenzen und Größe, außerdem soll der Stand nachvollziehbar sein).

```
cd backend
python scripts/kosit_regeln_holen.py            # holt in backend/.kosit-regeln (gitignoriert)
python scripts/kosit_regeln_holen.py --neu      # baut den Cache neu
python scripts/kosit_regeln_holen.py --ohne-testinstanzen
```

Das Skript lädt per `git fetch --depth 1` genau die Commits aus `kosit_regeln_pins.json`, bricht ab, wenn ein Hash nicht
stimmt, baut die XSLT-Dateien und schreibt `manifest.json` mit Versionen und Prüfsummen. Dauer etwa 20 Sekunden, Netzzugriff
auf öffentliche GitHub-Repositories nötig. Mit `XRECHNUNG_REGELN_DIR` kann ein anderer Ordner verwendet werden.
Im Docker-Image sind die Regeln nicht enthalten (`.dockerignore`); im Container den Ordner einbinden oder das Skript beim
Bau ausführen.

## Einstellungen und Verhalten

| Variable | Werte | Wirkung |
|---|---|---|
| `XRECHNUNG_PRUEFUNG` | `aus` | keine Prüfung |
| | `warnen` (Standard) | XML wird geliefert, das Ergebnis steht in den Antwort-Headern `X-Xrechnung-Pruefung`, `-Fehler`, `-Warnungen`, `-Regeln` |
| | `blockieren` | bei Fehlern oder fehlenden Regeln HTTP 422 statt der Datei |
| `XRECHNUNG_REGELN_DIR` | Pfad | Ort des Regel-Caches (Standard `backend/.kosit-regeln`) |

Ohne geholte Regeln lautet das Ergebnis „nicht geprüft“, nie „bestanden“. Im Modus `blockieren` führt das zu 422.

Endpunkt: `GET /invoices/{id}/e-rechnung-validierung` liefert das vollständige Ergebnis als JSON (Status, Fehler, Warnungen mit
Regel-ID, Ort und Text, Regelversion, Hinweis zu den Grenzen). Er verlangt volle Anmeldung und ist mandantengetrennt (fremde
Rechnungen: 404). Die XML-Verarbeitung läuft über den sicheren Parser `app/core/xml_safe.py` (keine DTDs, keine Entities).

## Gegenprobe mit dem echten KoSIT-Validator (Anleitung)

Diese Schritte sind in der Entwicklungsumgebung **nicht ausgeführt worden**: Der Zugriff auf GitHub-Releases und Maven
Central war dort gesperrt. Bitte lokal prüfen und das Ergebnis festhalten.

Benötigt: Java 11 oder neuer.

1. Validator (Standalone, Version 1.6.x) von https://github.com/itplr-kosit/validator/releases herunterladen, dazu die
   Konfiguration `xrechnung-3.0.2-validator-configuration-2026-08-31.zip` von
   https://github.com/itplr-kosit/validator-configuration-xrechnung/releases. Prüfsummen mit den Angaben auf den
   Release-Seiten vergleichen, beides nur aus diesen offiziellen Repositories laden.
2. Konfiguration in einen leeren Ordner entpacken.
3. XML aus Bilantiq holen, z. B. `GET /invoices/{id}/e-rechnung` (am besten mit `XRECHNUNG_PRUEFUNG=aus`, damit nichts
   blockiert wird) und als `rechnung.xml` speichern.
4. Ausführen:
   ```
   java -jar validationtool-1.6.3-standalone.jar -s scenarios.xml -r "$PWD" -h rechnung.xml
   ```
   (`-r` ist der Konfigurationsordner, `-h` schreibt zusätzlich einen HTML-Bericht; Dateiname der JAR je nach Version
   anpassen.) Alternativ der Daemon-Modus (`-D`) oder ein Docker-Image, das Sie selbst aus dem offiziellen Repository bauen.
5. Vergleichen: Der Validator meldet `acceptRecommendation` (`accept` oder `reject`) und die Regel-IDs. Bilantiq muss
   dasselbe Ergebnis und dieselben Regel-IDs zeigen. Abweichungen bitte mit der XML-Datei als Fehlerbericht festhalten; sie
   wären ein Fehler der Saxon-Ausführung und gehören nicht ins „bestanden“.

Zusätzlich lohnt sich ein Lauf über die Dateien in `backend/.kosit-regeln/testinstanzen/` (Standardfälle der KoSIT-Testsuite)
mit beiden Werkzeugen.

## Tests

```
cd backend
python scripts/kosit_regeln_holen.py
pytest -q tests/test_e_invoice_validation.py tests/test_xrechnung_generator.py \
          tests/test_xrechnung_pruefung_api.py tests/test_e_rechnung_beispielinstanzen.py
```

Ohne geholte Regeln werden die regelabhängigen Tests mit Hinweis übersprungen. In der CI führt der Job
`xrechnung-validierung` das Skript aus und die Tests danach.

## Mandantendaten für die XRechnung

Die XRechnung verlangt einen Verkäufer-Kontakt (BG-6). Dafür gibt es die Mandantenfelder `telefon` und `kontakt_email`
(verschlüsselt, nur der Inhaber darf sie ändern, Migration 0040). Die Anschrift muss im Format „Straße Nr, PLZ Ort“
vorliegen, damit sie in Straße, PLZ und Ort zerlegt werden kann. Fehlt etwas, nennt die API die fehlenden Pflichtfelder.
