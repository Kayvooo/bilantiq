# Changelog

Alle nennenswerten Änderungen an Bilantiq. Das Format orientiert sich an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/). Der Eintrag unten ist ein **Entwurf**, abgeleitet aus
der Git-Historie (Commits vom 5. September bis 14. Oktober 2026). Es wurde **kein Tag gesetzt**; Versionsnummer
und Datum legt der Owner beim Release fest (Release-Plan 1.9).

## [Unveröffentlicht] - Zwei-Faktor-Pflicht für Owner und frische Bestätigung (Sicherheitspaket F3)

Spec: `docs/specs/mfa-pflicht.md`. **Das ändert das Standardverhalten bestehender Instanzen:**

- **Owner brauchen MFA** (`MFA_PFLICHT=owner`, Standard; `alle` für jede Rolle; `aus` nur mit `APP_ENV=development`). Ein Owner ohne MFA bekommt nach dem Login nur den Einrichtungsbildschirm (`status: "mfa_einrichtung_erforderlich"`, kein `access_token`); fachliche Routen sind gesperrt, bis MFA eingerichtet ist.
- **Update bestehender Instanzen:** Owner ohne MFA werden beim ersten Aufruf nach dem Update einmal abgemeldet (HTTP 401) und richten MFA beim nächsten Login ein. Keine Datenbankmigration nötig.
- **MFA abschalten** ist für Pflichtrollen gesperrt (neu einrichten geht weiter). Der Betreiber-Reset (`konto_wiederherstellen --mfa-zuruecksetzen`) führt den Owner in die Neueinrichtung, nicht zu einem Zugang ohne MFA.
- **Frische Bestätigung** (5 Minuten, `POST /auth/bestaetigung`, Header `X-Bestaetigung`) für IBAN/BIC-Änderung, Benutzerverwaltung (Einladung, Direktanlage, Entfernen) und Gesamtexport. Ohne Bestätigung HTTP 428. Neue Einstellung `BESTAETIGUNG_MINUTEN` (Standard 5).
- Die Testumgebung setzt `MFA_PFLICHT=aus`; die Pflicht selbst deckt `backend/tests/test_mfa_pflicht.py` ab.

## [Unveröffentlicht] - Heimserver-Betrieb über VPN

- **Neu:** `docker-compose.home.yml`, `Caddyfile.home` und `.env.home.example` für den Betrieb auf einem eigenen Rechner, erreichbar nur
  über ein VPN (z. B. Tailscale). Caddy lauscht nur auf `127.0.0.1:8080` ohne TLS, Oberfläche und API liegen unter einer Adresse
  (`/api`). Anleitung: `docs/heimserver-tailscale.md`. Noch nicht auf einem echten Docker-Host ausprobiert.
- `frontend/Dockerfile` nimmt die Caddyfile über das Build-Argument `CADDYFILE` (Standard unverändert `Caddyfile`).

## [Unveröffentlicht] - Bezahlfunktion entfernt

### Entfernt
- Bezahlfunktion entfernt: Stripe-Anbindung, Tarife (Free/Pro/Business), Monats- und Nutzerlimits, HTTP-402-Sperren, die Tarifseite und der Online-Zahllink für Rechnungen (`/billing/*`, `/zahlen/{token}`). Alle Funktionen stehen jedem Mandanten ohne Einschränkung zur Verfügung; die lokale KI bleibt wie bisher standardmäßig ausgeschaltet (`AI_ENABLED=false`).
- Migration `0039` entfernt die Tarif- und Stripe-Spalten an `mandanten` und `invoices`, die Tabelle `webhook_ereignisse` und unter Postgres die Funktion `bq_mandant_aus_stripe_kunde`. Tarifstand, Stripe-Kennungen und Zahllink-Token gehen dabei verloren; der Rückweg legt die Spalten leer wieder an.
- Die Umgebungsvariablen `STRIPE_*` und `BILLING_FRONTEND_URL` sowie die Abhängigkeit `stripe` entfallen.

## [Unveröffentlicht] - Selbst-Hosting: eigener Speicher, optionale E-Mail, sichere Voreinstellungen

