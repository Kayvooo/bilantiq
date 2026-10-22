# Betrieb: Health, Monitoring, Alarm, Logs

Stand: 14. Oktober 2026. und 2.8 (Log-Aufbewahrung).

## Endpunkte

| URL | Zweck | Antwort |
| --- | --- | --- |
| `https://api.<domain>/health` | Lebt der Prozess? (kein DB-Zugriff) | `200 {"status":"ok"}` |
| `https://api.<domain>/health/ready` | Ist die Datenbank erreichbar? | `200 {"status":"ok"}` oder `503 {"status":"unavailable"}` |

Beide Endpunkte brauchen keine Anmeldung und liefern bewusst nur diesen einen Wert: keine Versionen, Hostnamen,
Fehlertexte, Mandanten- oder Personendaten. Bei einem DB-Ausfall steht im Backend-Log nur der Fehlertyp (kein Text mit
Zugangsdaten). Für externes Monitoring `/health/ready` verwenden. Der Host-Header muss zu `TRUSTED_HOSTS_RAW` passen
(das ist bei Aufruf über die öffentliche API-Domain automatisch so).

## scripts/healthcheck.sh

Prüft pro Lauf:

1. Erreichbarkeit von App (`APP_URL`, erwartet das SPA-Wurzelelement), API (`API_URL`, erwartet `"status":"ok"`) und optional Website (`WEBSITE_URL`).
2. TLS-Ablauf in Tagen für `TLS_HOSTS` (Warnung unter 21, kritisch unter 7 Tagen).
3. Festplattenbelegung für `DISK_PATHS` (Warnung ab 80 %, kritisch ab 92 %).
4. Backup: Alter von `$BACKUP_DIR/.last_success` (kritisch über 30 h), Größe und SHA-256-Prüfsumme der neuesten Sicherung (`manifest_<TS>.sha256`), Off-site-Marker `.last_offsite_success`. Beide Marker schreibt `scripts/backup.sh` erst nach vollständigem Erfolg.

Exit-Code: `0` alles in Ordnung, `1` Warnung, `2` kritisch (`64` Konfigurationsfehler).
Optionen: `--dry-run` (prüft und druckt, benachrichtigt nicht), `--test-notify` (schickt nur eine Testnachricht).

Benachrichtigung: nur bei **Änderung** der Problemliste, als Erinnerung nach `REMIND_HOURS` (12 h) und mit einer "wieder in
Ordnung"-Nachricht. Kein Spam alle fünf Minuten.

### Konfiguration (vom Betreiber auszufüllen)

Datei `/etc/bilantiq/healthcheck.env`, Rechte `600`, Eigentümer root. Einfache `KEY=Wert`-Zeilen, werden nicht als Shell
ausgeführt. Umgebungsvariablen haben Vorrang. Alle Werte unten sind Platzhalter.

```
SERVER_NAME=bilantiq-prod
APP_URL=https://app.example.invalid/
API_URL=https://api.example.invalid/health/ready
WEBSITE_URL=https://www.example.invalid/
TLS_HOSTS=app.example.invalid api.example.invalid www.example.invalid
DISK_PATHS=/ /var/lib/docker
BACKUP_DIR=/opt/bilantiq/backups
OFFSITE_EXPECTED=1
STATE_DIR=/var/lib/bilantiq-healthcheck

# Alarmweg 1: Webhook (Wert vom Betreiber eintragen; die URL ist ein Geheimnis)
NOTIFY_WEBHOOK_URL=
NOTIFY_WEBHOOK_FORMAT=text
# Alarmweg 2: E-Mail (braucht `mail` oder `sendmail` auf dem Host, also einen konfigurierten MTA)
NOTIFY_EMAIL=
# Dead-Man's-Switch (siehe Grenzen): URL eines externen Heartbeat-Dienstes
HEARTBEAT_URL=
```

`NOTIFY_WEBHOOK_FORMAT`: `text` sendet `{"text": "..."}` (Slack, Mattermost, Rocket.Chat), `content` sendet
`{"content": "..."}` (Discord), `plain` sendet den Text als Body (z. B. ntfy.sh-Thema aufs Handy).

Alarmweg einmal prüfen (das ist auch Schritt 6 der Go-Live-Checkliste):

```
sudo HEALTHCHECK_CONF=/etc/bilantiq/healthcheck.env /opt/bilantiq/scripts/healthcheck.sh --test-notify
```

Das Skript meldet nur "gesendet". Dass die Nachricht **ankommt**, siehst du am Handy bzw. im Postfach.

### systemd-Timer (empfohlen)

`/etc/systemd/system/bilantiq-healthcheck.service`:

```
[Unit]
Description=Bilantiq Healthcheck
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HEALTHCHECK_CONF=/etc/bilantiq/healthcheck.env
ExecStart=/opt/bilantiq/scripts/healthcheck.sh
# Exit 1/2 ist ein "Befund", kein Dienstfehler; die Meldung schickt das Skript selbst.
SuccessExitStatus=1 2
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/bilantiq-healthcheck
PrivateTmp=true
```

`/etc/systemd/system/bilantiq-healthcheck.timer`:

```
[Unit]
Description=Bilantiq Healthcheck alle 5 Minuten

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
```

Aktivieren:

```
sudo install -d -m 700 /var/lib/bilantiq-healthcheck /etc/bilantiq
sudo systemctl daemon-reload
sudo systemctl enable --now bilantiq-healthcheck.timer
systemctl list-timers bilantiq-healthcheck.timer
journalctl -u bilantiq-healthcheck.service -n 20
```

