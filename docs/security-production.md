# Bilantiq Produktions-Sicherheitsbaseline

Stand: 7. Oktober 2026, Abschnitt 4 (MFA) am 14. Oktober 2026 an den Code angepasst

> **Hinweis zum Selbst-Hosting-Modell (22. Oktober 2026):** Bilantiq wird als Open-Source-Projekt veröffentlicht; jede Person
> betreibt ihre eigene Instanz mit eigenem Speicher. Maßgeblich für Einrichtung, Speicher, Registrierung, E-Mail und
> Wiederherstellung ist [self-hosting.md](self-hosting.md). Dieses Dokument bleibt als Härtungs-Checkliste gültig; wo es von
> „dem Betreiber“, einem zentralen Betrieb oder Stripe/Tarifen spricht, stammt das aus der Planung eines gehosteten Dienstes
> und ist für Selbsthoster nicht verbindlich.

Diese Datei beschreibt Mindestanforderungen fuer einen produktiven Bilantiq-Server.
Sie ersetzt kein externes Pentest-/ISMS-Verfahren. „Perfekte Sicherheit“ kann nicht
garantiert werden; Ziel ist Defense in Depth fuer Finanz- und Personaldaten.

## 1. Host

- Dedizierter Linux-Server mit aktivierten Security-Updates.
- Root-Login per SSH deaktivieren; nur Schluessel, kein Passwort-SSH.
- Firewall: extern nur 22 (wenn benoetigt), 80 und 443. PostgreSQL niemals extern.
- SSH nach Moeglichkeit auf Admin-IP/VPN begrenzen.
- Datentraeger/VM-Volume mit LUKS oder gleichwertiger Provider-Verschluesselung.
- Zeit-Synchronisierung aktiv; Audit-/JWT-/TOTP-Funktionen haengen von korrekter Zeit ab.
- Keine Entwicklungsdaten, Dumps oder .env-Backups im Web-/Repo-Verzeichnis.

## 2. Secrets

Produktionssecrets liegen nicht in .env.prod, Git oder Docker-Images.

Initialisierung:

    sudo BILANTIQ_SECRETS_DIR=/opt/bilantiq/secrets ./scripts/init-secrets.sh

Danach:
- Verzeichnis 0700, Dateien 0600. Dateien für API/Migrator gehören für lokale Compose-Bind-Mounts UID 1000; die Admin-URL
  wird nur in den Migrator gemountet. `init-secrets.sh` richtet dies als root ein; siehe `security-runtime.md`.
- smtp_password nur ersetzen, wenn E-Mail genutzt werden soll (SMTP ist optional; der Platzhalter SET_ME bedeutet "aus").
- `database_url` bezeichnet die eigene API-Rolle. `migration_database_url`/`postgres_password` betreffen den separaten
  Administrator. Rotationen der jeweiligen PostgreSQL-Passwörter müssen zur passenden URL synchron erfolgen.
- Backup der Key-Dateien getrennt vom Datenbackup und offline/zugriffsbeschraenkt halten.
- Verlust aller aktiven DATA_ENCRYPTION_KEYS bedeutet Datenverlust; ein alter Key darf
  erst entfernt werden, wenn DB- und Dateirotation erfolgreich verifiziert wurden.

## 3. Application-Level Encryption

- Sensible Stamm-/Kontakt-/Freitextdaten: AES-256-GCM Envelope Encryption. Jeder Wert bzw. jede Datei erhält einen zufälligen 256-Bit-DEK; nur der gewrappte DEK liegt zusammen mit dem Ciphertext vor. Der versionierte KEK-Keyring liegt getrennt als Secret vor.
- Suchbare E-Mail-Adresse: Ciphertext + HMAC-Lookup.
- Bestehende Fernet-Werte bleiben nur als Migrations-Lesepfad erhalten.
- Belege, Logos und Briefpapier werden im Backend-Volume ebenfalls per Envelope-AES-GCM verschluesselt; Storage-Referenzen werden gegen Path Traversal geprüft, Verzeichnisse/Dateien auf 0700/0600 gesetzt.
- Betrags-/Datum-/Steuerspalten bleiben fuer deterministische Reports strukturiert;
  Backups und Datentraeger verschluesseln diese zweite Schutzebene.

Beim Produktionsstart läuft die idempotente Migration automatisch. Manuell kann sie ebenfalls ausgeführt werden:

    cd backend
    python scripts/reencrypt_storage.py

Das Skript ist idempotent.

## 4. Authentifizierung

