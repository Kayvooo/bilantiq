# Bilantiq selbst hosten

Stand: 22. Oktober 2026. Diese Anleitung gilt für Bilantiq als Open-Source-Projekt.

**Es gibt keinen gehosteten Dienst und keinen zentralen Speicher des Projekts.** Jede Person oder Firma betreibt ihre
eigene Instanz und braucht dafür ihren eigenen Speicher (Datenbank, Belege, Logos, Briefpapier, Kontoauszüge,
Altrechnungs-Archiv, Backups), ihre eigenen Schlüssel und ihren eigenen Server. Das Projekt hat keinen Zugriff auf Ihre
Daten, kann sie nicht wiederherstellen und gibt keine Gewähr (Lizenz und Haftungsausschluss siehe Repository). Wer die
Instanz betreibt, ist selbst zuständig für Betrieb, Sicherheit, Backups, Updates, Aufbewahrung und Datenschutz.
Nichts in dieser Datei ist Steuer- oder Rechtsberatung.

Was in dieser Anleitung geprüft wurde und was nicht, steht am Ende (Abschnitt 14). Bitte lesen Sie ihn, bevor Sie echte
Geschäftsdaten eintragen.

## 1. Voraussetzungen

- Ein Linux-Server (oder VM) mit Docker und dem Compose-Plugin, öffentlich erreichbar auf den Ports 80 und 443, wenn Sie
  die mitgelieferte Caddy-Konfiguration mit automatischem TLS nutzen.
- Zwei DNS-Einträge auf den Server, z. B. `buchhaltung.example.org` (Oberfläche) und `api.buchhaltung.example.org` (API).
- `python3` auf dem Server (für `scripts/init-secrets.sh`) und `age` (für verschlüsselte Backups, Abschnitt 8).
- Optional: ein SMTP-Konto für E-Mail-Versand und „Passwort vergessen“ (Abschnitt 7). Ohne läuft die App trotzdem.

## 2. Schnellstart: private Instanz mit Docker Compose

```bash
git clone <Repository-URL> /opt/bilantiq-app && cd /opt/bilantiq-app

# 1. Konfiguration (keine Geheimnisse hier hinein)
cp .env.prod.example .env.prod
#    Domains (APP_DOMAIN, API_DOMAIN, CORS_ALLOWED_ORIGINS_RAW, TRUSTED_HOSTS_RAW, APP_FRONTEND_URL, VITE_API_BASE_URL)
#    auf die eigenen Adressen setzen. REGISTRATION_MODE=first_account belassen (Abschnitt 6).

# 2. Secrets erzeugen (0700/0600, root). Ausserhalb des Repositories ablegen.
sudo BILANTIQ_SECRETS_DIR=/opt/bilantiq/secrets ./scripts/init-secrets.sh

# 3. Konfiguration prüfen (zeigt Fehler, ohne etwas zu starten)
docker compose --env-file .env.prod -f docker-compose.prod.yml config > /dev/null

# 4. Bauen und starten
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend
```

Zuerst führt der einmalige Dienst `migrate` die Datenbankmigrationen aus und richtet eine eigene eingeschränkte
API-Datenbankrolle ein. Erst danach startet das Backend: Datenbankrechte prüfen, Speicher-Startprüfung (Abschnitt 3),
Verschlüsselung eventuell vorhandener Alt-Dateien, dann der Server. Schlägt ein Schritt fehl, startet die API nicht.
**Bestehende Installationen:** Vor dem ersten Start dieser Version den Umstieg in
[security-runtime.md](security-runtime.md) durchführen. Eine alte Admin-Verbindung wird nicht still überschrieben.

Danach die Oberfläche unter Ihrer `APP_DOMAIN` öffnen und das **erste Konto registrieren**. Das ist der Inhaber der
Instanz. Mit `REGISTRATION_MODE=first_account` ist die Registrierung danach geschlossen (Abschnitt 6). Richten Sie
sofort die Zwei-Faktor-Anmeldung unter „Sicherheit & Datenschutz“ ein und speichern Sie die Wiederherstellungscodes.

