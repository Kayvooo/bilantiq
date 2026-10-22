# Bilantiq: Entwurf Verzeichnis der Verarbeitungstätigkeiten (Art. 30) und TOM-Beschreibung (Art. 32)

Stand: 14. Oktober 2026. **ENTWURF zur Prüfung durch eine Datenschutz-Fachperson**.

> **Was dieses Dokument ist und was nicht.** Es beschreibt ausschließlich die **technische Seite**,
> abgeleitet aus dem Code (`backend/app`, Migrationen), `docker-compose.prod.yml`, `Caddyfile`, den Skripten und
> `docs/security-production.md`. Es enthält **keine Rechtstexte**: keine Rechtsgrundlagen, keine
> Löschfristen, keine Einwilligungs- oder Informationstexte. Diese Felder sind mit
> `[von Fachperson auszufüllen]` markiert. Es ist keine Rechtsberatung und keine Zertifizierung. Wo etwas nicht
> umgesetzt oder nicht verifiziert ist, steht es unter „Lücke/offen“.

## 0. Verantwortlichkeiten

| Verarbeitung | Rolle von Bilantiq | Folge |
| --- | --- | --- |
| Buchhaltungsdaten der Kunden (Rechnungen, Belege, Kontakte, Lohnvorbereitung, Bankimport) | Voraussichtlich **Auftragsverarbeiter** (Art. 28) für den Kunden als Verantwortlichen | Verzeichnis nach **Art. 30 Abs. 2** (Teil B), AV-Vertrag |
| Nutzerkonten, Betrieb/Sicherheit/Logs, Website | **Verantwortlicher** | Verzeichnis nach **Art. 30 Abs. 1** (Teil A) |

Die rechtliche Einordnung der Rollen ist zu bestätigen `[von Fachperson auszufüllen]`.

Verantwortlicher / Anbieter: `[Name, Anschrift, Kontakt]` · Vertreter: `[ ]` · Datenschutzbeauftragte(r): `[ ]`

## 1. Systemübersicht (technische Grundlage)

```
Browser/PWA --HTTPS--> Caddy (<domain>, api.<domain>, Let's Encrypt) --> Backend (FastAPI/uvicorn)
                                                                                |--> PostgreSQL (nur internes Docker-Netz)
                                                                                |--> Volume /app/data (Belege, Logos, Briefpapier, Bank, Altrechnungen; verschlüsselt)
                                                                                |--> SMTP-Anbieter (E-Mail-Versand)
                                                                                |--> optional lokaler KI-Dienst (AI_ENABLED, Standard aus)
Backup: scripts/backup.sh -> age-verschlüsselt -> lokal + OFFSITE_TARGET
```

Mandantenmodell: `mandanten` (Firma), `users`, `mitgliedschaften` (Rolle `owner` oder `mitglied`). Alle fachlichen Tabellen
tragen `mandant_id`.

## 2. Teil A: Verarbeitungstätigkeiten als Verantwortlicher (Art. 30 Abs. 1)

Spalten „Zweck“, „Rechtsgrundlage“, „Speicherdauer“ sind rechtliche Angaben und bleiben leer.

### A1 Nutzerkonto und Anmeldung

| Feld | Eintrag |
| --- | --- |
| Betroffene | Nutzer (Inhaber und Mitglieder von Kundenfirmen) |
| Datenkategorien | Login-E-Mail (verschlüsselt, plus HMAC-Lookup `email_lookup_hash`), Passwort als Argon2id-Hash, optional TOTP-Secret (verschlüsselt), Fehlversuchszähler/Sperrzeit, Sicherheitsversion, Zeitstempel (erstellt, Passwort/E-Mail geändert, gelöscht), Sitzungen (`auth_sessions`: Nutzer, Mandant, User-Agent verschlüsselt, Erstellung/Ablauf/Widerruf), ausstehende E-Mail-Änderung (neue E-Mail verschlüsselt, Code-Hash), letzter verbrauchter TOTP-Zeitschritt, MFA-Wiederherstellungscodes (nur HMAC-Hashes, `mfa_wiederherstellungscodes`), Passwort-Reset-Tokens (nur HMAC-Hash, 60 Minuten gültig, `passwort_reset_tokens`) |
| Zweck / Rechtsgrundlage / Speicherdauer | `[von Fachperson auszufüllen]` |
| Empfänger | SMTP-Anbieter (Bestätigungscode bei E-Mail-Änderung, Passwort-Reset-Link, Benachrichtigung „Passwort geändert“), Hoster |
| Drittland | `[prüfen: Hoster-Region, SMTP-Anbieter]` |
| Technische Besonderheiten | Löschung = Anonymisierung (`DELETE /auth/me`): E-Mail wird durch Marker ersetzt, Passwort unbrauchbar, MFA-Secret entfernt; Zeile bleibt wegen Buchungsbezug. `[Lücke: Wiederherstellungscode- und Reset-Token-Hashes des Nutzers werden dabei noch nicht gelöscht; sie sind ohne Konto nutzlos, sollten aber mitgelöscht werden]` |

