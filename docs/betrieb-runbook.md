# Bilantiq Betriebs-Runbook

Stand: 14. Oktober 2026

> **Hinweis zum Selbst-Hosting-Modell (22. Oktober 2026):** Bilantiq wird als Open-Source-Projekt veröffentlicht; jede Person
> betreibt ihre eigene Instanz mit eigenem Speicher. Maßgeblich für Einrichtung, Speicher, Registrierung, E-Mail und
> Wiederherstellung ist [self-hosting.md](self-hosting.md). Dieses Dokument bleibt als Härtungs-Checkliste gültig; wo es von
> „dem Betreiber“, einem zentralen Betrieb oder Stripe/Tarifen spricht, stammt das aus der Planung eines gehosteten Dienstes
> und ist für Selbsthoster nicht verbindlich.

Ergänzt `docs/security-production.md` (Baseline), `docs/server-rollout.md` (Migrationen 0035/0036,
Laufzeitrolle) und `docs/incident-response.md` (Datenpannen). Alles hier ist aus dem Repo-Stand
abgeleitet. Nichts davon wurde auf dem echten Server ausgeführt. Dienstnamen (`backend`, `postgres`,
`caddy`) stammen aus `docker-compose.prod.yml`.

**In dieses Dokument gehören keine echten Passwörter, Schlüssel oder Tokens.** Es hält nur fest,
*wo* etwas liegt und *wer* Zugriff hat.

## 1. Notfallzugang (Vorlage zum Ausfüllen)

Ziel: Wenn der Admin-Rechner, der SSH-Schlüssel oder ein Konto ausfällt, kommt trotzdem jemand an den
Server und an die Wiederherstellungswege. Die ausgefüllte Fassung wird **an zwei getrennten Orten**
abgelegt (z. B. Passwortmanager mit Notfallzugang der Vertrauensperson und ausgedruckt im Safe), nicht
auf dem Server und nicht im Repo.

| Feld | Eintrag (ausfüllen, ohne Passwörter) |
| --- | --- |
| Hoster / Rechenzentrum / Region | [Anbieter, EU-Region] |
| Server-Bezeichnung, öffentliche IP, Vertrags-/Kundennummer | [ ... ] |
| Login Provider-Konto (E-Mail-Adresse des Kontos) | [Adresse] |
| Provider-Konto: MFA-Gerät / Wiederherstellungscodes liegen in | [Ort 1], [Ort 2] |
| Rescue-/VNC-/Konsolen-Zugang des Providers (URL, Vorgehen) | [URL, Schritte: Rescue-System starten, Disk mounten, ...] |
| SSH: Benutzername, Port, erlaubte Admin-IP/VPN | [ ... ] |
| SSH-Schlüssel: Fingerprint, wo liegen private Schlüssel (Gerät 1, Gerät 2) | [Fingerprint], [Ort] |
| Notfall-SSH-Schlüssel (Break-glass), Ablageort | [Ort, wer darf ihn nutzen] |
| Verzeichnis `BILANTIQ_SECRETS_DIR` auf dem Server | [z. B. /opt/bilantiq/secrets, Rechte 0700 root] |
| Offline-Sicherung der Secret-Dateien (getrennt vom Datenbackup) | [Ort, Verschlüsselung, Datum letzter Stand] |
| `age`-Backup-Schlüssel (privat): Ablageort(e), **nie auf dem Server** | [Ort 1], [Ort 2] |
| Off-site-Backup-Ziel (`OFFSITE_TARGET`), Konto, Zugangsweg | [Anbieter, Adresse, Zugangsart] |
| Domain-Registrar: Konto, MFA, Transfer-Sperre | [Anbieter, Konto] |
| DNS-Anbieter: Konto, Einträge `@`, `www`, `api` | [Anbieter, Konto] |
| SMTP-Anbieter: Konto, Absenderdomain, SPF/DKIM/DMARC-Stand | [ ... ] |
| GitHub: Repository, Inhaberkonto, Wiederherstellungscodes | [ ... ] |
| Vertrauensperson (Vertretung), Berechtigungen, Kontakt | [Name, Telefon] |
| Passwortmanager: Name, Notfallzugang konfiguriert am | [Datum] |
| Letzter Test des Notfallzugangs (Rescue-Login wirklich ausprobiert) | [Datum, Ergebnis] |