Die Dateien `.env.prod` und das Secrets-Verzeichnis dürfen nie in ein Repository, in ein Backup auf demselben
Speicherort oder in Chats gelangen. Es gibt keine mitgelieferten Beispielschlüssel; `init-secrets.sh` erzeugt zufällige
Werte, und die App verweigert den Start, wenn noch Platzhalter aus `.env.example` eingetragen sind.

## 3. Speicher und Volumes

Alle Daten Ihrer Instanz liegen an genau zwei Orten:

| Was | Wo (Docker Compose) | Inhalt |
| --- | --- | --- |
| Datenbank | Volume `postgres_data` (Postgres 16, nur im internen Docker-Netz, kein Port nach außen) | Mandanten, Konten, Rechnungen, Kontakte, Buchungen, Audit-Log (sensible Felder zusätzlich verschlüsselt) |
| Dateien | Volume `backend_data`, im Container `/app/data` (`STORAGE_DIR`) | Belege, Logos, Briefpapier, Kontoauszüge, Altrechnungs-Archiv (alle AES-256-GCM-verschlüsselt) |

`STORAGE_DIR` ist der einzige Basisordner für Dateien (Standard `./data`, im Docker-Image `/app/data`). Daraus leiten sich
die Unterordner `receipts`, `branding`, `briefpapier`, `bank` und `altrechnungen` ab. Einzelne Unterordner lassen sich
bei Bedarf mit `RECEIPT_STORAGE_DIR`, `BRANDING_STORAGE_DIR`, `LETTERHEAD_STORAGE_DIR`, `BANK_STORAGE_DIR` und
`ALTRECHNUNG_STORAGE_DIR` auf andere Laufwerke legen; das ist nur selten nötig.

**Startprüfung.** Beim Start (und vorab im Docker-Image als `python -m app.core.storage_check`) prüft Bilantiq alle
Speicherordner: Sie werden mit den Rechten 0700 angelegt, es wird mit einer echten Probedatei geschrieben, zu weite
Rechte werden auf 0700 zurückgesetzt (sofern der Prozess Besitzer ist), und es gibt eine Warnung bei weniger als 200 MB
freiem Platz. Ist etwas nicht benutzbar, steht eine lesbare Meldung im Log statt eines Stacktraces, z. B. dass ein Ordner
nicht beschreibbar ist, und die App startet nicht. Dateien selbst werden mit 0600 geschrieben; Pfade werden gegen
Path Traversal geprüft.

**Host-Ordner statt Docker-Volume.** In `docker-compose.prod.yml` lässt sich statt `backend_data:/app/data` ein
Host-Ordner einhängen (z. B. `/srv/bilantiq/daten:/app/data`). Er muss dem Benutzer mit UID 1000 gehören
(`chown 1000:1000`), sonst meldet die Startprüfung, dass nicht geschrieben werden kann.

**Wichtig:** `docker compose down -v` löscht beide Volumes unwiderruflich. Ein Server ohne Backup ist ein
Datenverlust-Risiko (Abschnitt 8).

**SQLite** gibt es nur für Entwicklung und Tests (kein Mandantenschutz auf Datenbankebene, keine Migrationen). Für eine
echte Instanz wird Postgres über Docker Compose verwendet.

**Andere Speicher (S3 o. Ä.):** Nicht gebaut. Die Dateizugriffe laufen im Wesentlichen über wenige Funktionen in
`backend/app/core/secure_storage.py` (`write_encrypted`, `read_encrypted`, Neuverschlüsselung/Rotation). Ein
Objektspeicher-Backend wäre deshalb ein möglicher späterer Schritt. Heute hängen aber noch das Anlegen von Ordnern, das
Löschen von Importdateien (`app/altrechnungen/storage.py`) und die Schlüsselrotation direkt am Dateisystem.

## 4. Secrets und Schlüssel

`scripts/init-secrets.sh` legt unter `BILANTIQ_SECRETS_DIR` (Verzeichnis 0700, Dateien 0600) zufällige Werte an:
`postgres_password`, `migration_database_url`, `database_url`, `jwt_secret`, `field_encryption_key`, `email_lookup_secret`, `blind_index_secret`,
`data_encryption_keys`. Bestehende Dateien werden nie überschrieben. Die Secrets gelangen als Docker-Secrets
read-only nach `/run/secrets` in den Container, nicht in `.env.prod` und nicht in Umgebungsvariablen.

