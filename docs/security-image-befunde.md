# Image-Befunde: Abnahme und verbleibende Sperre

Stand: 22. Oktober 2026, Commit `d2608032f7ca57d730a0177ebfe0b5db3e6c0e5c`.

## Nachgewiesenes Ergebnis

- [Deployment-CI](https://github.com/Kayvooo/bilantiq/actions/runs/39823974052): beide Compose-Profile einschließlich
  eingeschränkter API-Rolle und Wiederholungsmigration bestanden.
- Frontend-Image: keine High-/Critical-Meldung im Trivy-Lauf; beide Caddy-Konfigurationen bestanden.
- Backend-Image: Bild-/PDF-/deutsche OCR-Laufzeit bestanden; im Python-Bereich keine High-/Critical-Meldung mehr.
- Debian-Bereich: **80 Paketmeldungen zu 29 unterschiedlichen CVEs**, davon 79 High und eine Critical. In keiner
  dieser Meldungen gibt der Scanner eine reparierte Version für den verwendeten Debian-Zweig an. Der Job bleibt rot.

Das sind Paket-/Versionsbefunde; daraus folgt nicht automatisch dieselbe Erreichbarkeit im Produkt. Es gibt keine
Ausnahme oder abgeschlossene Risikoakzeptanz. Das grüne Frontend-Ergebnis betrifft den Filter High/Critical und den
Zeitpunkt dieses Laufs.

## Was bereits geändert wurde

Pillow 12.3.0 wurde auf 13.0.0 aktualisiert. Python verwendet das offizielle 3.14.9-Trixie-Image mit aktuellen apt-Paketen;
Paketinstaller und deren vendorte Bibliotheken verbleiben nicht in der Laufzeit. Caddy 2.11.7 wurde mit Go 1.27.3 und
x/net 0.60.0 neu gebaut. Die neuen Prüfungen laufen gegen das tatsächlich gebaute Image.

## Architekturfolge und nächste Maßnahmen

**Priorität 1:** F4 aus `security-claude-auftrag.md` umsetzen. Native Dokumentverarbeitung verarbeitet fremde Inhalte
und befindet sich derzeit in der API-Domäne mit Datenbankzugang und Schlüsseln. Ein eigener begrenzter Worker ohne
allgemeinen DB-Zugang, Schlüsselbund oder Internetzugang verringert den möglichen Schaden. Queue-/Zeit-/Speicherlimits
sichern die Verfügbarkeit; Parallelität ist an das RAM des selbst gehosteten Systems anzupassen. Isolation ersetzt
keine Paketpflege und setzt die Image-Schranke nicht automatisch außer Kraft.

**Priorität 2:** Nicht benötigte Laufzeitpakete anhand echter Paketabhängigkeiten entfernen. Insbesondere Hilfsprogramme
und deren Bibliotheken getrennt von tatsächlich benötigten OCR-/PDF-Abhängigkeiten prüfen. Kein manuelles Löschen
von Paketmetadaten, kein Wechsel auf ungeprüfte Distributionspakete und keine selbst gepflegte Bibliothekskopie ohne
klaren Update-Verantwortlichen. Nach jeder Änderung native Verarbeitung und beide Compose-Profile wieder prüfen.

**Priorität 3:** Jede CVE einzeln auf Paketstatus, geladenen Code und erforderliche Rechte bewerten. Bestehende Kontrollen
sind UID 1000, schreibgeschütztes Root-Dateisystem, `cap_drop: ALL`, `no-new-privileges` und kein Docker-Socket.
Sie begrenzen bestimmte Systemrechte; sie schützen die API-Schlüssel nicht zuverlässig vor kompromittierten Parsern.
Eine nötige befristete Ausnahme braucht CVE-ID, überprüfbaren Nachweis, Verantwortlichen, Ablaufdatum und separate
Freigabe. Dieses Dokument genehmigt keine Ausnahme.

**Priorität 4:** Aktuelle Distributions-/Upstream-Updates prüfen und erneut scannen. Fehlende Stable-Fixes lassen sich
nicht durch eine höhere Versionsnummer im Dockerfile versprechen. Bis zur Behebung oder expliziten Einzelfallentscheidung
bleibt die High-/Critical-Schranke aktiv.

## Einordnung anhand der Primärquellen

- [Debian: CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653): Trixie ist betroffen; Debian führt
  den Fall als `no-dsa`/Minor. Trivy verwendet hier die NVD-Einstufung Critical. Diese Abweichung erfordert eine
  Erreichbarkeitsprüfung und ist keine automatische Herabstufung.
- [Debian: CVE-2026-88047](https://security-tracker.debian.org/tracker/CVE-2026-88047): Tesseract in Trixie betroffen,
  kein repariertes Distributionspaket ausgewiesen. Vertrauenswürdige, schreibgeschützte Sprachmodelle sind eine
  relevante Randbedingung; andere Tesseract-Befunde sind unabhängig zu prüfen.
- [Debian: CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642): kein Trixie-Fix ausgewiesen.
  Containerrechte sind bei der Bewertung zu berücksichtigen; eine pauschale Ausnahme aller util-linux-Meldungen
  wurde nicht gesetzt.

## Vollständige Liste der CVE-IDs

Mehrere Binärpakete desselben Quellpakets erklären wiederholte Meldungen. `affected`, `fix_deferred` und `will_not_fix`
sind Scannerstatus und keine Risikoentscheidung für Bilantiq. Für alle Zeilen ist die Bewertung offen.

| CVE | Scanner-Schweregrad | Betroffene Pakete im Image | Scannerstatus |
| --- | --- | --- | --- |
| CVE-2025-69720 | HIGH | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | affected |
| CVE-2026-12064 | HIGH | libcurl3t64-gnutls, libcurl4t64 | affected |
| CVE-2026-16742 | HIGH | libsystemd0, libudev1 | affected |
| CVE-2026-24882 | HIGH | dirmngr, gnupg, gnupg-l10n, gpg, gpg-agent, gpgconf, gpgsm | affected |
| CVE-2026-36849 | HIGH | libtiff6 | will_not_fix |
| CVE-2026-52490 | HIGH | libtiff6 | affected |
| CVE-2026-54369 | HIGH | libacl1 | affected |
| CVE-2026-6653 | CRITICAL | libxml2 | affected |
| CVE-2026-73066 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-74860 | HIGH | libxml2 | affected |
| CVE-2026-76642 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-78408 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-78409 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-78410 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-8458 | HIGH | libcurl3t64-gnutls, libcurl4t64 | affected |
| CVE-2026-86138 | HIGH | libxml2 | affected |
| CVE-2026-86139 | HIGH | libxml2 | affected |
| CVE-2026-86140 | HIGH | libxml2 | affected |
| CVE-2026-86142 | HIGH | libxml2 | affected |
| CVE-2026-86143 | HIGH | libxml2 | affected |
| CVE-2026-86144 | HIGH | libxml2 | affected |
| CVE-2026-88047 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-88048 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-88051 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-88052 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-88053 | HIGH | libtesseract5, tesseract-ocr | affected |
| CVE-2026-88806 | HIGH | libx11-6, libx11-data | affected |
| CVE-2026-88807 | HIGH | libxrender1 | affected |
| CVE-2026-9538 | HIGH | perl-base | fix_deferred |

## Belegbindung

Scanner: Trivy 0.76.1, Filter High/Critical, keine pauschale Unfixed-Ausblendung. Backend-Image-ID:
`sha256:f68599933a0677cc1d6bf0aaa9a63ae2e66b370576329aa36a814647aabc1ceb`, Debian 13.7.
Das CI-Artefakt `sbom-backend` (ID `12446042081`) enthält CycloneDX-SBOM und vollständigen JSON-Bericht;
Artefakt-SHA-256 `c966743a5298da8135aa609a09e818e9b4764d886cd4e0366b53386cdce5dd12`, Aufbewahrung 30 Tage.
Diese Liste erhält die IDs dauerhaft im Repository, ersetzt aber keinen neuen Scan vor einem späteren Rollout.