Teil des Umbaus zum Open-Source-Projekt (Branch `oss/storage-sicherheit`). Gilt für Betreiber eigener Instanzen; Details in `docs/self-hosting.md`.

- **Speicher:** neuer Basisordner `STORAGE_DIR` (Standard `./data`, im Docker-Image `/app/data`) für alle Dateien; die Unterordner leiten sich daraus ab und bleiben einzeln überschreibbar. Startprüfung (`python -m app.core.storage_check`, zusätzlich im App-Start): legt Ordner mit 0700 an, schreibt eine Probedatei, setzt zu weite Rechte zurück und bricht mit lesbarer Meldung ab. Das Docker-Image führt sie vor den Migrationen aus und setzt `PYTHONPATH=/app` (ohne diesen Pfad fand `python scripts/reencrypt_storage.py` das Paket `app` nicht; lokal nachgestellt, im Container nicht ausgeführt). Kein S3-/Cloud-Speicher.
- **E-Mail ist optional:** ohne SMTP startet die App; Versand von Rechnungen/Angeboten/Mahnungen, „Passwort vergessen“ und die E-Mail-Bestätigung antworten mit HTTP 503 und einer klaren Meldung. Kein voreingestellter Absender (`noreply@bilantiq.de` entfällt); `SMTP_ABSENDER`, sonst `SMTP_USER` als Adresse.
- **Registrierung:** neue Einstellung `REGISTRATION_MODE` mit `first_account` (neuer Standard: nur das erste Konto, weitere per Einladungscode), `closed` und `open` (bisheriges Verhalten). **Das ändert das Standardverhalten:** wer mehrere Firmen frei registrieren will, setzt `REGISTRATION_MODE=open`.
- **Wiederherstellung für Betreiber:** `python -m scripts.konto_wiederherstellen` setzt Passwort (und optional MFA) auf dem Server zurück, widerruft Sitzungen und schreibt einen Audit-Eintrag.
- **Sichere Voreinstellungen:** die App lehnt Platzhalter-Secrets aus `.env.example` ab; `docker-compose.yml` (nur Entwicklung) bindet Postgres nur an localhost; Domains der Caddy-Konfiguration kommen aus `APP_DOMAIN`/`API_DOMAIN`; `init-secrets.sh` mahnt zur getrennten Schlüsselsicherung.
- **Doku:** `docs/self-hosting.md`, `SECURITY.md`, Abschnitt „Selbst hosten“ in der `README.md`.

## [Unveröffentlicht] - XRechnung-Validierung
- Neu: Prüfung der erzeugten XRechnung gegen XSD und Schematron der KoSIT-XRechnung-Konfiguration (XRechnung 3.0.2,
  Konfiguration 2026-08-31), ausgeführt mit lxml und Saxon (`saxonche==13.1.0`). Geprüft gegen die Konfiguration, nicht
  „KoSIT-zertifiziert"; der Original-Validator läuft nicht mit (siehe `docs/xrechnung-validierung.md`).
- Neu: `backend/scripts/kosit_regeln_holen.py` holt die Regeln von festgeschriebenen Commits per git (Hash- und SHA-256-Prüfung)
  in den ignorierten Ordner `backend/.kosit-regeln`; nichts davon wird im Repository abgelegt.
- Neu: Einstellung `XRECHNUNG_PRUEFUNG` (`aus`, `warnen`, `blockieren`) und `XRECHNUNG_REGELN_DIR`. XML-Download und
  ZUGFeRD-PDF liefern bei `warnen` das Ergebnis in `X-Xrechnung-*`-Headern, bei `blockieren` HTTP 422 statt einer ungültigen
  Datei. Neuer Endpunkt `GET /invoices/{id}/e-rechnung-validierung`.
- Behoben (Generator): falsche CustomizationID, fehlende ProfileID, Käuferreferenz/Leitweg-ID (BT-10), Verkäufer-Kontakt
  (BG-6), elektronische Adressen, Anschrift, Zahlungsmittel (IBAN/BIC), Steuerkategorien mit Befreiungsgrund (§ 19 UStG),
  Skonto-Format, Gutschrift als UBL-CreditNote (381), Steuernummer als Verkäuferkennung, Rundung (kaufmännisch) und
  Zahlendarstellung ohne Exponent.