**Schlüsselverlust ist Datenverlust.** Alle sensiblen Datenbankfelder und alle Dateien sind mit dem Schlüsselring
`data_encryption_keys` verschlüsselt. Verlieren Sie diese Datei (und alle Sicherungen davon), sind Belege, Kontakte,
Rechnungsdetails und mehr **unwiederbringlich unlesbar**, auch mit vollständigem Datenbank- und Dateibackup. Ebenso
wichtig sind `email_lookup_secret` und `blind_index_secret` (ohne sie funktionieren Anmeldung per E-Mail und Suche/
Duplikaterkennung nach einem Restore nicht) und `field_encryption_key` (Altbestand).

- Sichern Sie das gesamte Secrets-Verzeichnis **getrennt vom Datenbackup**: z. B. Passwortmanager mit Notfallzugang plus
  ausgedruckt oder auf einem Datenträger im Safe, an mindestens zwei Orten. Nicht in dasselbe Backup-Ziel wie die
  Datenbankdumps.
- Bei einer Schlüsselrotation (`backend/scripts/rotate_encryption.py`, Ablauf in `docs/betrieb-runbook.md`, Abschnitt 4)
  darf ein alter Schlüssel nie entfernt werden, solange Daten ihn noch brauchen. Das Audit-Log bleibt auf Postgres beim
  Schlüssel, mit dem es geschrieben wurde.
- Der private `age`-Schlüssel für Backups gehört nicht auf den Server (Abschnitt 8) und ebenfalls an zwei Orte.

## 5. TLS, Reverse-Proxy, Firewall

- Das mitgelieferte Caddy (im `caddy`-Container) holt automatisch Let's-Encrypt-Zertifikate für `APP_DOMAIN` und
  `API_DOMAIN`, liefert die Oberfläche aus und leitet die API an den internen Backend-Container weiter. Dafür müssen die
  Ports 80 und 443 aus dem Internet erreichbar sein und beide DNS-Einträge auf den Server zeigen.
- Wer einen eigenen Reverse-Proxy betreibt (nginx, Traefik …): Das Backend sollte nie direkt aus dem Internet erreichbar sein,
  der Proxy muss `X-Forwarded-Proto` und `X-Forwarded-For` setzen (das Image vertraut diesen Headern, siehe `backend/Dockerfile`),
  und `TRUSTED_HOSTS_RAW` muss den API-Hostnamen enthalten.
- Firewall: von außen nur 22 (SSH, wenn nötig, am besten auf eine Admin-IP oder ein VPN begrenzt), 80 und 443.
  Postgres ist im Compose-Stack absichtlich nicht veröffentlicht und darf nie von außen erreichbar sein. Beispiel mit ufw:
  `ufw default deny incoming && ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable`. Hinweis:
  Docker umgeht ufw-Regeln für veröffentlichte Ports; vermeiden Sie deshalb zusätzliche `ports:`-Einträge und prüfen
  Sie von außen, was wirklich erreichbar ist (z. B. `nmap` von einem anderen Rechner).
- Weitere Host-Härtung (SSH nur mit Schlüssel, automatische Sicherheitsupdates, Datenträgerverschlüsselung):
  `docs/security-production.md`, Abschnitt 1.
- Die interaktive API-Dokumentation (`/docs`) ist standardmäßig aus (`API_DOCS_AKTIV=false`). Lassen Sie sie aus.

## 6. Registrierung: wer darf ein Konto anlegen?

Eine öffentlich erreichbare Privatinstanz mit offener Registrierung lässt jede fremde Person ein Konto (und damit eine
eigene Firma auf Ihrem Server, Ihrem Speicher und, falls eingerichtet, über Ihren SMTP-Zugang) anlegen. Deshalb ist der
Standard restriktiv. `REGISTRATION_MODE` in `.env.prod`:

