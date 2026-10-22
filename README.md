# Bilantiq

Buchhaltungssoftware zum **Selbst-Hosten**, mit Fokus auf Datenschutz (DSGVO) und Nachvollziehbarkeit (GoBD):
Rechnungen inkl. XRechnung, Angebote, Belegerfassung, Mahnwesen, EÜR/UStVA/BWA und DATEV-Export. Die KI-Funktionen laufen
ausschließlich lokal (eigener Inferenz-Dienst, kein Cloud-Fallback) und sind standardmäßig aus.

Lizenz: [GNU AGPL-3.0](LICENSE). Name und Logo: siehe [TRADEMARK.md](TRADEMARK.md).

> **Wichtig, bitte lesen.** Bilantiq ist ein Open-Source-Projekt ohne Gewähr. Es ist **keine Steuer- oder Rechtsberatung** und
> kein geprüftes oder zertifiziertes Buchhaltungsprogramm. Was nicht getestet oder geprüft ist, steht unten unter
> „Bekannte Grenzen". Prüfen Sie Ergebnisse (Rechnungen, Steuerwerte, Exporte) mit Ihrer Steuerberatung, bevor Sie sich
> darauf verlassen.

## Selbst hosten: eigener Speicher und eigene Verantwortung

Es gibt **keinen gehosteten Dienst** und **keinen zentralen Speicher** des Projekts. Wer eine Instanz betreibt, sorgt selbst für

- **Speicher**: Datenbank (Postgres-Volume) und Dateien (Belege, Logos, Briefpapier, Kontoauszüge, Altrechnungs-Archiv unter
  `STORAGE_DIR`, im Docker-Setup das Volume `backend_data`), jeweils auf dem eigenen Server;
- **Backups**: regelmäßig, verschlüsselt, mit Kopie außerhalb des Servers und getestetem Restore;
- **Schlüssel**: Der Verlust von `DATA_ENCRYPTION_KEYS` macht alle verschlüsselten Daten unwiederbringlich unlesbar, auch mit
  Backup. Schlüssel getrennt vom Datenbackup sichern;
- **Updates und Sicherheit**: Server, Docker, Images und Bilantiq aktuell halten, Registrierung begrenzen
  (`REGISTRATION_MODE`, Standard `first_account`: nur das erste Konto registriert sich selbst, weitere Personen per
  Einladungscode), TLS und Firewall einrichten;
- **Recht**: Aufbewahrungsfristen, GoBD und Datenschutz (DSGVO) liegen in der Verantwortung der Betreiberin bzw. des
  Betreibers.

E-Mail (SMTP) ist optional; ohne sie sind Versand und „Passwort vergessen" abgeschaltet, ein Wiederherstellungsweg für
Betreiber steht in der Anleitung. Schnellstart, Speicher, Backups, Updates und Checkliste:
**[docs/self-hosting.md](docs/self-hosting.md)**. Sicherheitslücken melden: [SECURITY.md](SECURITY.md).
Mitmachen: [CONTRIBUTING.md](CONTRIBUTING.md).

## Funktionsüberblick

- **Verkauf**: Rechnungen (inkl. XRechnung/ZUGFeRD, wiederkehrende Rechnungen, Gutschriften), Angebote inkl. Umwandlung in Rechnung, Auftragsbestätigung und Lieferscheine, dreistufiges Mahnwesen, Kontakte, Produktkatalog mit optionaler Lagerbestandsführung (Zugang/Abgang-Buchungen wie ein Kassenbuch).
- **E-Mail-Versand**: Rechnungen, Angebote und Mahnungen lassen sich direkt aus der App per E-Mail mit PDF-Anhang verschicken (eigene SMTP-Anbindung, kein Drittanbieter-SDK).
- **Rechnungs-Designer**: 11 PDF-Vorlagen × 4 Design-Varianten, Logo, Briefpapier, Sprache (De/En), 10 Element-Toggles, GiroCode (EPC-QR), echte Mehrseiten-Paginierung — als mandantenweites Standarddesign mit Live-Vorschau.
- **Ausgaben**: lokale OCR-Belegerfassung (kein bezahlter KI-API-Call), wiederkehrende Ausgaben ohne Beleg, sonstige Einnahmen, manuelles Kassenbuch, Anlagenverwaltung mit linearer AfA (fließt automatisch in EÜR/BWA/SuSa/DATEV ein).
- **Auswertungen**: EÜR, UStVA, SuSa, BWA, DATEV-Export (EXTF-CSV, SKR03), 8-Wochen-Cashflow-Prognose (deterministisch), Dashboard mit Kennzahlen.
- **Verwaltung**: Mehrbenutzer (Einladungscode oder direktes Anlegen durch den Inhaber), Buchhaltungsvorgaben (Standard-Zahlungsziel, Standard-USt, Kleinunternehmerregelung), Steuerberater-Kontaktdaten, DSGVO-Datenexport (Art. 15/20, nur Inhaber, als JSON mit entschlüsselten Feldern), Konto-Anonymisierung.