Regeln:
- Zugang **zweimal jährlich testen** (Rescue-Konsole öffnen, Fallback-SSH-Schlüssel prüfen) und
  das Testdatum eintragen. Ein nie getesteter Notfallzugang gilt als nicht vorhanden.
- Ändert sich ein Eintrag (neuer Provider, neuer Schlüssel), beide Ablageorte am selben Tag aktualisieren.
- Wer im Vorfall Zugangsdaten verwendet hat, trägt es im Vorfallsprotokoll ein (siehe
  `docs/incident-response.md`).

## 2. Logs: Was geloggt wird, Aufbewahrung, Rotation

### 2.1 Bestandsaufnahme (aus dem Code)

| Komponente | Was geloggt wird | Quelle |
| --- | --- | --- |
| Caddy (Container `caddy`) | Laufzeitmeldungen auf stderr (Start, TLS/ACME, Fehler). **Keine Zugriffsprotokolle**, da im `Caddyfile` kein `log`-Block steht. | `Caddyfile` |
| Backend (Container `backend`) | uvicorn-Standardausgabe: Startmeldungen, **Zugriffszeilen** (Client-IP über `--proxy-headers`, Methode, Pfad inkl. Query-String, Status), Tracebacks bei unbehandelten Fehlern. Der Anwendungscode selbst schreibt keine Logs (`logging`/`print` kommen in `backend/app` nicht vor). | `backend/Dockerfile`, `backend/app` |
| Postgres (Container `postgres`) | Server-Meldungen auf stderr (Fehler, Checkpoints, Verbindungsprobleme). Keine Konfiguration für `log_statement` oder `log_connections` im Repo, also gelten die Standardwerte des Images `postgres:16` (keine Statement-Protokollierung). | `docker-compose.prod.yml` |
| Backup-Skript | Meldungen nach stdout, laut README per cron in `/var/log/bilantiq-backup.log`. Keine Daten, nur Dateinamen/Zeitstempel. | `scripts/backup.sh`, README |
| Anwendungs-Audit-Log | Tabelle `audit_log_eintraege` in der Datenbank (kein Datei-Log), append-only, Kontext AES-GCM-verschlüsselt. Fachliche Nachweispflicht, **nicht** durch Log-Rotation zu löschen. | `backend/app/core/audit_log.py` |

### 2.2 Prüfung auf personenbezogene Daten und Secrets (Befund)

Quelle ist Code-Lektüre, kein Laufzeittest.

- **IP-Adressen** stehen in den uvicorn-Zugriffszeilen. Das ist personenbezogen (Art. 4 Nr. 1 DSGVO). Es
  braucht Zweck, Frist und Eintrag im Verzeichnis (`docs/dsgvo-toms-entwurf.md`) und Erwähnung in der
  Datenschutzerklärung.
- **Authentifizierung läuft über Bearer-Header**, nicht über die URL. Passwörter, MFA-Codes und JWTs
  stehen deshalb nicht in Zugriffszeilen. Anfragen mit Body (Login, Registrierung) loggt uvicorn nicht.
- **Query-Strings im Zugriffslog:** Ein Logging-Filter (`backend/app/core/zugriffslog.py`, am Logger `uvicorn.access`,
  beim App-Start installiert) ersetzt **jeden Query-String** in der Zugriffszeile durch `?[gekuerzt]`. Grenzen: Der Filter
  wirkt nur auf Zugriffszeilen; Tracebacks (`uvicorn.error`) und ältere, vor dem Update geschriebene Logs sind
  nicht betroffen und bleiben wie Zugangsdaten zu behandeln.
- **Query-Strings mit Kundendaten:** Die Rechnungsvorlagen-Vorschau nahm früher `iban`, `bic` und `fusszeile_text`
  als Query-Parameter (`GET`). Sie ist jetzt `POST /auth/mandant/rechnungsvorlage/vorschau` mit JSON-Body; der
  GET-Pfad existiert nicht mehr. Die übrigen GET-Routen mit Query-Parametern (Filter, Jahr, `anbieter` bei
  `/belege/vorschlag`) enthalten keine Zugangsdaten; ihre Query-Strings werden vom Filter ohnehin entfernt.