| Wert | Wirkung | Empfehlung |
| --- | --- | --- |
| `first_account` (Standard) | Nur das allererste Konto der Instanz darf sich selbst registrieren und legt die Firma an. Weitere Personen treten nur mit einem Einladungscode des Inhabers bei, den der Inhaber unter „Benutzer“ erzeugt, oder werden vom Inhaber direkt angelegt. Als „vorhanden“ zählt jedes jemals angelegte Konto, ein gelöschtes Erstkonto öffnet die Registrierung nicht wieder. | Für eine Firma oder Familie: so belassen |
| `closed` | Keine Selbstregistrierung, auch nicht per Einladungscode. Der Inhaber legt Mitglieder direkt an. Das erste Konto lässt sich dann nur anlegen, indem Sie kurz auf `first_account` stellen. | Nach der Einrichtung, wenn niemand mehr dazukommen soll |
| `open` | Jede Person darf eine neue Firma anlegen. | Nur für bewusst öffentliche Mehrmandanten-Instanzen, mit eigenem Betreiber-Konzept (Missbrauchsschutz, Datenschutz, Verträge) |

Grenze: Zwei exakt gleichzeitige Erstregistrierungen auf einer frischen, noch leeren Instanz sind nicht gegeneinander
gesperrt. Registrieren Sie das erste Konto direkt nach dem Start, bevor Sie die Adresse weitergeben. Die Registrierung
ist zusätzlich je IP-Adresse begrenzt.

## 7. E-Mail ist optional, Konto wiederherstellen

SMTP ist optional. Fehlen `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (Secret-Datei `smtp_password`) oder eine
Absenderadresse (`SMTP_ABSENDER`, sonst `SMTP_USER`, falls das eine Adresse ist), startet die App trotzdem und schreibt
beim Start eine Warnung ins Log. Dann gilt:

- „Per E-Mail senden“ bei Rechnungen, Angeboten und Mahnungen antwortet mit HTTP 503 und der Meldung, dass E-Mail nicht
  eingerichtet ist. Es wird nichts als „versendet“ verbucht. Das PDF lässt sich weiterhin herunterladen und selbst versenden.
- „Passwort vergessen“ und die E-Mail-Bestätigung beim Ändern der Adresse antworten ebenfalls mit 503 und einer klaren
  Meldung. Die Antwort ist für bekannte und unbekannte Adressen gleich.
- Registrierung, Anmeldung und alles andere funktionieren unverändert.

Als Absender wird nie eine voreingestellte Domain verwendet; tragen Sie eine Adresse Ihrer eigenen Domain ein und richten
Sie SPF/DKIM ein (siehe `docs/email-zustellung.md`).

**Wiederherstellungsweg ohne E-Mail (für Betreiber).** Wer sein Passwort verliert, setzt es mit dem Skript
`backend/scripts/konto_wiederherstellen.py` auf dem Server zurück. Es braucht Zugriff auf Datenbank und Schlüssel der
Instanz, also Serverzugang:

```bash
# Konten ansehen (falls die Adresse vergessen wurde)
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \
  python -m scripts.konto_wiederherstellen --konten-auflisten

# Passwort neu setzen (verdeckte Eingabe, zweimal); alle Sitzungen werden widerrufen
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \
  python -m scripts.konto_wiederherstellen --email name@example.org

# Zusätzlich Zwei-Faktor-Anmeldung abschalten (Gerät und Wiederherstellungscodes verloren)
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend \
  python -m scripts.konto_wiederherstellen --email name@example.org --mfa-zuruecksetzen