## Technik

- Backend: Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 (`backend/`). Produktion: Postgres mit Row-Level-Security;
  lokal und in den Tests SQLite mit Anwendungs-Ebene als Ersatz (`app/core/rls.py`).
- Frontend: React 19, TypeScript, Vite, handgeschriebenes CSS ohne UI-Framework (`frontend/`).
- Sicherheit: Argon2id, serverseitig widerrufbare Sitzungen, optionale MFA (TOTP), AES-256-GCM-Verschlüsselung sensibler
  Felder und Dateien mit rotierbarem Schlüsselbund, append-only Audit-Log.
- Belegerfassung: lokal mit Tesseract, ohne Cloud-API. Lokale KI: OpenAI-kompatible Schnittstelle zu einem eigenen Dienst
  (`AI_ENABLED=false` ist der Standard).
- Betrieb: Docker Compose mit Postgres, Backend und Caddy (automatisches TLS), `age`-verschlüsselte Backups.

## Entwicklung

Backend (Python 3.13 oder 3.14), Linux/macOS:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/dev_env_erzeugen.py   # legt .env mit frischen Schlüsseln an (nur für lokal)
uvicorn app.main:app --reload
pytest -q                            # SQLite, kein Postgres nötig; die Postgres-RLS-Tests brauchen TEST_DATABASE_ADMIN_URL
```

Windows (PowerShell):

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1          # bei einer Fehlermeldung zuerst: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements-dev.txt
python scripts/dev_env_erzeugen.py
uvicorn app.main:app --reload
```

Die API läuft dann auf `http://localhost:8000`, die interaktive API-Doku unter `/docs`. Für die Belegerfassung (OCR) werden
zusätzlich Tesseract mit deutschem Sprachpaket und Poppler gebraucht (Linux: `sudo apt install tesseract-ocr tesseract-ocr-deu
poppler-utils`); ohne sie funktioniert alles andere.

Frontend (zweites Terminal, Node.js 22 oder neuer):

```bash
cd frontend
npm ci
npm run dev          # öffnet http://localhost:5173; die API-Adresse steht in frontend/.env.example
```

Beim ersten Aufruf legen Sie das erste Konto an (Registrierung ist im Standard nur für das erste Konto offen).