- **UUIDs** (Mandant, Rechnung, Beleg) erscheinen in Pfaden. Sie sind Pseudonyme, keine Klartextdaten.
- **Fehlermeldungen:** `HTTPException`-Texte enthalten keine Nutzerdaten (nur Feldnamen und Grenzen). Ein
  unbehandelter Fehler schreibt einen Traceback, der je nach Fehler Werte aus dem Request enthalten *kann*.
  Das ist beim Hypercare zu beobachten.
- **Secrets** werden vom Anwendungscode nicht geloggt. Sie liegen unter `/run/secrets` (Dateien) und nicht in
  Umgebungsvariablen von `docker inspect`, sofern `.env.prod` wie vorgesehen nur nicht-geheime Werte
  enthält (siehe `.env.prod.example`).
- **Postgres-Standard** loggt keine SQL-Parameter. `log_statement`, `log_min_duration_statement` mit
  Statements oder `log_connections` nur gezielt und zeitlich begrenzt aktivieren, da Parameter
  (verschlüsselte Texte, aber auch Hashes und IDs) in den Log geraten können.

### 2.3 Aufbewahrung und Rotation (Vorschlag, vom Betreiber zu bestätigen)

Docker nutzt ohne Konfiguration den `json-file`-Treiber **ohne** Größenbegrenzung. Logs wachsen dann, bis
die Platte voll ist (Verfügbarkeitsrisiko, ebenso Datenschutzrisiko durch unbegrenzte IP-Speicherung).

| Log | Vorschlag Aufbewahrung | Begründung |
| --- | --- | --- |
| Backend-/Caddy-/Postgres-Container-Logs | höchstens 30 Tage bzw. ca. 50 MB je Container (5 Dateien à 10 MB) | Fehleranalyse und Vorfallsuntersuchung; IP-Adressen nicht länger als nötig. Die Frist legt der Owner mit der Datenschutz-Fachperson fest. |
| Backup-Skript-Log `/var/log/bilantiq-backup.log` | 90 Tage (wöchentliche Rotation, 12 Stück) | Nachweis, dass Backups liefen |
| Host-Logs (SSH/Auth) | Distributions-Standard (journald/logrotate), mindestens 30 Tage | Einbruchsanalyse |
| Audit-Log (Datenbank) | **nicht rotieren/löschen**, solange kein Aufbewahrungskonzept beschlossen ist. Die Einstellung `retention_years` (Vorbelegung 10) wird **nirgends durchgesetzt**: im Code kommt sie nur in `config.py` und einem Docstring vor, es gibt keinen Löschjob und der Postgres-Trigger `audit_log_append_only` verbietet jedes `UPDATE`/`DELETE`. Bewertung und Optionen siehe Abschnitt 6 | Nachweis-/GoBD-Zweck |

Umsetzungsvarianten (Konfigurationsänderungen gehören ins Compose/Hostsetup, nicht in diesen Entwurf):

1. Host-weit in `/etc/docker/daemon.json`:
   ```json
   { "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
   ```
   Wirkt für neu erstellte Container (Docker-Dienst neu starten, Container neu erzeugen).
2. Alternativ je Dienst ein `logging:`-Block mit denselben `options` in `docker-compose.prod.yml`.
3. Für `/var/log/bilantiq-backup.log` eine logrotate-Regel `weekly`, `rotate 12`, `compress`, `missingok`,
   `notifempty`.
4. Prüfen nach Einführung: `docker inspect --format '{{.HostConfig.LogConfig}}' <container>` und
   Plattenbelegung (`df -h`, `docker system df`).

### 2.4 Logs lesen

```
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --since 1h --timestamps backend
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --since 1h --timestamps caddy postgres
```

Beim Hypercare täglich nach `permission denied`/`InsufficientPrivilege` (Laufzeitrolle, siehe
`docs/server-rollout.md`), HTTP 500 und ungewöhnlich vielen 401/403-Antworten suchen. Beim Teilen von
Log-Auszügen IP-Adressen schwärzen.

## 3. Backup und Restore (Kurzfassung)

Grundsatz aus `docs/security-production.md`: Ein Backup gilt erst nach einem **getesteten Restore** als
belastbar (Release-Blocker 1). Dieser Test wurde im Rahmen der Doku-Arbeit nicht ausgeführt.