- Passwortspeicherung: Argon2id.
- Alte bcrypt-Hashes werden beim naechsten erfolgreichen Login automatisch ersetzt.
- MFA/TOTP ist **optional** (seit PR #12). Wer sie nicht eingerichtet hat, bekommt direkt eine volle
  Sitzung (Audit-Eintrag `sitzung_erstellt` mit Kontext `ohne_mfa`); das Dashboard zeigt ein Hinweis-Popup zur
  Einrichtung. Ob MFA für Inhaber oder Konten mit Mitarbeitern erzwungen wird, ist offen.
- MFA deaktivieren geht nur mit aktuellem Passwort **und** aktuellem Code (`POST /security/mfa/deaktivieren`);
  danach werden alle Sitzungen widerrufen und `mfa_deaktiviert` protokolliert.
- **TOTP-Replay-Schutz:** Ein Code ist pro Konto nur einmal verwendbar. Gespeichert wird der letzte verbrauchte
  Zeitschritt (`users.mfa_letzter_zeitschritt`), das Setzen ist ein bedingtes UPDATE (gleichzeitige Anfragen mit
  demselben Code: nur eine gewinnt). Gilt für Anmeldung, Einrichtung, Deaktivieren und Neu-Einrichten. Folge für den
  Betrieb: Wer zweimal innerhalb von 30 Sekunden denselben Code eingibt, wird beim zweiten Mal abgewiesen.
- **MFA-Wiederherstellungscodes:** Bei der ersten Aktivierung entstehen 10 Einmalcodes (`XXXXX-XXXXX`, ca. 50 Bit), die
  genau einmal im Klartext angezeigt werden; in `mfa_wiederherstellungscodes` stehen nur HMAC-Hashes (Schlüssel aus
  `BLIND_INDEX_SECRET`, kontogebunden). Anmeldung per `POST /auth/login/mfa/wiederherstellungscode`, der Code wird
  verbraucht, Fehlversuche zählen im Brute-Force-Zähler. Neu erzeugen nur mit Passwort und aktuellem Code, danach sind alle
  alten Codes ungültig. Wiederherstellungscodes gelten auch als "aktueller Code" beim Deaktivieren/Neu-Einrichten.
  **Grenze:** Hat jemand weder Gerät noch Codes, gibt es keinen automatischen Weg zurück (bewusst: ein E-Mail-Weg würde
  MFA aushebeln). Beim Selbst-Hosting setzt die Person mit Serverzugang MFA über
  `python -m scripts.konto_wiederherstellen --email ... --mfa-zuruecksetzen` zurück (`docs/self-hosting.md`, Abschnitt 7).
- **Passwort vergessen** (`POST /auth/passwort/vergessen`, `/zuruecksetzen`): Antwort immer gleich (202), IP-Limit
  10/h und Konto-Limit 3/h, Antwortzeit auf mindestens 0,4 s aufgefüllt, Mail erst nach der Antwort. Token 256 Bit,
  nur als HMAC gespeichert, einmalig, 60 Minuten, eine neue Anforderung entwertet ältere. Link:
  `<APP_FRONTEND_URL>/#passwort-zuruecksetzen/<nutzer-id>.<token>` (Fragment, damit der Token in keinem Zugriffslog und
  keinem Referer landet). **Ohne eingerichtetes SMTP ist die Route abgeschaltet** und antwortet für alle Adressen gleich mit
  HTTP 503; der Weg für Betreiber ist `backend/scripts/konto_wiederherstellen.py` (siehe `docs/self-hosting.md`). Nach dem Zurücksetzen: alle Sitzungen weg, MFA bleibt aktiv, Benachrichtigungsmail
  "Passwort wurde geändert". **`APP_FRONTEND_URL` muss in `.env.prod` gesetzt sein**, sonst werden keine Reset-Mails
  erzeugt (nur ein Log-Eintrag). Die Mails laufen über denselben SMTP-Zugang wie die E-Mail-Bestätigung; der Versand ist
  bisher nur gegen Attrappen getestet, ein Echttest mit dem Produktions-SMTP steht aus.
- Schutz vor Raten: Konto-Sperre nach 5 Fehlversuchen für 15 Minuten (`failed_login_limit`,
  `failed_login_lock_minutes`) plus IP-Limits für Login, Registrierung, MFA und Reset. IP-Zähler liegen pro Prozess
  im Speicher und müssen vor mehreren Workern/Instanzen gemeinsam geführt werden.
- Full-Access-JWTs sind an eine serverseitige Session und security_version gebunden.
- Passwort-, E-Mail- oder MFA-Aenderung widerruft bestehende Sessions.
- Benutzerentfernung wird bei jedem Request gegen die aktuelle Membership geprueft.

## 5. Netzwerk/Container

docker-compose.prod.yml:
- PostgreSQL nur im internen Docker-Netz.
- Caddy hat keinen DB-Netzzugriff.
- Backend-Dateisystem read-only, nur /app/data und /tmp schreibbar.
- Backend no-new-privileges, Linux-Capabilities entfernt.
- Secrets nur read-only unter /run/secrets.
- Eigener einmaliger Migrationsdienst; API-Startprüfung erzwingt eingeschränkte Laufzeitrechte.

Vor Deployment pruefen:

    docker compose --env-file .env.prod -f docker-compose.prod.yml config

## 6. Backups

Unverschluesselte Produktionsbackups sind durch scripts/backup.sh absichtlich nicht
mehr erlaubt.

Voraussetzungen:
- age installiert.
- BACKUP_AGE_RECIPIENT = Public Key des Backup-Schluessels.
- Private age-Identity NICHT auf demselben Server aufbewahren.
- OFFSITE_TARGET auf getrenntes Storage setzen.

Restore benoetigt explizit BACKUP_AGE_IDENTITY_FILE.

Regelmaessig einen Restore auf einem isolierten Testsystem pruefen. Ein Backup, dessen
Restore nie getestet wurde, gilt nicht als belastbare Wiederherstellungsstrategie.

## 7. Betrieb

Vor jedem Produktionsrelease:
1. CI komplett gruen.
2. alembic upgrade head auf Staging.
3. Backup erstellen und Verschluesselung pruefen.
4. Health-/Login-/MFA-/Rechnung-/Beleg-Smoke-Test.
5. Abhaengigkeits-/Container-Updates pruefen.
6. Audit-Log und fehlgeschlagene Logins auf Auffaelligkeiten kontrollieren.

Regelmaessig:
- externe Schwachstellenanalyse/Pentest,
- Key-Rotation,
- Restore-Test,
- Benutzer-/Rollenreview,
- Entfernen nicht mehr benoetigter Accounts,
- Pruefung von TLS-/Security-Headers und Dependency-CVEs.
