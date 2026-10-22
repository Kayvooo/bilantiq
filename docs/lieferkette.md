# Lieferkette: Abhängigkeits-Audit, Secret-Scan, SBOM

## Änderung vom 22. Oktober 2026: Prüfungen als CI-Schranke

Die folgenden älteren Ergebnisse sind historische Momentaufnahmen. Aktuell gilt:

- Python-Audit-Befunde und Scan-Fehler lassen die Audit-Jobs fehlschlagen; npm-Audit stoppt ab High/Critical.
- Die direkt verwendeten GitHub Actions sind auf überprüfte Commit-SHAs festgelegt; Workflow-Token haben nur
  `contents: read`. Neue Action-/Scanner-Stände benötigen eine bewusste Aktualisierung.
- `deployment-ci.yml` baut Backend und Frontend ohne Produktivsecrets, erzeugt Image-SBOMs (CycloneDX) und prüft mit
  Trivy OS- und Bibliotheksschwachstellen. High/Critical und Scan-Fehler sind Fehler; unfixed Befunde werden nicht
  pauschal ausgeblendet. Eine nötige Ausnahme benötigt konkrete Befund-ID, Begründung, Verantwortlichen und Ablaufdatum.
- Derselbe Workflow prüft für beide Compose-Profile die echte Startkette mit getrenntem Migrator und API-Rolle.
- **Repository-Regeln:** Fehlgeschlagene Jobs verhindern einen Merge erst dann zuverlässig, wenn diese Checks in den
  GitHub-Regeln als erforderlich hinterlegt sind. Dieser Code ändert keine Konto-/Repository-Einstellungen.
- Restpunkte: Hash-Lock für transitive Python-Pakete, geregelte Digest-Updates der Basisimages und zusätzliche
  Release-/Artefaktsignierung. Neue Scanner ersetzen weder Quellcodeprüfung noch einen vollständigen Restore.

Der erste Lauf für `8fb9c4b` bestand bei Python-/npm-Audit, Backend-Suiten und beiden Compose-Profilen. Die neuen
Image-Schranken stoppten korrekt bei High-/Critical-Befunden. Die Basisimages und betroffenen Bibliotheken werden
gezielt aktualisiert; Architektur und Abnahme stehen in `specs/security-images.md`. Es gibt keine pauschalen Ausnahmen.
Die früheren Angaben „nicht blockierend“ unten beschreiben ausschließlich den alten Stand.

Stand: 2026-10-14, Branch `release/abhaengigkeiten`. Frühere Release-Planung, nicht mehr im Repository.
Alle Angaben stammen aus tatsächlich ausgeführten Läufen; wo etwas nicht geprüft wurde, steht das dabei.
Die Audit-Datenbanken ändern sich täglich. Dieses Dokument ist eine Momentaufnahme, kein Dauerzertifikat.

## 1. Abhängigkeits-Audit

### Backend (`pip-audit 2.10.1`, `backend/requirements-dev.txt`, inkl. transitiver Pakete)

Vorher: 14 Meldungen, alle gegen `pyjwt 2.13.0` (PYSEC-2026-4140 bis -4152 und -4183, Aliase CVE-2026-101917 ff.).
Behoben mit `pyjwt==2.15.0` (Minor-Sprung, exakt gepinnt wie alle anderen Pakete). Danach: keine bekannten Schwachstellen.

Erreichbarkeitsbewertung (vor dem Update):

| Gruppe | Betrifft | Für Bilantiq erreichbar? |
|---|---|---|
| Algorithmenverwechslung (HMAC mit asymmetrischem Schlüssel, PEM/DER/JWKS-Varianten) | `jwt.decode` mit gemischter Algorithmenliste oder PyJWK-Schlüsseln | Nein. `app/core/security.py` nutzt nur `HS256` mit String-Secret, `algorithms=[settings.jwt_algorithm]`. |
| `PyJWKClient` (Redirects, ungebremste Abrufe, `kid`-DoS) und `PyJWKSet`/JWK-Parsing | JWKS-Abruf und JWK-Verarbeitung | Nein. Weder `PyJWKClient` noch `PyJWK` kommen im Code vor. |
| Leerer `oct`-JWK bei HS256 | PyJWK-Pfad | Nein, siehe oben. |
| Nicht-Base64URL-Zeichen in der Signatur werden akzeptiert | Token-Identität, relevant nur bei Sperrlisten nach Roh-Token | Praktisch nein: Im Code gibt es keine Sperrliste oder Hash-Ablage von Roh-Tokens (per Suche geprüft, keine Treffer). |
| ReDoS in `is_pem_format`, Mutation des `options`-Dicts | Kundenseitig steuerbare Zertifikate bzw. wiederverwendete Options-Objekte | Nein. Bilantiq reicht keine Zertifikate und kein `options`-Dict durch. |

Das Update war trotzdem sinnvoll: Es ist ein Minor-Sprung, die vollständige Backend-Suite lief danach grün (692 passed, 7 skipped, SQLite), und eine offene Dauer-Ausnahme in einer Sicherheitsbibliothek erspart jede Einzelfallbewertung später.

Hinweis: `pip-audit` kennt nur öffentlich gemeldete Schwachstellen und prüft Versionen, nicht den Code. Systempakete im Docker-Image (Tesseract, poppler, libc usw.) sind damit **nicht** abgedeckt (siehe Abschnitt 4, offene Punkte).

### Frontend (`npm audit`, `frontend/package-lock.json`)

