# Bilantiq zu Hause betreiben, erreichbar nur über ein VPN (Tailscale)

Für eine Person oder einen kleinen Kreis: Bilantiq läuft auf einem Rechner, der meistens an ist (Laptop, Mini-PC, Heimserver).
Von unterwegs und vom Handy erreichen Sie es über ein VPN. Die Instanz ist **nicht im Internet erreichbar**, es gibt keine
Port-Freigabe im Router und keine öffentliche Domain.

> **Stand:** Die Compose-Datei ist mit `docker compose config` auf Gültigkeit geprüft. Der Stack wurde in der Entwicklungsumgebung
> **nicht gestartet** (kein Docker-Dienst verfügbar), und `tailscale serve` wurde nicht ausprobiert. Die Anleitung ist ein erster
> Stand und wird nach den ersten echten Läufen korrigiert. Meldungen und Fehler bitte als Issue.

## So hängt es zusammen

```
Handy/Laptop ──(Tailscale, verschlüsselt)──> tailscale serve (HTTPS, Zertifikat von Tailscale)
                                                  │
                                                  v
                                       127.0.0.1:8080  Caddy  ──"/"──> Oberfläche
                                                         └───"/api"──> Backend ──> Postgres
```

- Caddy lauscht nur auf `127.0.0.1:8080` des Rechners. Ohne Tailscale davor kommt niemand von außen heran.
- `tailscale serve` liefert HTTPS mit einem echten Zertifikat für den Namen `rechner.tailnet-name.ts.net`. Es gibt keine
  Browser-Warnung und kein selbst gebautes Zertifikat.
- Oberfläche und API haben dieselbe Adresse (`/api`), deshalb braucht die Oberfläche keinen festen Hostnamen.

## Was Sie brauchen

- Docker mit Compose (Arch: `sudo pacman -S docker docker-compose`, dann `sudo systemctl enable --now docker` und den eigenen
  Benutzer in die Gruppe `docker` aufnehmen).
- Tailscale auf dem Server-Rechner und auf den Geräten, mit denen Sie zugreifen. Im Tailscale-Adminbereich unter DNS müssen
  **MagicDNS** und **HTTPS-Zertifikate** aktiviert sein (sonst funktioniert `tailscale serve` mit HTTPS nicht).
- Den Quellcode: `git clone https://github.com/Kayvooo/bilantiq.git && cd bilantiq`.

## 1. Schlüssel erzeugen

Die Schlüssel liegen in einem Ordner in Ihrem Benutzerverzeichnis, nicht im Repository:

```bash
BILANTIQ_SECRETS_DIR=$HOME/.config/bilantiq/secrets ./scripts/init-secrets.sh
```

**Sichern Sie sofort `data_encryption_keys` aus diesem Ordner** (Passwortmanager, ausgedruckt). Ohne diesen Schlüssel sind alle
verschlüsselten Daten unwiederbringlich verloren, auch mit intaktem Backup.

Hinweis zu den Rechten: Das Backend läuft im Container als Benutzer mit der Nummer 1000. Die Secret-Dateien müssen für ihn lesbar
sein. Gehören sie Ihnen und Sie sind Benutzer 1000 (`id -u` zeigt 1000), passt das. Haben Sie eine andere Nummer, ändern Sie
die Dateirechte auf 644 (`chmod 644 ~/.config/bilantiq/secrets/*`) und lassen den Ordner selbst auf 700.

## 2. Einstellungen

```bash
cp .env.home.example .env.home
```

Dann in `.env.home` die drei Stellen mit dem Beispielnamen ersetzen und den Secret-Ordner eintragen:

1. Ihren Tailscale-Namen herausfinden: `tailscale status --json | grep -m1 DNSName` zeigt `"DNSName": "rechner.tailnet-name.ts.net."`.
   Ohne Punkt am Ende in `TRUSTED_HOSTS_RAW`, `CORS_ALLOWED_ORIGINS_RAW` (mit `https://`) und `APP_FRONTEND_URL` eintragen.
2. `BILANTIQ_SECRETS_DIR` auf Ihren echten Ordner setzen (`/home/IHR-NAME/.config/bilantiq/secrets`).