- Geändert: Die Umsatzsteuer einer Rechnung wird je Steuersatz aus der Summe der gerundeten Positionen berechnet (vorher
  je Position gerundet); Summen können sich dadurch um wenige Cent ändern.
- Neu: Mandantenfelder `telefon` und `kontakt_email` (verschlüsselt, nur Inhaber; Pflicht für die XRechnung, BG-6),
  Migration `0040`. Im Frontend gibt es dafür noch keine Eingabefelder.
- Tests: Generator-Fälle (19 %, 7 %, 0 %, § 19, gemischte Sätze, Storno, Leitweg-ID, Skonto, viele Positionen, Rundung),
  Prüfmodi über die API und die Beispielinstanzen der Regel-Repositories auch gegen die Leseseite; CI-Job
  `xrechnung-validierung`.

## [v0.1.0-beta] - Entwurf, noch nicht veröffentlicht

Erste geschlossene Beta (Stufe 1 laut `docs/release-plan.md`). Die API meldet intern `version="0.1.0"`
(`backend/app/main.py`). Stand der Tests am 14. Oktober 2026: 844 bestanden, 11 übersprungen (SQLite-Lauf), Postgres/RLS-Lauf 855 bestanden, Alembic-Head `0038`.

Bekannte Grenzen des Funktionsumfangs (bewusst, siehe `CLAUDE.md`): XRechnung ist nicht KoSIT-validiert, ZUGFeRD ist
best-effort und nicht Factur-X-zertifiziert, der DATEV-Export ist nicht gegen echtes DATEV getestet, SKR03-Konten sind nicht
steuerberatergeprüft, Mahngebühren sind Platzhalter, die Lohnvorbereitung berechnet weder Lohnsteuer noch Sozialversicherung,
eine Bankanbindung über finAPI gibt es nicht (nur Kontoauszug-Import).

