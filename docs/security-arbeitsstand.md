# Sicherheitsarbeiten: Stand und Abnahmegrenzen

Review-Basis: `c63413a74bea1af2570dd0121b144202d2f9c7db`, 22. Oktober 2026.

| Befund | Stand dieses Änderungspakets |
| --- | --- |
| F1: privilegierte API-Datenbankrolle | Implementierungsvorschlag mit Migrator, Startprüfung und Upgrade-Weg; echte Compose-/Postgres-Abnahme noch ausstehend |
| F2: breite Mitgliedsrechte | Claude-Arbeitsauftrag mit Rechtematrix und Tests; hier keine Rollenänderung |
| F3: optionale MFA | Claude-Arbeitsauftrag mit Bestandsübergang, Recovery und frischer Bestätigung |
| F4: Parser in der API-Sicherheitsdomäne | Claude-Arbeitsauftrag für Limits und anschließende Worker-Isolation |
| F5: Schlüsselrotation | Claude-Arbeitsauftrag für Audit-/HMAC-Lebenszyklus |
| F6: Sicherheitsereignisse | Claude-Arbeitsauftrag; veraltete Aussage zu fehlenden IP-Limits korrigiert |
| F7: Restore | Vollständiger Abnahmeplan erstellt; kein realer Restore oder gemeinsamer Snapshot implementiert |
| F8: Lieferkette | CI-Fehler werden nicht verschluckt, Actions gepinnt, Image-Scans/SBOM und Deployment-Workflow ergänzt; Repository-Regeln und erste echte CI-Abnahme offen |

## Durchgeführt

- Gezielte Tests für Laufzeitrechte, Security-Header und Alembic-Head unter Python 3.14.8: **17 bestanden, 7 PostgreSQL-Tests übersprungen** (kein Server).
- Python-Syntax, YAML-Struktur, Shell-Syntax und `git diff --check` erfolgreich geprüft.
- Frontend: TypeScript-Prüfung, Lint und Build erfolgreich; bestehende Lint-/Bundlegrößenwarnungen vorhanden.
- Unveränderter Ausgangsstand auf separatem Worktree mit Python 3.14.8 und frischer SQLite-Datei geprüft: Abbruch mit
  **1 fehlgeschlagenen Test, 1 Teardown-Fehler und 80 bestandenen Tests**; SQLite meldete einen fehlerhaften Schema-/Indexzustand.
  Der Gesamtlauf der geänderten Version lieferte hier keinen vollständigen auswertbaren Abschlussbericht.

## Vor Zusammenführung und produktivem Einsatz

1. Neue CI-Jobs prüfen: beide Compose-Profile, echte PostgreSQL-Laufzeitrolle, erneute Migration, Image-Scan und SBOM.
2. Gesamte Backend-Suite auf dem CI-/Staging-System ausführen; SQLite-Ausgangsfehler nachvollziehen, nicht ignorieren.
3. Erforderliche Checks in GitHub-Regeln hinterlegen. Das Setzen solcher Regeln ist keine Wirkung dieses Code-PRs.
4. Bestehende Secrets nach `security-runtime.md` umstellen; kein automatischer Austausch alter URLs/Schlüssel.
5. Vollständigen isolierten Restore und fachliche Smoke-Tests mit belegten Ergebnissen durchführen.
6. Claude-Pakete separat umsetzen und gegen `security-claude-auftrag.md` prüfen.

Dieses Paket ist ein überprüfbarer Entwurf, keine Freigabe für Produktion und keine DSGVO-/GoBD-Konformitätsbestätigung.