Vorher: 1 Meldung (High): `source-map-js` 1.0.0 bis 1.2.1, Event-Loop-DoS über Source-Map-Offsets (GHSA-68fv-2mgg-jv7q). Transitive Build-Abhängigkeit (über postcss/Vite), nur beim Bauen aktiv, nicht im ausgelieferten Bundle.
Behoben per `npm audit fix` (nur Lockfile, 1.2.1 -> 1.2.2). Danach: 0 Meldungen. `tsc -b --noEmit`, `oxlint` und `vite build` laufen durch (oxlint nennt weiterhin vorhandene Warnungen im Bestand, keine Fehler).

Die frühere Next.js-Website ist nicht mehr Teil des Repositories (Open-Source-Umbau); ihre Abhängigkeiten sind hier nicht mehr relevant.

## 2. Secret-Scan der Git-Historie

`gitleaks` ist nicht installiert. Ersatz: ein eigenes Python-Skript (nicht im Repo) über `git log -p --all` (alle 336 Commits aller Branches, hinzugefügte Zeilen, inklusive später gelöschter Dateien). Gesucht wurde nach: privaten Schlüsseln, `sk_live_`/`sk_test_`, `whsec_`, AWS-Schlüsseln, JWT-artigen Strings, GitHub-/Slack-/Google-Tokens, Zugangsdaten in URLs und hoher Entropie in Zeilen der Form `…SECRET/KEY/PASSWORD/TOKEN = wert`.

Ergebnis: **kein echter Treffer.** Das Skript lieferte 30 Treffer, alle einzeln eingeordnet (Werte nie im Klartext ausgegeben):

- Platzhalter in Vorlagen (`backend/.env.example`: `generate-with…`; `.env.prod.example`: `BITTE_STARKES_…`).
- Variablennamen, Pfade oder Code, der Secrets erst erzeugt oder liest (`init-secrets.sh`, `POSTGRES_PASSWORD_FILE`, `BILANTIQ_SECRETS_DIR`, Zuweisungen wie `accessToken = {…}`).
- Test- und Wegwerfwerte: `user:password@api.example.com` in `build-mobile.test.mjs`, `postgres://geheim:passwort@db-intern` in `test_health.py` (prüft, dass Fehlertexte keine Zugangsdaten leaken), `sk_test_unused` in einem Vorschauskript.
- `docker-compose.yml`: `POSTGRES_PASSWORD` mit einem als „dev only“ benannten Entwicklungswert (Wert in der Entwicklungs-Compose-Datei, nicht in Produktions-Compose). Kein Produktionsgeheimnis, aber ein Entwicklungspasswort im Repo; wer den Compose-Port nach außen öffnet, sollte es ändern.

Mit `git ls-files` und einer Suche nach je hinzugefügten Dateien in der gesamten Historie geprüft: Es sind keine `.env`-Dateien (nur `*.example`), keine Datenbankdateien, keine Dumps, keine Schlüsseldateien und kein `docs/rechtstexte/` getrackt oder je getrackt gewesen.

Auffälligkeiten (nicht geändert, weil außerhalb des Auftrags):

- Das frühere Brand-Paket-ZIP (4,9 MB) wurde im Open-Source-Umbau aus dem Repository entfernt.
- Das `.gitignore` im Root schließt inzwischen `.env` und `.env.*` aus (nur `*.example`-Vorlagen sind erlaubt).
- Das Skript sieht Binärdateien (z. B. das ZIP) nicht und erkennt keine Secrets in unüblichen Formaten. Es ersetzt `gitleaks` nur unvollständig; vor dem Veröffentlichen eines Repositories sollte `gitleaks detect` einmal zusätzlich laufen.

## 3. SBOM

Keine SBOM-Datei im Repo (sie wäre schnell veraltet und gehört ins Release-Artefakt). Erzeugbar mit:

```bash
# Backend (CycloneDX, inkl. transitiver Pakete)
cd backend && pip-audit -r requirements.txt -f cyclonedx-json -o sbom-backend.json
# Frontend (CycloneDX aus dem Lockfile; npm ci vorher)
cd frontend && npm sbom --sbom-format cyclonedx > sbom-frontend.json
```

Probelauf am 2026-10-14: Backend 54 Komponenten (CycloneDX 1.4), Frontend 27 Komponenten (CycloneDX 1.5).
Eine SBOM der Docker-Images (OS-Pakete) fehlt; dafür bräuchte es ein Image-Werkzeug wie `syft`, das hier nicht installiert war.

## 4. CI und offene Punkte

- `backend-ci.yml`: neuer Job `postgres-rls` (Service-Container `postgres:16`, Migrationen als Admin, Laufzeitrolle ohne BYPASSRLS, Suite als diese Rolle) und `pip-audit` (nicht blockierend). `frontend-ci.yml`: `npm-audit` (nicht blockierend). `audit.yml`: wöchentlich plus manuell, Backend, Frontend und Website. Alle Audit-Schritte laufen mit `continue-on-error`.
- **Der Postgres-Job wurde lokal nicht ausgeführt.** Er bildet `backend/scripts/rls_testlauf.sh` nach; die YAML-Syntax ist mit PyYAML geprüft, ein echter Lauf passiert erst auf GitHub. Beim ersten Lauf Logs ansehen. Punkte, die schiefgehen könnten: `psql`-Client-Verfügbarkeit auf dem Runner (auf `ubuntu-latest` vorinstalliert, nicht verifiziert), Python-3.14-Wheels für `psycopg[binary]`.
- Offen: Image-Scan der Docker-Images (z. B. Trivy/Grype), Dependabot oder Renovate für automatische Update-PRs, Hash-Pinning der Python-Abhängigkeiten (`pip-compile --generate-hashes`), `gitleaks` als zusätzlicher Lauf.