Backup-Timer (täglich 03:15), `bilantiq-backup.service` + `.timer`:

```
# bilantiq-backup.service
[Unit]
Description=Bilantiq verschluesseltes Backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/bilantiq
EnvironmentFile=/etc/bilantiq/backup.env
ExecStart=/opt/bilantiq/scripts/backup.sh

# bilantiq-backup.timer
[Unit]
Description=Bilantiq Backup taeglich

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

`/etc/bilantiq/backup.env` (Rechte 600): `BACKUP_AGE_RECIPIENT=age1...`, `OFFSITE_TARGET=...`, optional `OFFSITE_SSH_OPTS=...`,
`BACKUP_DIR=/opt/bilantiq/backups`. Das Backup-Skript liest `.env.prod` selbst; `/etc/bilantiq/backup.env` enthält nur
die Backup-Einstellungen. Ein fehlgeschlagenes Backup erkennt der Healthcheck am veralteten `.last_success` (und
systemd zeigt `failed`: `systemctl status bilantiq-backup.service`).

### Alternative: Cron

```
# /etc/cron.d/bilantiq  (Zeile "MAILTO" nur setzen, wenn der Host Mail versenden kann)
*/5 * * * * root HEALTHCHECK_CONF=/etc/bilantiq/healthcheck.env /opt/bilantiq/scripts/healthcheck.sh >/dev/null 2>&1
15 3 * * *  root cd /opt/bilantiq && set -a && . /etc/bilantiq/backup.env && set +a && ./scripts/backup.sh >>/var/log/bilantiq-backup.log 2>&1
```

## Grenzen (wichtig)

- **Ein Skript auf dem Server kann den Ausfall des Servers nicht melden.** Dafür braucht es einen Beobachter außerhalb:
  `HEARTBEAT_URL` (Dienst, der Alarm schlägt, wenn der Ping ausbleibt) und/oder ein externer Uptime-Monitor, der
  `https://api.<domain>/health/ready` von außen abfragt. Welcher Dienst, entscheiden Sie (E-Mail/Handy-Push als Ziel).
  Wer die Daten- und Hostregion eines Heartbeat-Dienstes prüft: Es werden nur Pings ohne Inhalt gesendet.
- Das Skript prüft keine Fehlerquote der Anwendung und keine Antwortzeiten, nur die genannten Punkte.
- Der TLS-Check liest das vom Server präsentierte Zertifikat und prüft das Ablaufdatum, nicht die Vertrauenskette (die Kette prüft der `curl`-Abruf der Erreichbarkeits-URLs).
- Das Skript wurde lokal gegen eine Testinstanz, ein selbstsigniertes Zertifikat (läuft in 2 Tagen ab), einen lokalen Webhook-Empfänger und manipulierte Backup-Verzeichnisse geprüft. Gegen die echten Domains, `mail`/`sendmail` und systemd-Timer auf dem Server wurde es **nicht** ausgeführt.
- Die Unit-Dateien oben wurden mit `systemd-analyze verify` auf Syntax geprüft (mit durch `/usr/bin/true` ersetzten `ExecStart`-Pfaden; die einzige Meldung war, dass `docker.service` auf dem Entwicklungsrechner nicht existiert). Auf einem Zielhost aktiviert wurden sie nicht.

## Logs und Aufbewahrung

Ist-Zustand aus dem Code:

- Die Anwendung schreibt selbst fast nichts ins Log (keine `print`/`logger`-Aufrufe in `app/` außer dem Readiness-Fehlertyp). Personenbezogene Daten oder Secrets werden von der Anwendung nicht geloggt.
- **uvicorn schreibt einen Zugriffslog** (Standard) auf stdout: Client-IP (über `--proxy-headers`), Methode, Pfad, Statuscode. IP-Adressen sind personenbezogene Daten.
- Caddy hat im mitgelieferten Caddyfile keinen Zugriffslog konfiguriert (Caddy loggt Zugriffe nur nach `log`-Direktive).
- Docker speichert stdout in `json-file` ohne Obergrenze, sofern nicht begrenzt.

Empfehlung:

1. Docker-Logs global begrenzen, `/etc/docker/daemon.json` (danach `sudo systemctl restart docker`, Container neu starten):
   ```
   { "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
   ```
   `docker-compose.prod.yml` setzt das nicht je Dienst; die globale `daemon.json` deckt es ab.
2. Aufbewahrungsfrist festlegen: Das ist größenbasiert (hier höchstens 50 MB je Container), keine feste Anzahl Tage. Wer eine Frist in Tagen braucht (z. B. 14 Tage für Zugriffslogs), muss das extern lösen (z. B. journald-Treiber mit `MaxRetentionSec`). Die Frist gehört in das Verzeichnis der Verarbeitungstätigkeiten / die Datenschutzerklärung.
3. Optional: uvicorn ohne Zugriffslog starten (`--no-access-log` im `CMD` des `backend/Dockerfile`) oder Caddy-Log mit IP-Kürzung. Das ändert das Dockerfile und wurde hier nicht angefasst; Entscheidung des Betreibers.
4. Nach dem ersten Staging-Lauf einmal prüfen: `docker compose logs backend | grep -iE 'passwort|password|token|authorization' | head` sollte nichts liefern.