### A2 Audit-Log (Sicherheits- und Nachweisprotokoll)

| Feld | Eintrag |
| --- | --- |
| Betroffene | Nutzer |
| Datenkategorien | Mandant-ID, Nutzer-ID, Aktionsname, Zeitpunkt, Kontext (AES-GCM-verschlüsselt). Keine IP-Adresse. |
| Zweck / Rechtsgrundlage / Speicherdauer | `[von Fachperson auszufüllen]` |
| Technische Besonderheiten | Append-only (Anwendungs-Hook und Postgres-Trigger, Laufzeitrolle ohne UPDATE/DELETE). Eine Löschung einzelner Einträge ist technisch nicht vorgesehen. Das ist mit Löschwünschen abzuwägen `[von Fachperson]`. |

### A4 Betrieb, Fehlersuche, Logs

| Feld | Eintrag |
| --- | --- |
| Betroffene | Besucher und Nutzer |
| Datenkategorien | IP-Adresse, Zeit, HTTP-Methode, Pfad inkl. Query-String, Status (uvicorn-Zugriffszeilen im Container-Log), Tracebacks. Caddy-Zugriffslogs sind im aktuellen `Caddyfile` nicht aktiviert. Postgres-Serverlog (ohne Statements). Siehe `docs/betrieb-runbook.md`, Abschnitt 2. |
| Besonderheit | Vorschau-Endpunkt nimmt IBAN/BIC als Query-Parameter. Logs sind wie Zugangsdaten zu schützen. |
| Zweck / Rechtsgrundlage / Speicherdauer | `[von Fachperson auszufüllen]` (Vorschlag technisch: 30 Tage, Rotation noch nicht im Repo eingerichtet) |

### A5 Website und Support

Eine Website oder ein Support-Postfach gehört nicht zur Software, sondern zu Ihrem Betrieb. Angaben dazu
`[von Betreiber bzw. Fachperson auszufüllen]`.

### A6 Kundenkommunikation per E-Mail

Versand von Rechnungen, Angeboten, Mahnungen im Auftrag des Kunden: siehe Teil B (B5). Systemmails (z. B.
E-Mail-Änderung) sind eigene Verarbeitung von Bilantiq (A1).

## 3. Teil B: Verarbeitungstätigkeiten als Auftragsverarbeiter (Art. 30 Abs. 2)

Gilt je Kunde als Verantwortlichem. Die Verarbeitungen sind für alle Kunden gleich aufgebaut.

Angaben je Eintrag: Name/Kontakt des Verantwortlichen (der jeweilige Kunde): `[je Kunde]`; Kategorien der Verarbeitung; Drittland-
übermittlung; allgemeine Beschreibung der TOM (Abschnitt 4).