Ist Port 8000 schon belegt (dann zeigt das Frontend zum Beispiel „Not Found", weil dort ein anderes Programm antwortet), starten
Sie das Backend auf einem anderen Port und sagen dem Frontend, wo es ist:

```bash
uvicorn app.main:app --reload --port 8010                  # im Ordner backend
VITE_API_BASE_URL=http://localhost:8010 npm run dev        # im Ordner frontend (PowerShell: $env:VITE_API_BASE_URL="http://localhost:8010"; npm run dev)
```

Prüfen, ob wirklich Bilantiq antwortet: `curl -s localhost:8010/openapi.json | head -c 80` muss `"title":"Bilantiq` zeigen.

Vor einem Pull Request: `npx tsc -b --noEmit`, `npm run lint`, `npm run build` und `pytest -q`. Die lokale Dev-Datenbank wird
per `create_all()` erzeugt und ändert bestehende Spalten nicht: bei Schemaänderungen die Datei löschen. Produktion nutzt
ausschließlich Alembic-Migrationen (`backend/migrations/`).

## Betrieb

Produktions-Stack, Secrets, Backups, Restore, Updates und Notfälle: [docs/self-hosting.md](docs/self-hosting.md),
[docs/backup-restore.md](docs/backup-restore.md), [docs/rollback.md](docs/rollback.md),
[docs/security-production.md](docs/security-production.md), [docs/betrieb-runbook.md](docs/betrieb-runbook.md),
[docs/incident-response.md](docs/incident-response.md). Die Betriebs- und Datenschutzdokumente sind Entwürfe, nicht rechtlich
geprüft.

## Lohnvorbereitung (Phase 3)

Unter **Mehr → Lohnvorbereitung** lassen sich Mitarbeitende anlegen, bearbeiten,
deaktivieren und reaktivieren. Monatliche Bruttowerte werden als Monatsentwürfe
erfasst und können solange korrigiert werden, bis sie als „abgeschlossen“ markiert
werden; ein abgeschlossener Entwurf kann zur Korrektur wieder reaktiviert werden.
Zusätzlich stehen eine klar gekennzeichnete CSV-Arbeitsdatei und ein Lohnzettel-PDF
pro Person/Monat für die Steuerkanzlei bereit. Personennamen werden verschlüsselt
gespeichert, alle Datensätze sind mandantengetrennt.

Der aktuelle Baustein ist keine rechtsverbindliche Lohnabrechnung: Er berechnet
keine Lohnsteuer oder Sozialversicherungsbeiträge und sendet keine ELSTER-,
ELStAM-, DEÜV- oder eAU-Meldungen. Für den elektronischen Datenaustausch mit
Sozialversicherungsträgern braucht das Produkt zunächst die ITSG-Systemprüfung
einschließlich Pilotbetrieb und eine gültige Prod-MOD-ID. Die ausführliche Grenze
steht in `docs/specs/lohnvorbereitung.md`.

## Bekannte Grenzen (bewusst offen kommuniziert statt verschwiegen)

- **XRechnung (erzeugt):** Das UBL-XML wird gegen XSD und Schematron der KoSIT-XRechnung-Konfiguration geprüft
  (XRechnung 3.0.2, Konfiguration Release 2026-08-31: EN16931-Schematron 1.3.16, XRechnung-Schematron 2.6.0, Peppol BIS
  3.0.21), ausgeführt mit lxml und Saxon (`saxonche`). Das ist **geprüft gegen die KoSIT-XRechnung-Konfiguration mit Saxon**,
  nicht „KoSIT-zertifiziert": Der Java-Validator selbst läuft in Bilantiq nicht, und das XRechnung-Schematron wird mit dem
  ISO-Schematron-Skeleton statt mit SchXslt übersetzt. Auf den 33 UBL-Standardfällen der KoSIT-Testsuite stimmt das Ergebnis,
  eine Gegenprobe mit dem Original-Validator auf Ihrer Maschine steht noch aus (Anleitung: `docs/xrechnung-validierung.md`).
  Die Regeln liegen nicht im Repository; sie werden mit `python backend/scripts/kosit_regeln_holen.py` geholt. Ohne sie ist das
  Ergebnis „nicht geprüft", nie „bestanden". Einstellung `XRECHNUNG_PRUEFUNG` (`aus`, `warnen` als Standard, `blockieren`).
- **XRechnung (nicht abgedeckt):** nur UBL, kein CII-Generator; nur Verkäufer in Deutschland; Steuerbefreiung nur nach § 19 UStG,
  kein Reverse-Charge, keine innergemeinschaftlichen Lieferungen, keine Anzahlungen, keine Rabatte auf Dokumentebene, keine
  Anhänge. Die Prüfung belegt die Einhaltung der Regeln, nicht, dass der Empfänger (z. B. Behörden-Portal) die Datei annimmt.
  Eingehende E-Rechnungen werden nur gelesen, nicht geprüft; Gutschriften werden nicht automatisch gelesen.
- ZUGFeRD ist best-effort und nicht Factur-X-zertifiziert (angehängt wird das UBL-XML, kein CII, kein veraPDF-geprüftes PDF/A-3).
- DATEV-Export ist nicht gegen echtes DATEV getestet; SKR03-Kontonummern (inkl. der für Anlagen-AfA verwendeten 4830/0490) sind nicht steuerberatergeprüfte Annahmen.
- Mahngebühren sind Platzhalterwerte.
- Cashflow-Prognose ist bewusst deterministisch (keine Bankanbindung, keine KI-Schätzung).
- Lohnvorbereitung ersetzt keine echte Lohnabrechnung (siehe oben).
- finAPI/Bankanbindung ist bis auf Weiteres bewusst ausgeklammert — kein automatischer Kontoabgleich, Zahlungen werden manuell als bezahlt markiert.
- Automatischer Lagerbestandsabzug beim Verkauf ist nicht verdrahtet (Rechnungspositionen sind noch nicht mit dem Produktkatalog verknüpft).
- Visuelle Browser-Abnahme des Desktop-Layouts und mehrerer neuerer Seiten steht noch aus; `tsc`, Lint und Build ersetzen das nicht.
- Die Betriebs- und Datenschutzdokumente in `docs/` sind Entwürfe und nicht rechtlich geprüft.

## Dokumentation und Änderungen

Feature-Beschreibungen mit den jeweils getroffenen Annahmen liegen in [`docs/specs/`](docs/specs/). Änderungen:
[CHANGELOG](CHANGELOG.md).