### Fundament, Konten und Mandanten
- Mandanten-/Nutzer-Fundament mit Registrierung, TOTP-MFA, Postgres Row-Level-Security (mit Anwendungs-Fallback für SQLite) und append-only Audit-Log.
- Mehrbenutzer: Einladungscodes, direktes Anlegen von Mitgliedern durch den Owner, Passwortänderung, Rollen `owner` und `mitglied`.
- Lösch- und Anonymisierungsworkflow, DSGVO-Datenexport (Art. 15/20) als Owner-only-JSON.
- Zwei-Faktor-Anmeldung ist jetzt **optional** mit Hinweis-Popup am Dashboard; Deaktivierung nur mit Passwort und aktuellem Code (PR #12).
- „Dieses Gerät 30 Tage merken", zentrales 401-Handling im Frontend, Sitzung bleibt beim Reload erhalten.
- Mandantenkontext korrigiert: `set_config` je Transaktion, Lookup-Funktionen ohne `BYPASSRLS` (Migration 0035), eigenständiger RLS-Testlauf (`backend/scripts/rls_testlauf.sh`), Laufzeitrolle `bilantiq_runtime` (PR #8).

### Rechnungen, Angebote und Dokumente
- Rechnungen inklusive E-Rechnung (XRechnung, ZUGFeRD), Stornierung, Nummernkreise, Gutschriften-Ansicht.
- Wiederkehrende Rechnungen (immer nur Entwürfe), Angebote mit Umwandlung in Rechnung, Auftragsbestätigungen und Lieferscheine (inkl. Teillieferungen).
- Rechnungs-Editor mit Split-Layout und Live-PDF-Vorschau; Produktkatalog; Lagerbestand als manuelle Warenwirtschaft; Rechnungsliste mit Kundennamen.
- Rechnungs-Designer: 11 PDF-Vorlagen, 4 Design-Varianten, Akzentfarbe, Logo, Briefpapier, Sprache De/En, Element-Schalter, GiroCode, Mehrseiten-Paginierung; später neue Drucklayouts (`document_layouts.py`) und echte Vorschauen.
- E-Mail-Versand von Rechnungen, Angeboten und Mahnungen mit PDF-Anhang (stdlib `smtplib`, STARTTLS).
- Online-Zahllink für Rechnungen über Stripe Checkout (Zahlung nur nach signiertem, idempotentem Webhook).
- Dreistufiges Mahnwesen mit mandantenweiter Übersicht.

### Belege, Bank und Buchhaltung
- Lokale Belegerfassung mit Tesseract-OCR (keine bezahlte KI-API), Confidence-Werte und „[UNKLAR]"-Schwelle; Kamera-Aufnahme im Beleg-Upload; Beleg löschen (nicht für gebuchte Belege).
- Ausgaben mit Zahlungsdatum und gemischten USt-Anteilen (0/7/19 %), Originalbeleg-Vorschau; EÜR, Dashboard, Cashflow, UStVA, DATEV und DSGVO-Export berücksichtigen beides.
- Gemeinsamer Erfassungsweg für Belege (Dateityp aus dem Inhalt, Größenlimit, sicherer XML-Leser), Kategorien lernen, E-Rechnungen (XRechnung, ZUGFeRD) empfangen und exakt lesen.
- Kontoauszug-Import (CAMT.053, CSV) mit Zuordnungsvorschlägen, nur auf Bestätigung (Pro/Business).
- Auswertungen: EÜR, UStVA, SuSa, BWA (vereinfacht), Cashflow-Prognose (8 Wochen, deterministisch), Dashboard-Kennzahlen, DATEV-Export (EXTF-CSV, SKR03), KI-Buchungsvorschläge mit Begründung.
- Sonstige Einnahmen, Buchhaltungsvorgaben, Kassenbuch, Anlagenverwaltung mit linearer AfA (fließt in die Auswertungen ein), wiederkehrende Ausgaben.
- Lohnvorbereitung: verschlüsselte Mitarbeiterstammdaten, Monatsentwürfe mit Korrektur-Workflow, Lohnzettel-PDF, CSV-Arbeitsdatei. Keine Lohnabrechnung.
- Steuerberater-Kontakt mit Auswertungs-Kurzwahl.

### Datenumzug und Suche
- Kontakte als Kunde, Lieferant oder beide, mit Ansprechpartner, IBAN, Zahlungsziel/Skonto und Leitweg-ID.
- Import und Export von Kontakten und Produkten (CSV, Excel) mit Spaltenzuordnung, Probelauf und Rückgängig.
- Volltextsuche `POST /suche` und Befehlspalette (Strg+K).
- Rechnungen aus dem alten Programm (Import, verschlüsseltes PDF-Archiv, Zahlungen), Umzugsassistent, Nummernkreis fortsetzen.

### KI (lokal)
- Lokale KI-Grundschicht (`app/ai`), standardmäßig deaktiviert, kein externer Cloud-Fallback: Assistent (Lesen), Rechnungs- und Angebotsentwürfe zur Prüfung im Editor, Textvorschläge für Versand und Mahnungen. Das Modell hat keinen Datenbankzugriff.

### Tarife und Billing
- Premium-Tarife Free/Pro/Business mit zentralen Quoten (Free: 5 Rechnungen, 10 Belege pro Monat, 1 Nutzer), Stripe Checkout und Kundenportal (Owner-only), signierte und idempotente Webhooks, atomare Quotenprüfung, Upgrade-Hinweise im Frontend.

### Sicherheit und Datenschutz
- Envelope-Verschlüsselung (AES-256-GCM, zufälliger Datenschlüssel je Wert/Datei, versionierter Schlüsselbund) für Stamm-, Kontakt-, Finanz-, Lohn- und Freitextdaten sowie Beleg-, Logo-, Briefpapier-, Kontoauszug- und Altrechnungs-Dateien; HMAC-Blind-Indizes für Suche und Duplikaterkennung.
- Argon2id statt bcrypt (alte Hashes werden beim nächsten Login ersetzt), serverseitig widerrufbare Sitzungen mit `security_version`, verifizierter E-Mail-Wechsel, MFA-Neueinrichtung, Seite „Sicherheit & Datenschutz".
- Migration 0036 (PR #10): verschlüsselte Spalten als TEXT (nicht umkehrbar), Schlüsselrotation (`scripts/rotate_encryption.py`) mit Prüfmodus; auf Postgres bleibt der Audit-Log wegen des Append-only-Triggers beim alten Key.
- Migration 0038: **TOTP-Replay-Schutz** (ein Code pro Konto nur einmal verwendbar), **MFA-Wiederherstellungscodes** (10 Einmalcodes, einmal sichtbar, nur als Hash gespeichert, Anmeldung per Code, Neu-Erzeugen mit Passwort und Code) und **„Passwort vergessen“** per E-Mail-Link (Einmal-Token 256 Bit, 60 Minuten, keine Konto-Enumeration, beendet alle Sitzungen, MFA bleibt aktiv). Neue Einstellung `APP_FRONTEND_URL` (ohne Default). Der Mailversand ist nur gegen Attrappen getestet.
- Storage gegen Path Traversal gehärtet (Rechte 0700/0600), Upload-Härtung, Security-Header und Host-Header-Schutz, `Cache-Control: no-store` für API-Antworten.

### Betrieb und Deployment
- Produktions-Stack mit Docker Compose (PostgreSQL im internen Netz, Backend read-only ohne Capabilities, Caddy mit automatischem TLS), Docker-Secrets (`scripts/init-secrets.sh`).
- Backups nur noch `age`-verschlüsselt im Stream (`scripts/backup.sh`), Restore nur mit expliziter Identity (`scripts/restore.sh`).
- CI für Backend (Python 3.14, ephemere Test-Secrets) und Frontend.
- Dokumentation: Release-Plan, Produktions-Sicherheitsbaseline, Server-Rollout für 0035/0036, Betriebs-Runbook, Incident-Plan, Entwurf Art. 30/TOMs.

### Oberfläche und Branding
- Bilantiq-Branding 2026 (Waldgrün, Limette, Papier; lokale Schriften Manrope und IBM Plex Sans, keine Google-Font-Anfragen), altes Petrol-Branding entfernt (PR #9).
- Desktop-Layout ab 1024 px mit Sidebar, Dashboard-Neubau mit Schnellzugriff und Diagrammen, Seite „Erste Schritte", KI-Chat-Oberfläche, formatierte Tabellen, Auswahl-/Belegprüfungs-Fixes.
- PWA-Grundlage (Manifest, Service Worker nur für die App-Hülle, Install-Hinweis); öffentliche Website (`website/`, Next.js) mit App-Einstieg per `?ansicht=anmelden` bzw. `?ansicht=registrieren`.
- Produkt-Disclaimer sichtbar (keine Steuerberatung, genannte Grenzen).

### Behobene Fehler (Auswahl)
- Sitzung ging bei jedem Reload verloren; MFA-Code wurde trotz richtiger Eingabe abgelehnt; Validierungsfehler zeigten nur „Etwas ist schiefgelaufen".
- Rechnungsvorschau: Fehler statt Hinweis bei leerer Positionsbeschreibung, mandantenfremde Kontaktpersonen gesperrt, Design-Tab im Free-Tarif unbenutzbar, Tabellenkopf-Kollision bei schmalen Vorlagen.
- Login, Migrationskette und doppelter Import auf `main` repariert; Schlüsselrotation ließ 42 verschlüsselte Spalten aus (jetzt aus den Modellen abgeleitet).
- Sortierung nach Ciphertext (Kontakte, Einnahmen, Produkte, Briefpapier) auf Sortierung nach Entschlüsselung umgestellt.

### Offen vor dem Release
Siehe `docs/release-plan.md`: Restore-Test, Migrationen 0035/0036 und Laufzeitrolle auf Staging/Produktion, echte Secrets, Rechtstexte, Browser-Abnahme, externer Sicherheitstest, Entscheidung zur MFA-Politik.