| Nr. | Verarbeitung (Modul) | Betroffene (beim Kunden) | Datenkategorien (Tabellen) | Verschlüsselung am Feld |
| --- | --- | --- | --- | --- |
| B1 | Stammdaten Firma (`mandanten`) | Inhaber, ggf. Steuerberater-Kontakt | Firmenname, Adresse, USt-ID, Steuernummer, IBAN/BIC, DATEV-Nummern, Steuerberater-Name/E-Mail/Telefon, Rechnungsdesign-Einstellungen | Ja (Firmen-, Steuer-, Bank-, Berater-Felder) |
| B2 | Kontakte (`kontakte`) | Kunden, Lieferanten, Ansprechpartner | Name, Anrede, Vor-/Nachname, Anschrift, E-Mail, Telefon, USt-ID, Steuernummer, IBAN (+ Blind-Index `iban_hash`), BIC, Leitweg-ID, Kundennummer, Notiz | Ja, Freitexte und Stammfelder |
| B3 | Rechnungen, Angebote, Aufträge, Lieferscheine, Mahnungen, wiederkehrende Rechnungen | Rechnungsempfänger | Beträge, Mengen, Positionstexte, Betreff/Kopf-/Fußtext, Referenz, Kostenstelle, Rechnungsnummer (strukturiert), Daten, Status, Versandzeitpunkt | Beträge und Texte ja; Nummern/Daten/Status strukturiert |
| B4 | Belege und Ausgaben (`receipts`, `ausgaben`, Dateien) | Lieferanten, ggf. Dritte auf Belegen | Hochgeladene Belegdatei (Bild/PDF/XML), per lokalem OCR erkannte Felder (Anbieter, Betrag, IBAN, Rechnungsnummer, Begründung, E-Rechnungsdaten), Kategorie, USt-Aufteilung, Zahlungsdatum | Felder ja; Datei AES-GCM im Volume |
| B5 | E-Mail-Versand (Rechnungen/Angebote/Mahnungen) | Rechnungsempfänger | Empfängeradresse, Betreff, Text, PDF-Anhang; Versandzeitpunkt wird gespeichert | Übertragung via SMTP mit STARTTLS (`app/core/mailer.py`), Inhalt beim Anbieter nicht von Bilantiq verschlüsselt |
| B6 | Bankimport (`bankkonten`, `bankimporte`, `bankumsaetze`, Dateien) | Kontoinhaber, Zahlungspartner | Kontoauszugsdatei (CAMT.053/CSV), Beträge, Gegenpartei-Name und -IBAN, Verwendungszweck, End-to-End-ID, Zuordnungen | Felder und Datei ja |
| B7 | Lohnvorbereitung (`mitarbeitende`, `lohn_monatsentwuerfe`) | Mitarbeitende des Kunden | Vor-/Nachname, Personalnummer, Eintritts-/Austrittsdatum, Monatsbrutto, Zuschläge, Erstattungen, Abzüge, Summen. **Keine** Steuer-ID, kein Geburtsdatum, keine Sozialversicherungsdaten (keine Lohnabrechnung) | Namen und Beträge ja; Personalnummer und Datumsfelder strukturiert |
| B8 | Kassenbuch, sonstige Einnahmen, Anlagen, Lager, Produkte | Geschäftspartner (indirekt) | Bezeichnungen, Beträge, Mengen, Gründe | Ja |
| B9 | Altrechnungen (Import, PDF-Archiv) | Rechnungsempfänger | Nummer, Beträge, Zahlungen, PDF-Dateien | Felder ja, Dateien AES-GCM |
| B10 | Datenimporte/-exporte (Kontakte/Produkte CSV/XLSX, Datenexport Art. 15/20) | wie B2 | Import-Dateiname, Zuordnungen; Export als JSON (Owner-only, protokolliert) | Import-Dateiname ja |
| B12 | Lokale KI-Funktionen (`app/ai`, optional) | wie B3 | Ausschnitte der Mandantendaten werden **nur an den konfigurierten lokalen Inference-Endpunkt** gesendet; kein externer Cloud-Fallback; standardmäßig deaktiviert (`AI_ENABLED=false`) | Transport nach Betreiberkonfiguration (`AI_BASE_URL`) |
| B13 | Audit-Log / Sicherheitsprotokoll je Mandant | Nutzer | siehe A2 | Kontext ja |
| B14 | Backup | alle obigen | Verschlüsselter Dump der Datenbank und des Upload-Volumes | `age`, getrennt vom Schlüsselmaterial |

**Empfänger / Unterauftragsverarbeiter (zu prüfen und zu vertraglich zu regeln):**