**Was gesichert wird** (`scripts/backup.sh`): ein Postgres-Dump (`pg_dump --clean --if-exists`, gzip,
direkt mit `age` verschlüsselt, Datei `db_<Zeitstempel>.sql.gz.age`) und das Upload-Volume
`bilantiq_backend_data` (Belege, Logos, Briefpapier, Bankdateien, Altrechnungen; als
`uploads_<Zeitstempel>.tar.gz.age`). **Nicht** enthalten: Secrets/Key-Dateien (separat und offline sichern),
`.env.prod`, Caddy-Zertifikate (Caddy holt sie neu), Container-Images (aus Git neu bauen).

**Täglich (cron/Timer):**

```
cd /opt/bilantiq && BACKUP_AGE_RECIPIENT="<age public key>" OFFSITE_TARGET="<ziel>" ./scripts/backup.sh >> /var/log/bilantiq-backup.log 2>&1
```

- Pflicht: `BACKUP_AGE_RECIPIENT` (ohne ihn bricht das Skript ab, unverschlüsselte Backups sind nicht möglich).
- Lokale Aufbewahrung `RETENTION_DAYS` (Standard 14 Tage); `OFFSITE_TARGET` (rsync) ist laut Skript sonst nur eine
  Warnung, in der Praxis aber Pflicht (GoBD, getrennter Speicher).
- Täglich prüfen: Logzeile `backup.sh: fertig`, Dateigrößen größer 0, Off-site-Datei vorhanden (Alarm einrichten,
 ).

**Restore (auf isoliertem Testsystem, dann im Ernstfall):**

1. System mit gleichem Compose-Stack und **denselben Secret-Dateien** aufsetzen. Besonders
   `data_encryption_keys` mit allen Keys, die je aktiv waren (auch Audit-Log, siehe Abschnitt 4).
2. `BACKUP_AGE_IDENTITY_FILE=<privater age-Schlüssel> ./scripts/restore.sh backups/db_<TS>.sql.gz.age`
   (überschreibt die Datenbank; verlangt Eingabe `JA`).
3. Upload-Volume nach dem Kommentarblock am Ende von `scripts/restore.sh` einspielen (`age -d ... | docker run ... tar xzf -`).
4. Anwendung starten (`alembic upgrade head` läuft im Backend-Start), Laufzeitrolle prüfen (`backend/scripts/runtime_rolle.sql`).
5. Prüfen: Login, Rechnungsliste, ein Rechnungs-PDF, ein Beleg-Download, `/health`. Dauer messen und
   notieren: Restore-Zeit `[ ]`, Datenstand `[ ]`, Datum `[ ]`.
6. Test-Restore **quartalsweise** wiederholen, danach Protokoll im Vorfallsordner ablegen.

Grenzen: Wiederherstellung kennt nur den Stand des letzten Backups (täglich = bis zu 24 h Datenverlust). Das Backup
hängt zusätzlich vom Upload-Volume ab, die beiden Dateien müssen zum selben Zeitpunkt passen.

## 4. Key-Rotation (inklusive Audit-Log-Grenze)

Betroffen sind die Dateien unter `BILANTIQ_SECRETS_DIR` (siehe `scripts/init-secrets.sh` und
`docker-compose.prod.yml`). Die Auswirkung je Secret steht in `docs/incident-response.md`, Abschnitt 7.
Hier der geplante (nicht kompromittierte) Ablauf für den Datenschlüssel, der mit Skript unterstützt wird:

1. **Backup und Key-Sicherung:** frisches Backup (Abschnitt 3), aktuelle `data_encryption_keys` getrennt kopieren.
2. Neuen Key erzeugen:
   `python3 -c 'import base64,secrets; print("v2:"+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))'`
3. Den Wert **zusätzlich** zur bestehenden Zeile in `data_encryption_keys` aufnehmen (kommagetrennt,
   `v1:...,v2:...`). `DATA_ENCRYPTION_ACTIVE_KID` auf `v2` setzen. Backend neu starten.
   Ab jetzt werden neue Werte mit `v2` geschrieben, alte bleiben mit `v1` lesbar.
4. Rotation ausführen (im Backend-Container oder einer Arbeitskopie mit denselben Secrets):
   `python scripts/rotate_encryption.py`. Es schreibt Datenbankwerte und Dateien (Belege, Logos,
   Briefpapier, Kontoauszüge, Altrechnungen) auf den aktiven Key um.