## 3. Starten

```bash
docker compose --env-file .env.home -f docker-compose.home.yml up -d --build
```

Der erste Start baut die Images (Backend, Frontend) und dauert einige Minuten. Prüfen:

```bash
docker compose --env-file .env.home -f docker-compose.home.yml ps
curl -s http://127.0.0.1:8080/api/health        # erwartet: {"status":"ok"}
```

Bei Problemen: `docker compose --env-file .env.home -f docker-compose.home.yml logs backend --tail 100`. Der Speicher-Check beim
Start meldet Rechteprobleme im Klartext.

## 4. Über Tailscale freigeben

```bash
sudo tailscale serve --bg 8080
tailscale serve status
```

`tailscale serve status` zeigt die HTTPS-Adresse (`https://rechner.tailnet-name.ts.net`). Öffnen Sie sie im Browser auf dem
Laptop und auf dem Handy (Tailscale muss dort verbunden sein). Das erste Konto legen Sie über „Registrieren" an. Richten Sie danach unter
„Sicherheit & Datenschutz" die Zwei-Faktor-Anmeldung ein und speichern Sie die Wiederherstellungscodes.

**Nicht verwenden: `tailscale funnel`.** Funnel stellt die Adresse ins öffentliche Internet. Das wollen Sie hier nicht.
Rückgängig machen: `sudo tailscale serve reset`.

Das Handy können Sie über „Zum Startbildschirm hinzufügen" als App ablegen (PWA).

## Betrieb

- **Neustart:** Die Container starten mit Docker automatisch wieder (`restart: unless-stopped`). `tailscale serve --bg`
  bleibt über Neustarts erhalten.
- **Laptop als Server:** Der Rechner darf nicht schlafen. Stellen Sie den Deckel (Energieeinstellungen bzw.
  `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`) und das Netzteil entsprechend ein. Ist der Rechner aus, ist Bilantiq
  aus.
- **Updates:** `git pull`, dann denselben `docker compose ... up -d --build`. Vorher ein Backup. Datenbankänderungen laufen beim
  Start automatisch (siehe `docs/self-hosting.md`, Abschnitt Updates).
- **Backups** (verschlüsselt mit `age`, Pflicht, denn ein einzelner Rechner ist ein einzelner Ausfallpunkt):

  ```bash
  ENV_FILE=.env.home COMPOSE_FILE=docker-compose.home.yml BACKUP_AGE_RECIPIENT="age1..." ./scripts/backup.sh
  ```

  Legen Sie die Sicherung auf ein **anderes** Medium (externe Platte, anderer Rechner). Probieren Sie die Wiederherstellung
  einmal aus (`docs/backup-restore.md`). Die Skripte nehmen `ENV_FILE` und `COMPOSE_FILE` aus der Umgebung.
- **E-Mail** ist abgeschaltet, solange kein SMTP eingetragen ist. Konto-Wiederherstellung ohne E-Mail: `docs/self-hosting.md`.

## Grenzen (ehrlich)

- Wer in Ihrem Tailscale-Netz ist, kann die Seite erreichen. Teilen Sie das Netz mit niemandem, dem Sie die Buchhaltung
  nicht anvertrauen würden, und prüfen Sie in den Tailscale-Zugriffsregeln (ACL), wer Zugriff hat. Die Anmeldung in Bilantiq bleibt
  der zweite Schutz.
- Die Datenbank läuft mit dem Eigentümerkonto. Die zusätzliche Mandantentrennung per Postgres-Rolle (`docs/server-rollout.md`) ist hier
  nicht eingerichtet. Für eine Instanz mit einer Firma spielt das praktisch keine Rolle; bei mehreren Firmen auf einer Instanz bitte
  nachlesen.
- Tailscale ist ein Dienst eines Drittanbieters (Konto, Koordinationsserver). Der Datenverkehr selbst ist Ende-zu-Ende
  verschlüsselt. Wer das nicht möchte, kann das Muster mit reinem WireGuard nachbauen; dafür gibt es hier keine Anleitung.
- Der Rechner ist Ihr Server: Festplattenverschlüsselung, Updates, Backups und der Schutz des Schlüssels liegen bei Ihnen.