| Dienst | Zweck | Welche Daten | Status |
| --- | --- | --- | --- |
| Hoster `[Anbieter, Region]` | Server, Netz | alle (auf Datenträger-/App-Ebene verschlüsselt, siehe TOM) | `[von Fachperson / Owner auszufüllen]` |
| Backup-Speicher `[Anbieter]` | Off-site-Kopie | nur `age`-verschlüsselte Dateien | `[ ]` |
| SMTP-Anbieter `[Anbieter]` | Versand | Empfänger, Text, PDF | `[ ]` |
| Let's Encrypt (über Caddy) | TLS-Zertifikate | Domainnamen, Server-IP | `[ ]` |
| Lokaler KI-Dienst | optional | siehe B12 | kein Dritter, wenn selbst betrieben |

## 4. TOM-Beschreibung (Art. 32), nach Schutzzielen

Legende: **Umgesetzt** = im Repo vorhanden und (soweit angegeben) durch Tests abgedeckt. **Betrieb** = muss auf
dem Server eingerichtet werden, im Repo nur als Vorgabe. **Lücke** = nicht vorhanden oder nicht verifiziert.
Test-Hinweis: Die Backend-Tests laufen auf SQLite; Postgres-RLS-Tests (`tests/test_rls_postgres.py`) werden
ohne Postgres übersprungen (`backend/scripts/rls_testlauf.sh`).

### 4.1 Vertraulichkeit