5. Prüfen: `python -m scripts.rotate_encryption --pruefen`. Die Ausgabe nennt jede Spalte, die noch nicht auf dem
   aktiven Key liegt.
6. Smoke-Test (Login, Rechnung, PDF, Beleg, Export).
7. **Alten Key `v1` nicht entfernen**, wenn eine der folgenden Grenzen greift.

**Audit-Log-Grenze auf Postgres:** Die Tabelle `audit_log_eintraege` ist per Datenbank-Trigger
(Migration 0001, `audit_log_append_only`) gegen jede Änderung gesperrt. Das Rotationsskript überspringt sie
deshalb. Ihr Kontext bleibt mit dem Key verschlüsselt, mit dem er geschrieben wurde. Das Skript meldet das
(„Alten Key BEHALTEN“) und beendet sich mit einem Hinweis. Konsequenzen:
- Der alte Key muss dauerhaft im Keyring bleiben, solange Audit-Einträge auf ihm liegen (Aufbewahrung nach dem noch festzulegenden
  Aufbewahrungskonzept, vorläufig bis zu 10 Jahre). Er wird also in die Offline-Sicherung der Key-Dateien aufgenommen und darf bei
  Aufräumarbeiten nicht gelöscht werden.
- Eine Rotation wegen eines **kompromittierten** Keys macht die Audit-Kontexte nicht sicherer, weil sie mit dem alten Key
  weiter lesbar bleiben. Das gehört in die Risikobewertung (`docs/incident-response.md`, Abschnitt 4).
- Auf SQLite (nur Entwicklung) gilt die Sperre nicht, dort wird das Audit-Log mit rotiert.

**Andere Secrets:** `jwt_secret` austauschbar (alle Nutzer müssen sich neu anmelden); `email_lookup_secret` und
`blind_index_secret` haben **kein** Rotationsskript, ein Tausch bricht Logins bzw. Suche und Duplikaterkennung. SMTP-/
Datenbankpasswörter: Ablauf in `docs/incident-response.md`, Abschnitt 7. Rotationsintervall (Vorschlag, vom Betreiber
zu bestätigen): Datenschlüssel jährlich oder bei Verdacht, Zugangsdaten externer Dienste jährlich oder beim Ausscheiden einer Person.

**Übung:** Einmal komplett auf Staging durchspielen, Zeitbedarf notieren: `[ ]`.

## 5. Routinen (Checkliste)

| Takt | Aufgabe |
| --- | --- |
| täglich (Hypercare) | Backup-Logzeile und Off-site-Datei, Fehler-Logs (Abschnitt 2.4), Plattenbelegung, Supportpostfach |
| wöchentlich | Audit-Log auf Auffälligkeiten (viele `login_fehlgeschlagen`, unbekannte `datenexport`), Zertifikatsablauf, Updates (Host, Images) |
| monatlich | Abhängigkeiten (`pip-audit`, `npm audit`), Benutzer-/Rollenreview, Logrotation kontrollieren |
| quartalsweise | Restore-Test, Notfallzugang testen (halbjährlich), Key-Dateien-Offlinesicherung abgleichen |
| jährlich | Key-Rotation, Pentest/Scan, Incident-Übung, TOMs und Verzeichnis prüfen |

## 6. Offene Punkte