```

`--zufallspasswort` erzeugt stattdessen ein Passwort und gibt es einmal aus. Ohne `--mfa-zuruecksetzen` bleibt MFA aktiv.
Das Skript setzt außerdem Fehlversuchszähler und Kontosperre zurück und schreibt einen Audit-Eintrag
(`konto_wiederhergestellt_betreiber`, ohne Passwort). Es ist ein Betreiberwerkzeug: Wer es ausführen kann, kann jedes Konto
übernehmen, das ist bei Serverzugang ohnehin so. Sichern Sie Ihren Serverzugang entsprechend (Abschnitt 5 und
`docs/betrieb-runbook.md`, Abschnitt 1).

Sind alle Inhaber-Konten gesperrt und der Serverzugang selbst verloren, hilft nur das Zurückspielen eines Backups auf
einem neuen Server, wofür Backup **und** Schlüssel nötig sind (Abschnitte 4 und 8).

## 8. Backups

Ein Backup muss Datenbank **und** Dateien umfassen, und der Restore muss getestet sein. Eine Kopie auf demselben Server
schützt nicht vor Serverausfall, Diebstahl oder Ransomware.

- `scripts/backup.sh` sichert Postgres (`pg_dump`) und das Datei-Volume, beides direkt im Stream mit `age` verschlüsselt, mit
  Prüfsummen. Es gibt keinen Klartext-Modus. Einrichtung, Variablen und Beispiele: `docs/backup-restore.md`.
- Erzeugen Sie das `age`-Schlüsselpaar **nicht auf dem Server** (`age-keygen`), tragen Sie nur den öffentlichen Schlüssel
  (`BACKUP_AGE_RECIPIENT=age1...`) ein und bewahren Sie den privaten an zwei Orten außerhalb des Servers auf. Verlust des
  privaten Schlüssels macht alle Backups unbrauchbar.
- **Off-site:** `OFFSITE_TARGET` (rsync-Ziel bei einem anderen Anbieter) einrichten. Das Skript endet standardmäßig mit
  Fehler, wenn kein Off-site-Ziel gesetzt ist; `REQUIRE_OFFSITE=0` schaltet das ab, schützt Sie dann aber nur vor
  Bedienfehlern, nicht vor dem Verlust des Servers.
- **Die Anwendungsschlüssel stehen nicht im Backup** und müssen separat gesichert werden (Abschnitt 4).
- Täglich per Cron oder systemd-Timer; Beispiel in `docs/backup-restore.md`. `scripts/healthcheck.sh` prüft Alter und
  Unversehrtheit des letzten Backups (`docs/betrieb-monitoring.md`).
- **Restore testen:** `scripts/restore-test.sh` spielt ein Backup in eine Wegwerf-Datenbank und prüft es. Danach zusätzlich
  einmal auf einem Testsystem mit Kopie der Schlüssel anmelden und ein Rechnungs-PDF und einen Beleg öffnen. Erst damit ist
  das Backup belastbar. Wiederholen Sie den Test regelmäßig (mindestens quartalsweise) und nach jeder Migration, die Daten
  umschreibt.

## 9. Updates und Migrationen

```bash
cd /opt/bilantiq-app
# 1. Backup erstellen und prüfen (Abschnitt 8). Release-Hinweise lesen: CHANGELOG.md.
git fetch && git checkout <neues-Release-Tag>
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail 100 backend
```

Der separate Dienst `migrate` führt `alembic upgrade head` aus; die API selbst hat keine Schema-Verwaltungsrechte.
Bei Updates nach Stoppen der alten API auch `migrate` erneut ausführen/recreaten (siehe `docs/security-runtime.md`).
Schemaänderungen kommen ausschließlich über neue Migrationen;
manche sind nicht umkehrbar (z. B. `0036`). Ein „Zurück“ gibt es deshalb nur über das Zurückspielen des Backups von vor
dem Update (`docs/rollback.md` beschreibt den Ablauf). Prüfen Sie nach jedem
Update: Anmeldung, Rechnungsliste, ein PDF, ein Beleg, `GET /health`. Halten Sie außerdem das Betriebssystem, Docker und
die Basis-Images aktuell und beobachten Sie Sicherheitsmeldungen des Projekts (siehe `SECURITY.md`).

## 10. Aufbewahrungsfristen und GoBD: Ihre Verantwortung

Bilantiq ist ein Werkzeug, keine Zertifizierung. Es gibt keine Prüfbescheinigung für GoBD-Konformität, und das Projekt
gibt keine Gewähr dafür, dass Ihre Buchführung den steuerlichen Anforderungen genügt. Als Betreiber und Nutzer sind Sie
verantwortlich für:

- die gesetzlichen **Aufbewahrungsfristen** Ihrer Unterlagen (Handels- und Steuerrecht, u. a. AO und HGB; die Dauer
  hängt von der Art der Unterlage und vom Zeitpunkt ab, hier nicht rechtlich geprüft) und dafür, dass Backups und
  Schlüssel diese gesamte Zeit lesbar bleiben (Schlüssel dürfen in dieser Zeit nicht verloren gehen);
- die **Verfahrensdokumentation**, Unveränderbarkeit, Nachvollziehbarkeit und ordnungsgemäße Archivierung nach den GoBD für
  Ihren Betrieb. Bilantiq führt ein append-only Audit-Log (auf Postgres per Datenbank-Trigger gesperrt), ersetzt
  aber weder Ihre Verfahrensdokumentation noch die Beratung durch Steuerberatung;
- den Umgang mit der **Konto-Löschung/Anonymisierung** in der App: Sie kollidiert mit Aufbewahrungspflichten, wenn
  Buchungsunterlagen betroffen sind. Klären Sie das vorher.

Die Funktionen für E-Rechnung, DATEV-Export, UStVA, EÜR und andere Auswertungen haben dokumentierte Grenzen (siehe
README, „Bekannte Grenzen“, und die Specs unter `docs/specs/`). Prüfen Sie Ergebnisse mit Ihrer Steuerberatung, bevor Sie
sie an Behörden oder Dritte weitergeben.

## 11. Datenschutz (DSGVO): Ihre Verantwortung

- Wer Bilantiq für die eigene Firma betreibt, ist für die Daten seiner Kundschaft, Lieferanten und Beschäftigten
  **Verantwortlicher** im Sinne der DSGVO. Dazu gehören ein Verzeichnis der Verarbeitungstätigkeiten, Datenschutzerklärung,
  Löschkonzept, Meldewege bei Datenpannen (72 Stunden) und technische/organisatorische Maßnahmen. Einen Entwurf einer
  TOM-Beschreibung aus der Zeit vor dem Open-Source-Umbau enthält `docs/dsgvo-toms-entwurf.md`; er ist nicht rechtsgeprüft
  und beschreibt keine Instanz, die Sie betreiben.
- Wer die Instanz **für andere** betreibt (Verein, Dienstleister, mehrere Firmen auf einem Server), verarbeitet deren Daten in
  der Regel als **Auftragsverarbeiter** und braucht dafür eigene Verträge (Auftragsverarbeitungsvertrag), eigene
  Datenschutzhinweise und Nutzungsbedingungen. Das Projekt stellt keine Vertrags- oder Rechtstexte bereit.
- IP-Adressen stehen in den Zugriffsprotokollen des Servers und müssen im Verzeichnis und in der Datenschutzerklärung
  erscheinen; begrenzen Sie die Aufbewahrung der Docker-Logs (Vorschlag in `docs/betrieb-runbook.md`, Abschnitt 2.3).
- Laut Projektstand lädt die Oberfläche keine Schriften von Drittanbietern (nicht erneut geprüft). Die lokale KI-Funktion ist standardmäßig aus und hat keinen
  Cloud-Fallback; schalten Sie sie nur mit einem Inferenz-Dienst ein, den Sie selbst betreiben und verantworten.

## 12. Sicherheits-Checkliste

- [ ] `APP_ENV=production`, `TRUSTED_HOSTS_RAW` und `CORS_ALLOWED_ORIGINS_RAW` auf die eigenen Domains gesetzt (die App startet sonst nicht)
- [ ] Secrets mit `init-secrets.sh` erzeugt, getrennt vom Datenbackup gesichert, keine Platzhalter
- [ ] `REGISTRATION_MODE=first_account` oder `closed`
- [ ] MFA für alle Inhaber-Konten eingerichtet, Wiederherstellungscodes gespeichert
- [ ] Firewall: nur 22/80/443, Postgres nirgends veröffentlicht, von außen geprüft
- [ ] Backup mit `age` und Off-site-Kopie, Restore auf einem Testsystem durchgeführt
- [ ] Regelmäßige Updates von Host, Docker, Images und Bilantiq
- [ ] SSH nur mit Schlüssel, Root-Login aus; Datenträgerverschlüsselung beim Hoster oder per LUKS

Sicherheitslücken in Bilantiq selbst melden Sie nach `SECURITY.md`.

## 13. Fehlersuche

| Meldung / Symptom | Ursache und Abhilfe |
| --- | --- |
| `Der Dateispeicher ist nicht benutzbar: … nicht geschrieben werden` | Besitzer/Rechte des Ordners oder des gemounteten Volumes. Im Image läuft Bilantiq als UID 1000: `chown -R 1000:1000 <Ordner>`. |
| `… existiert, ist aber kein Ordner` | `STORAGE_DIR` zeigt auf eine Datei. |
| `… enthaelt noch den Platzhalter aus .env.example` | Ein Secret wurde nicht ersetzt. Mit `init-secrets.sh` bzw. eigenen Zufallswerten füllen. |
| `TRUSTED_HOSTS_RAW muss auf die echte(n) Domain(s) gesetzt sein` | Bei `APP_ENV=production` Pflicht, kein `*`. |
| HTTP 503 „E-Mail ist auf dieser Instanz nicht eingerichtet“ | SMTP nicht (vollständig) konfiguriert, siehe Abschnitt 7. |
| HTTP 403 „Registrierung ist geschlossen“ | `REGISTRATION_MODE`, siehe Abschnitt 6. Einladungscode des Inhabers verwenden. |
| Container startet nicht, `PermissionError` bei `/run/secrets/…` | Rechte der Secret-Dateien: siehe Abschnitt 14 (nicht verifiziert). |
| Caddy bekommt kein Zertifikat | DNS zeigt nicht auf den Server, Ports 80/443 gesperrt, `APP_DOMAIN`/`API_DOMAIN` falsch. |

## 14. Was geprüft wurde und was nicht

Geprüft (automatische Tests, Backend, SQLite): Ableitung der Speicherordner aus `STORAGE_DIR`; Startprüfung mit Anlegen,
Rechten 0700, Probedatei, Meldungen bei Datei statt Ordner und bei nicht anlegbaren Ordnern; Abbruch des App-Starts bei
kaputtem Speicher; Verschlüsselung und Path-Traversal-Schutz der Dateiablage; Start ohne SMTP, 503-Antworten statt
stillem Verschlucken, gleiche Antwort für bekannte und unbekannte Adressen bei „Passwort vergessen“; die drei
Registrierungsmodi; das Wiederherstellungsskript (Passwort, Sitzungen, MFA, Audit-Eintrag); Ablehnung von
Platzhalter-Secrets. Außerdem lief `docker compose config` für beide Compose-Dateien sauber, und `init-secrets.sh` erzeugt
die Dateien mit den Rechten 0700/0600.

**Nicht geprüft** (in der Entwicklungsumgebung gab es keinen Docker-Daemon, kein Caddy, keinen echten Server, keinen
SMTP-Zugang und kein echtes Postgres):

- Bauen und Starten der Docker-Images, die Startkette im Container (Speicherprüfung, Migration, Server) und das
  Schreiben in ein frisches Volume bzw. in einen Host-Ordner mit UID 1000.
- Die Platzhalter `{$APP_DOMAIN}`/`{$API_DOMAIN}` in der `Caddyfile` (Caddy ersetzt Umgebungsvariablen beim Einlesen, hier
  nicht ausgeführt) und die Zertifikatsausstellung.
- Ob der Benutzer im Container (UID 1000) die als 0600/root angelegten Docker-Secret-Dateien unter `/run/secrets` lesen
  kann. Falls der erste Start mit einem Berechtigungsfehler abbricht, ist das die Stelle (Rechte oder Besitzer der
  Secret-Dateien bzw. `uid`/`mode` bei den Secrets in der Compose-Datei anpassen).
- Backup, Restore und Healthcheck gegen echtes Docker (siehe die Einschränkungen in `docs/backup-restore.md`).
- Der echte SMTP-Versand (nur gegen Attrappen getestet) und die Postgres-Variante der Row-Level-Security im Rahmen dieser
  Änderungen.