| Maßnahme | Beschreibung | Beleg | Status |
| --- | --- | --- | --- |
| Zutrittskontrolle | Liegt beim Hoster/Rechenzentrum (nicht im Repo). | Hoster-Nachweise | Betrieb `[Nachweis vom Hoster einholen]` |
| Zugangskontrolle Server | Root-Login aus, nur SSH-Schlüssel, Firewall nur 22/80/443, SSH möglichst auf Admin-IP/VPN, Updates automatisch, Volume-Verschlüsselung | `security-production.md` §1 | Betrieb |
| Zugangskontrolle Anwendung | Passwort mindestens 12 Zeichen, Argon2id, Konto-Sperre nach 5 Fehlversuchen für 15 Minuten, optionale TOTP-MFA (Codes nur einmal verwendbar, Replay-Schutz; 10 Wiederherstellungscodes als Hash; Deaktivierung nur mit Passwort und aktuellem Code, danach Sitzungen widerrufen), Passwort-Reset per Einmal-Link (256 Bit, 60 Minuten, nur Hash gespeichert, keine Konto-Enumeration, beendet alle Sitzungen), Zugriffstoken 30 Minuten, „Gerät merken“ bis 30 Tage (widerrufbar), Sitzungen serverseitig widerrufbar | `app/core/security.py`, `app/config.py`, `app/security/routes.py` | Umgesetzt. **Lücke:** MFA ist freiwillig (Entscheidung E4 offen). Kein Schutz pro IP/Rate-Limit außer der Konto-Sperre. Passwort-Reset per E-Mail ist vorhanden (nur gegen Attrappen getestet); kein automatischer Weg zurück, wenn Gerät und Wiederherstellungscodes fehlen (Support-Prozess offen). |
| Zugriffskontrolle (Berechtigungen) | Rollen `owner` / `mitglied`; Owner-only-Routen prüfen die aktuelle Mitgliedschaft aus der Datenbank, nicht aus dem Token; entfernte Nutzer verlieren beim nächsten Request den Zugriff | `app/auth/dependencies.py`, Tests | Umgesetzt; Stichprobenprüfung aller Routen steht aus |
| Mandantentrennung | Doppelt: expliziter `mandant_id`-Filter in der Anwendung (`app/core/rls.py`) und Postgres Row-Level-Security mit `app.current_mandant_id` je Transaktion; Laufzeitrolle `bilantiq_runtime` ohne Superuser und ohne `BYPASSRLS`; wenige `SECURITY DEFINER`-Lookups (Einladungscode, Login) | `docs/specs/rls-postgres.md`, `docs/server-rollout.md`, `backend/scripts/runtime_rolle.sql`, Migration 0035 | Umgesetzt im Code. **Betrieb/Lücke:** Wirksamkeit setzt voraus, dass die App wirklich mit der Laufzeitrolle verbindet; SQLite (nur Entwicklung) hat nur die Anwendungsebene. |
| Verschlüsselung gespeicherter Daten | AES-256-GCM Envelope Encryption: zufälliger Datenschlüssel je Wert und Datei, durch versionierten Schlüsselbund (KEK) gewrappt; sensible Stamm-, Kontakt-, Rechnungs-, Beleg-, Bank-, Lohn-Felder, Beträge und Audit-Kontext; Belege, Logos, Briefpapier, Kontoauszüge, Altrechnungen als verschlüsselte Dateien; Dateiablage mit Pfadprüfung und Rechten 0700/0600 | `app/core/key_management.py`, `encrypted_types.py`, `secure_storage.py`, Migrationen 0029, 0036; Liste der Spalten per `scripts/rotate_encryption.py` aus den Modellen | Umgesetzt. **Grenzen:** Datums-, Status-, ID- und Nummernfelder sind aus Gründen der Auswertung unverschlüsselt (u. a. Personalnummer, Eintritts-/Austrittsdatum, Rechnungsnummer). Schlüssel liegen auf demselben Host (Docker-Secrets), ein Angreifer mit Root auf dem laufenden Host erreicht Klartext. Kein HSM/KMS. |
| Verschlüsselung bei Übertragung | HTTPS mit automatischen Let's-Encrypt-Zertifikaten durch Caddy, HSTS, HTTP→HTTPS; SMTP mit STARTTLS | `Caddyfile`, `app/core/mailer.py` | Umgesetzt; TLS-Konfiguration auf der echten Domain noch prüfen |
| Pseudonymisierung/Blind-Index | Suchbare Felder (IBAN, Umsatzduplikate, Altrechnungsnummern, E-Mail) über HMAC-Hashes statt Klartext | `key_management.blind_index`, `crypto.lookup_hash` | Umgesetzt |
| Secrets-Management | Produktionssecrets als Docker-Secrets unter `/run/secrets` (0600/0700, root), nicht in `.env.prod`, Git oder Image; Skript `init-secrets.sh` | `docker-compose.prod.yml`, `scripts/init-secrets.sh` | Umgesetzt; echte Werte/Offline-Sicherung = Betrieb |
| Container-Härtung | PostgreSQL nur im internen Netz, Caddy ohne DB-Zugriff, Backend read-only mit schreibbarem `/app/data` und `/tmp` (tmpfs, `noexec`), `no-new-privileges`, alle Capabilities entfernt, Backend läuft als Nutzer `app` (UID 1000) | `docker-compose.prod.yml`, `backend/Dockerfile` | Umgesetzt (Compose-Datei geprüft, nicht auf echtem Server ausgeführt) |
| Web-Sicherheitsheader | Backend: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, restriktive CSP für JSON-Antworten, HSTS über HTTPS, `Permissions-Policy`; Caddy: HSTS, CSP für die SPA, Server-Header entfernt; Host-Header-Schutz (`TRUSTED_HOSTS_RAW`); CORS nur eigene Origins | `app/main.py`, `Caddyfile`, `app/config.py` | Umgesetzt; CSP nach erstem Deploy im Browser prüfen (Kommentar im `Caddyfile`) |
| Upload-Sicherheit | Dateityp aus dem Inhalt statt Client-Header, Größenlimits (Beleg 15 MB, Bank/Import 10 MB, Briefpapier 5 MB), sicherer XML-Parser gegen XXE (`xml_safe`), Pfad-Traversal-Schutz | `app/receipts/service.py`, `app/core/xml_safe.py`, `app/core/secure_storage.py` | Umgesetzt; externer Test steht aus |
| Trennung von Zwecken | Mandantenweit getrennte Daten; Test-/Entwicklungsdaten getrennt (SQLite lokal, CI mit ephemeren Secrets) | `.github/workflows`, `backend/tests/conftest.py` | Umgesetzt; Staging fehlt |

### 4.2 Integrität