- Log-Konfiguration (Abschnitt 2.3) ist ein Vorschlag, im Repo nicht umgesetzt.
- Zugriffslog: Query-Strings werden seit Release-Härtung maskiert (Abschnitt 2.2); ältere Logs davor bleiben sensibel.
- **Audit-Log-Aufbewahrung (`retention_years`) ist nicht durchgesetzt** (bewusst nicht implementiert; der Log ist append-only, per Trigger auch in der Datenbank). Bewertung:
  - Es gilt faktisch „unbegrenzt“: Der Log wächst ohne Löschfrist. Das ist für den Nachweiszweck (GoBD/Revisionssicherheit) unkritisch, für den
    Datenschutz aber ein Punkt (Art. 5 Abs. 1 lit. e DSGVO, Speicherbegrenzung): Einträge enthalten Nutzer-/Mandanten-IDs, Aktion, Zeitpunkt und
    einen verschlüsselten Kontext (z. B. Rechnungsnummern). Ohne begründete Frist im Verzeichnis der Verarbeitungstätigkeiten ist „unbegrenzt“ schwer zu vertreten.
  - Der Wert 10 ist nicht hergeleitet: Nach meinem Kenntnisstand gelten für Bücher/Jahresabschlüsse 10 Jahre, für Buchungsbelege seit 2025 8 Jahre (§ 147 AO);
    ob ein Änderungsprotokoll überhaupt darunter fällt oder zur Verfahrensdokumentation gehört, ist steuerberaterlich zu klären. Sicherheits-Ereignisse
    (`login_fehlgeschlagen`, `konto_gesperrt`) brauchen vermutlich eine deutlich kürzere Frist als buchungsnahe Aktionen.
  - Umsetzung wäre kein Einzeiler: (a) Löschen verlangt entweder eine Ausnahme im Trigger (z. B. nur für eine eigene Wartungsrolle und nur für Zeilen älter als N Jahre)
    oder (b) Partitionierung nach Jahr und Abtrennen/Löschen alter Partitionen (kein Row-Trigger beteiligt, braucht aber eine Migration und Umbau der Tabelle).
    Dazu kommt die Schlüsselrotation: Auf Postgres bleibt der Audit-Log beim alten Datenschlüssel, der alte Key darf erst nach dem
    Ablauf der Frist entfallen. Eine Löschfrist wäre also zugleich die Voraussetzung dafür, alte Schlüssel jemals zu entsorgen.
  - Empfehlung: Frist je Ereignisart mit Steuerberater/Datenschutz festlegen und im Verzeichnis eintragen; danach (b) oder (a) bauen, Einstellung
    in `audit_aufbewahrung_jahre` umbenennen oder entfernen, damit sie nichts vorspiegelt. Bis dahin Log nie manuell kürzen. **Entscheidung der Betreiberin bzw. des Betreibers.**
- Monitoring/Alarmierung und Staging (2.9) fehlen.
- Restore-Test und Key-Rotation auf Staging stehen aus; Dauer und Ergebnis sind hier noch nicht eingetragen.

## 7. Betriebsschalter aus der Release-Härtung (Branch release/log-limits)

| Schalter / Maßnahme | Wo | Wirkung | Was der Betreiber tun muss |
| --- | --- | --- | --- |
| `APP_ENV=production`  | `.env.prod` | Die App **startet nicht**, wenn `TRUSTED_HOSTS_RAW` fehlt, leer ist oder `*` enthält (Host-Header-Schutz wäre sonst still aus). Standard `development` (lokal/Tests) bricht nicht. | Zeile `APP_ENV=production` in die **bestehende** `.env.prod` auf dem Server eintragen. Ohne sie startet die App weiter, schreibt aber bei Postgres + `TRUSTED_HOSTS_RAW=*` eine Warnung ins Log (`TRUSTED_HOSTS_RAW erlaubt jeden Host ...`). |
| `--no-server-header` im uvicorn-Start (`backend/Dockerfile`) und `header -Server` im API-Block von `Caddyfile` | Dockerfile, Caddyfile | Keine `Server: uvicorn`/`Server: Caddy`-Header mehr an der API. `--no-server-header` habe ich lokal mit uvicorn geprüft (Header fehlt). **Die Caddy-Zeile ist nicht getestet** (kein `caddy`/Docker in dieser Umgebung); im Frontend-Block steht `-Server` bereits, die Syntax ist dieselbe. | Image neu bauen, Caddy neu laden; mit `curl -sI https://api.bilantiq.de/health` prüfen, dass kein `server:` erscheint. |
| 500er-Antworten tragen Security-Header | `backend/app/main.py` | Unbehandelte Ausnahmen laufen in Starlette außerhalb der Header-Middleware; ein Exception-Handler setzt dieselben Header. Antwort bleibt ohne Details (`Interner Serverfehler.`), der Traceback steht weiter im Log. CORS-Header fehlen bei 500ern weiterhin (CORS-Middleware liegt innerhalb). | – |
| `EMAIL_LIMIT_PRO_STUNDE` / `EMAIL_LIMIT_PRO_TAG` / `EMAIL_REPLY_TO_NUTZER` | optional in `.env.prod` | Versandlimit je Mandant (Default 30/h, 100/Tag, `0` = aus) und Reply-To; Details in `docs/email-zustellung.md`. | Defaults prüfen; sie sind eine Annahme. |
