# Sicherheitsarbeiten: Stand und Abnahmegrenzen

Review-Basis: `c63413a74bea1af2570dd0121b144202d2f9c7db`, 22. Oktober 2026.

| Befund | Stand dieses Änderungspakets |
| --- | --- |
| F1: privilegierte API-Datenbankrolle | Migrator, Startprüfung und Upgrade-Weg implementiert; beide Compose-Profile und PostgreSQL-/RLS-Suite in CI bestanden |
| F2: breite Mitgliedsrechte | Claude-Arbeitsauftrag mit Rechtematrix und Tests; hier keine Rollenänderung |
| F3: optionale MFA | Claude-Arbeitsauftrag mit Bestandsübergang, Recovery und frischer Bestätigung |
| F4: Parser in der API-Sicherheitsdomäne | Claude-Arbeitsauftrag für Limits und anschließende Worker-Isolation |
| F5: Schlüsselrotation | Claude-Arbeitsauftrag für Audit-/HMAC-Lebenszyklus |
| F6: Sicherheitsereignisse | Claude-Arbeitsauftrag; veraltete Aussage zu fehlenden IP-Limits korrigiert |
| F7: Restore | Vollständiger Abnahmeplan erstellt; kein realer Restore oder gemeinsamer Snapshot implementiert |
| F8: Lieferkette | Audit-Schranken, gepinnte Actions, Image-Scans/SBOM und Deployment-Workflow implementiert; Frontend-Image grün, Backend-Image durch 29 offene CVEs gesperrt; Repository-Regeln offen |

## Durchgeführt

- Weiterführung F8: hashgeprüfte Laufzeit-/Dev-Locks, Versionsdrift-Prüfung, Multiarch-Image-Digests einschließlich
  PostgreSQL und explizites Bash/pipefail ergänzt. Acht lokale Negativ-/Positivtests der Lock-Prüfung bestanden;
  manipulierte Hashes und fehlgeschlagene Pipelines werden abgewiesen. Vollständige CI-Abnahme dieses Nachtrags offen.
- Gezielte Tests für Laufzeitrechte, Security-Header und Alembic-Head unter Python 3.14.8: **17 bestanden, 7 PostgreSQL-Tests übersprungen** (kein Server).
- GitHub Actions für Commit `8fb9c4b`: SQLite **813 bestanden, 63 übersprungen**; PostgreSQL/RLS **830 bestanden, 46 übersprungen**.
  Beide echten Compose-Startketten (`prod`, `home`) einschließlich Wiederholungsmigration bestanden.
- Erneute vollständige CI für die Image-Updates in `d2608032`: SQLite **813 bestanden, 63 übersprungen**;
  PostgreSQL/RLS **830 bestanden, 46 übersprungen**. Python-/npm-Audit, Frontend-Build, XRechnung-Validierung und beide
  Compose-Profile bestanden. Native Bild-/PDF-/OCR-Laufzeit und beide Caddy-Konfigurationen bestanden ebenfalls.
- Frontend-Image ohne High-/Critical-Meldung; Backend-Python-Abhängigkeiten ebenfalls ohne solche Meldung.
  Das Backend bleibt wegen **80 Debian-Paketmeldungen zu 29 CVEs** gesperrt (79 High, eine Critical, keine vom Scanner
  ausgewiesene reparierte Stable-Version). Vollständige IDs, Belege und nächste Maßnahmen: `security-image-befunde.md`.
- Python-Syntax, YAML-Struktur, Shell-Syntax und `git diff --check` erfolgreich geprüft.
- Frontend: TypeScript-Prüfung, Lint und Build erfolgreich; bestehende Lint-/Bundlegrößenwarnungen vorhanden.
- Unveränderter Ausgangsstand auf separatem Worktree mit Python 3.14.8 und frischer SQLite-Datei geprüft: Abbruch mit
  **1 fehlgeschlagenen Test, 1 Teardown-Fehler und 80 bestandenen Tests**; SQLite meldete einen fehlerhaften Schema-/Indexzustand.
  Der Gesamtlauf der geänderten Version lieferte hier keinen vollständigen auswertbaren Abschlussbericht.
  Ein lokaler Testlauf nach dem Pillow-Update traf zusätzlich auf eine fehlende Poppler-Shared-Library und erneut
  den Schemafehler; er gilt nicht als bestandene Abnahme. Die tatsächliche Image-Prüfung in CI bestand.

## Vor Zusammenführung und produktivem Einsatz

1. Offene Debian-CVEs anhand von `security-image-befunde.md` behandeln. Keine pauschale Ausblendung; die Image-Schranke
   bleibt aktiv. Die F4-Worker-Isolation reduziert die gemeinsame Sicherheitsdomäne von Parsern und API-Geheimnissen.
2. Nach weiteren Code-/Paketänderungen die bestandenen Backend-, Image- und Deployment-Prüfungen erneut ausführen.
3. Erforderliche Checks in GitHub-Regeln hinterlegen. Das Setzen solcher Regeln ist keine Wirkung dieses Code-PRs.
4. Bestehende Secrets nach `security-runtime.md` umstellen; kein automatischer Austausch alter URLs/Schlüssel.
5. Vollständigen isolierten Restore und fachliche Smoke-Tests mit belegten Ergebnissen durchführen.
6. Claude-Pakete separat umsetzen und gegen `security-claude-auftrag.md` prüfen.

Dieses Paket ist ein überprüfbarer Entwurf, keine Freigabe für Produktion und keine DSGVO-/GoBD-Konformitätsbestätigung.