| Maßnahme | Beschreibung | Beleg | Status |
| --- | --- | --- | --- |
| Weitergabekontrolle | Auslieferung nur über HTTPS; Datenexport nur durch Owner und im Audit-Log; Dateien werden nur über authentifizierte Routen mit Mandantenprüfung ausgeliefert | `app/auth/routes.py` (`datenexport`), `app/receipts/routes.py` | Umgesetzt |
| Eingabekontrolle / Protokollierung | Append-only-Audit-Log (Anwendungs-Hook, Postgres-Trigger, entzogene Rechte der Laufzeitrolle) für Anmeldungen, MFA, Passwort, Mitglieder, Exporte, Rechnungs-/Beleg-/Bank-/Lohnaktionen, Webhooks | `app/core/audit_log.py`, Migration 0001, `runtime_rolle.sql` | Umgesetzt. **Lücke:** keine IP-Adresse, keine Protokollierung reiner Lesezugriffe. |
| Revisionssicherheit Buchhaltung | Finalisierte Rechnungen unveränderlich (Storno statt Ändern), Kassenbuch und Lagerbewegungen als Gegenbuchung, Altrechnungs-PDFs unveränderbar | Fachmodule | Umgesetzt; GoBD-Konformität ist keine Zertifizierung |
| Manipulationsschutz Verschlüsselung | AES-GCM mit AAD (Zweck/Key-ID) erkennt Manipulation | `key_management.py`, Tests | Umgesetzt |
| Abhängigkeitskontrolle | Versionen gepinnt, CI baut Backend und Frontend | `requirements*.txt`, `.github/workflows` | Teilweise. **Lücke:** `pip-audit`/`npm audit` und `gitleaks` noch nicht ausgeführt. |

### 4.3 Verfügbarkeit und Belastbarkeit

| Maßnahme | Beschreibung | Beleg | Status |
| --- | --- | --- | --- |
| Backup | Täglicher `pg_dump` und Upload-Volume, direkt mit `age` verschlüsselt (kein Klartext auf Platte), lokale Aufbewahrung 14 Tage, Off-site per rsync, unverschlüsselte Backups technisch ausgeschlossen | `scripts/backup.sh` | Skript vorhanden. **Betrieb/Lücke:** noch nicht auf einem Server ausgeführt; Off-site-Ziel und Cron einzurichten. |
| Wiederherstellung | `scripts/restore.sh` mit expliziter privater `age`-Identity und Bestätigung; Upload-Volume manuell | `scripts/restore.sh`, `docs/betrieb-runbook.md` | **Lücke:** Restore noch nie real getestet (Release-Blocker 1). Wiederherstellungszeit und RPO nicht gemessen. |
| Schlüsselverlust | Verlust aller aktiven `DATA_ENCRYPTION_KEYS` heißt Datenverlust; Key-Dateien getrennt vom Datenbackup und offline zu sichern; Schlüsselrotation mit Prüfmodus | `security-production.md` §2, `scripts/rotate_encryption.py` | Umgesetzt (Skript). **Grenze:** Audit-Log bleibt auf Postgres beim alten Key. Rotation auf Staging noch nicht geübt. |
| Wiederherstellbarkeit der Migration | `alembic upgrade head` beim Start; Rückweg über Backup (`downgrade()` von 0036 absichtlich nicht implementiert) | `docs/server-rollout.md` | Umgesetzt |
| Monitoring/Alarmierung | Gesundheitsendpunkt `/health`; Container-Neustart `unless-stopped`; Postgres-Healthcheck | `docker-compose.prod.yml`, `app/main.py` | **Lücke:** Monitoring und Alarm noch nicht eingerichtet. |
| Störungsfestigkeit | Rechnungsnummern und Einladungseinlösung atomar gegen Parallelzugriffe (Zeilensperre pro Mandant) | Tests | Umgesetzt; Lasttest steht aus (Phase 5) |
| Updates | Sicherheitsupdates Host automatisch; Images neu bauen | Vorgabe | Betrieb |

### 4.4 Verfahren zur regelmäßigen Überprüfung, Bewertung und Evaluierung (Art. 32 Abs. 1 lit. d)

| Maßnahme | Status |
| --- | --- |
| Automatisierte Tests (Backend `pytest`, Frontend `tsc`/`oxlint`/Build) in CI | Umgesetzt (Teststand siehe CLAUDE.md) |
| Postgres-RLS-Nachweis mit zwei Mandanten über die Laufzeitrolle | Testskript vorhanden, Lauf auf Staging/Produktion steht aus |
| Restore-Test (quartalsweise vorgeschlagen), Rotationsübung, Incident-Übung | Plan in `docs/betrieb-runbook.md`, `docs/incident-response.md`; noch nicht durchgeführt |
| Externer Scan/Pentest, Security-Review der Auth-Pfade | Offen |
| Rollen- und Benutzerreview, Entfernen nicht benötigter Konten | Vorgabe, nicht automatisiert |

### 4.5 Auftragskontrolle und Datenschutz durch Technikgestaltung

| Maßnahme | Beschreibung | Status |
| --- | --- | --- |
| AV-Verträge mit Unterauftragnehmern | Hoster, SMTP, Backup-Speicher | Offen `[Owner / Fachperson]` |
| Anweisungsgebundene Verarbeitung | Bilantiq verarbeitet Kundendaten nur über die App-Funktionen; kein Zugriff durch Mitarbeiter von Bilantiq außer Administratoren des Betriebs | Organisatorisch festlegen `[ ]` |
| Betroffenenrechte technisch | Auskunft/Übertragbarkeit: Owner-Export (`GET /auth/datenexport`, JSON, ohne Passwort-Hashes und MFA-Secrets); Berichtigung in der App; Löschung als Anonymisierung des Nutzers, Buchungsdaten bleiben wegen GoBD/§ 147 AO; Datenexport/Import von Kontakten und Produkten (CSV/XLSX) | Umgesetzt; Löschkonzept und Mandanten-Komplettlöschung bei Vertragsende **nicht** im Code `[Lücke]` |
| Datenminimierung | Lohnvorbereitung ohne Steuer-ID/Geburtsdatum/SV-Daten; OCR vollständig lokal (Tesseract), keine externe KI-API; KI-Funktionen optional und lokal | Umgesetzt |
| Standard-Voreinstellungen | MFA-Hinweis-Popup im Dashboard, aber MFA nicht erzwungen; KI aus | Umgesetzt (MFA-Pflicht ist offene Entscheidung E4) |
| Meldeprozess für Datenpannen | `docs/incident-response.md` | Entwurf (Fristen/Texte durch Fachperson zu prüfen) |
| Mitarbeiter-Verpflichtung, Schulung, Clean-Desk, Geräteabsicherung | Organisatorische TOMs ohne Repo-Bezug | `[von Owner / Fachperson auszufüllen]` |

## 5. Offene Fragen für die Datenschutz-Fachperson

1. Rollenbestätigung (Auftragsverarbeiter vs. Verantwortlicher) pro Verarbeitung, Inhalt AV-Vertrag.
2. Rechtsgrundlagen, Zwecke und Speicher-/Löschfristen aller Einträge, besonders Audit-Log (append-only) und Zugriffsprotokolle mit IP.
3. Datenschutz-Folgenabschätzung wegen Lohn- und Finanzdaten.
4. Drittlandübermittlung (SMTP-Anbieter, Hoster, Support-Werkzeuge).
5. Mandanten-Komplettlöschung bei Vertragsende und Umgang mit Backups (Aufbewahrung der verschlüsselten Backups).
6. Zugriffe Dritter (Steuerberater des Kunden): aktuell kein eigener Steuerberater-Zugang im Code, nur Export/Kontaktdaten.
7. Verfahren für Betroffenenanfragen gegen Kunden-Daten (Weiterleitung an den Verantwortlichen).

## 6. Pflege

Dieses Dokument bei jeder Änderung an Datenmodellen (neue verschlüsselte Spalten, neue Empfänger), an
`docker-compose.prod.yml`, `Caddyfile` und `security-production.md` mitpflegen. Die Spaltenliste mit
Verschlüsselung lässt sich aus dem Code ableiten (`scripts/rotate_encryption.py`, Funktion `verschluesselte_spalten`).
Prüfdatum: `[ ]`, geprüft von: `[ ]`.
