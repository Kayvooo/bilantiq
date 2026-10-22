# Backup und Restore

Stand: 14. Oktober 2026. und 2.5 (Restore-Test), Voraussetzung für 3.1 und alle Migrationen.

> **Hinweis zum Selbst-Hosting-Modell (22. Oktober 2026):** Bilantiq hat keinen zentralen Speicher und kein Backup durch das
> Projekt. Wer eine Instanz betreibt, sichert Datenbank, Dateien (`STORAGE_DIR`, Volume `backend_data`) und die
> Anwendungsschlüssel selbst. Kurzfassung und Einordnung: [self-hosting.md](self-hosting.md), Abschnitte 3, 4 und 8. Die
> Begriffe „Release-Plan“, „Owner“ (hier: Betreiber) und „Release“ unten stammen aus der Planung eines gehosteten Dienstes.

Skripte: `scripts/backup.sh`, `scripts/restore.sh`, `scripts/restore-test.sh`. Überwachung: `scripts/healthcheck.sh` (siehe `docs/betrieb-monitoring.md`).

## Was gesichert wird und was nicht

| Gesichert | Nicht gesichert (getrennt aufbewahren!) |
| --- | --- |
| PostgreSQL-Datenbank (`pg_dump --clean --if-exists`, enthält Schema, Daten, RLS-Policies, Funktionen, Rechte) | **Anwendungsschlüssel**: `DATA_ENCRYPTION_KEYS`, `FIELD_ENCRYPTION_KEY`, `BLIND_INDEX_SECRET`, `EMAIL_LOOKUP_SECRET`, `JWT_SECRET` (Secrets-Verzeichnis, `.env.prod`) |
| Upload-Volume `bilantiq_backend_data` (Belege, Logos, Briefpapier, Importdateien) | Datenbankrollen (z. B. `bilantiq_runtime`): Rollen gehören zum Cluster, nicht zur Datenbank |
| | Caddy-Zertifikate (werden neu bezogen) |

**Ohne die Anwendungsschlüssel sind Spaltenwerte (verschlüsselt) und die E-Mail-Suche nach einem Restore unlesbar.** Die
Schlüssel gehören offline an mindestens zwei getrennte Orte (Passwortmanager plus Papier/Tresor) und **nicht** in dasselbe
Backup-Ziel wie die Datenbank-Sicherungen. Beim Schlüsselwechsel (Rotation) die alten Schlüssel im Ring behalten
(siehe `docs/server-rollout.md`, `docs/security-production.md`).

## Einmalige Einrichtung

1. **age-Schlüsselpaar** auf einem Rechner erzeugen, der NICHT der Server ist:
   ```
   age-keygen -o bilantiq-backup.key        # gibt "Public key: age1..." aus
   ```
   Der private Schlüssel (`bilantiq-backup.key`) wird nur für Restore und Restore-Test gebraucht: offline an zwei Orten sichern,
   nie auf den Server, nie ins Repo. Verlust bedeutet: alle Backups sind unbrauchbar. Mehrere Empfänger sind möglich
   (`BACKUP_AGE_RECIPIENT="age1... age1..."` oder `BACKUP_AGE_RECIPIENTS_FILE`), z. B. ein zweiter Schlüssel in einem Bankschließfach.
2. Auf dem Server `age` installieren (`apt install age`), den **öffentlichen** Schlüssel eintragen (`/etc/bilantiq/backup.env`).
3. Off-site-Ziel: ein Server/Speicher **eines anderen Anbieters**, per SSH-Schlüssel mit eigenem Benutzer.
   Empfehlung: Schlüssel auf dem Ziel auf das Backup-Verzeichnis beschränken (`restrict`, `command="rrsync ..."`), am Ziel
   Aufbewahrung/Löschung selbst regeln (Versionierung oder Snapshots), damit ein kompromittierter Produktionsserver die Kopien nicht löschen kann.
   Das Skript benutzt **kein** `rsync --delete`.
4. Timer einrichten (`docs/betrieb-monitoring.md`), danach einmal manuell laufen lassen.

## Backup-Lauf

```
cd /opt/bilantiq
BACKUP_AGE_RECIPIENT=age1... OFFSITE_TARGET=backup@host:/pfad/ ./scripts/backup.sh
```

Wichtige Einstellungen (Umgebungsvariablen): `ENV_FILE` (Standard `.env.prod`), `COMPOSE_FILE`, `BACKUP_DIR` (Standard `./backups`),
`RETENTION_DAYS` (14), `MIN_KEEP` (3), `OFFSITE_TARGET`, `OFFSITE_SSH_OPTS`, `REQUIRE_OFFSITE` (1; Staging: 0), `VOLUME_NAME`,
`DB_MIN_BYTES`, `MIN_FREE_MB`. Je Lauf entstehen `db_<TS>.sql.gz.age`, `uploads_<TS>.tar.gz.age`, `manifest_<TS>.sha256`
(Prüfsummen der Chiffrate) sowie die Marker `.last_success` und `.last_offsite_success`. Ohne Off-site-Ziel endet das Skript
mit Exit 2 (lokal vorhanden, aber nicht off-site), außer `REQUIRE_OFFSITE=0`.

### Ergebnis der kritischen Durchsicht (was am alten Skript fehlte und jetzt behoben ist)

| Befund im alten Stand | Änderung |
| --- | --- |
| Bei Abbruch blieb eine halbe `.age`-Datei, die wie ein gültiges Backup aussah | Schreiben nach `*.part`, Umbenennen erst nach Prüfung, `trap`-Aufräumen |
| Leerer/zu kleiner Dump wurde nur über `[ -s ]` der verschlüsselten Datei geprüft (ein leerer Dump ergibt trotzdem eine nichtleere `.age`-Datei) | Größe des komprimierten Dumps wird gemessen, unter `DB_MIN_BYTES` wird verworfen; `age`-Header wird geprüft |
| Fehlte das Docker-Volume, legte `docker run -v` ein **leeres** Volume an und sicherte "erfolgreich" nichts | `docker volume inspect` vorab, sonst Fehler |
| Retention löschte rein nach Alter: ein wochenlang fehlschlagendes Backup löschte irgendwann alle guten Stände | Die neuesten `MIN_KEEP` Sicherungen bleiben immer; Sicherungssätze (DB, Uploads, Manifest) werden zusammen entfernt |
| Keine Prüfsummen | `manifest_<TS>.sha256` je Lauf; `restore.sh`, `restore-test.sh` und `healthcheck.sh` prüfen sie |
| Fehlendes Off-site war nur eine Warnung bei Exit 0 | `REQUIRE_OFFSITE=1` (Standard) macht es zum Fehler; Marker für den Healthcheck |
| Kein Erfolgsnachweis für Monitoring | `.last_success`/`.last_offsite_success` |
| `source .env.prod` führte die Env-Datei als Shell aus (Compose-Env-Dateien sind keine Shell-Syntax; ein Wert mit Leerzeichen oder `$(...)` bricht oder führt Code aus) | Nur `POSTGRES_USER`/`POSTGRES_DB` werden per `grep` gelesen |
| Kein Schutz gegen versehentlich eingetragenen privaten Schlüssel oder Tippfehler im Empfänger | Empfänger muss mit `age1` beginnen; `AGE-SECRET-KEY-` wird abgelehnt |
| Keine Sperre gegen parallele Läufe, kein Platzcheck | `flock`, Mindestplatz `MIN_FREE_MB` |
| `restore.sh`: Einspielen mit `ON_ERROR_STOP` ohne Transaktion, halb wiederhergestellte Datenbank bei Fehler möglich | Ein Import in **einer** Transaktion; `COMMIT` wird nur gesendet, wenn Entschlüsseln und Entpacken vollständig gelangen (ein abgeschnittener Datenstrom committet nicht) |
| `restore.sh`: keine Prüfsumme, kein Hinweis auf laufendes Backend, kein Abschlussnachweis | Manifest-Prüfung, Warnung bei laufendem Backend, Ausgabe des Alembic-Stands |

Ausdrücklich **nicht** geändert: `pg_dump --clean --if-exists` (Einspielen überschreibt die Datenbank, deshalb die Rückfrage
"JA" im `restore.sh`), die Pflicht zur Verschlüsselung (es gibt weiterhin keinen Klartext-Modus).

## Restore-Test (Pflicht vor dem Release, danach regelmäßig)

Er läuft auf einer **isolierten Wegwerf-Postgres** (Docker-Container ohne Netzwerk, oder lokale Binaries mit nur einem
Unix-Socket) und berührt weder Produktion noch Staging:

```
BACKUP_AGE_IDENTITY_FILE=/pfad/bilantiq-backup.key \
EXPECT_MIN="mandanten=1,users=1" \
  ./scripts/restore-test.sh backups/db_<TS>.sql.gz.age backups/uploads_<TS>.tar.gz.age
```

Er prüft: Prüfsumme gegen das Manifest, Einspielen ohne Fehler (fehlende Rollen aus dem Dump werden als `NOLOGIN` angelegt),
Alembic-Stand gleich dem Head des Repos, Tabellen vorhanden, Row-Level-Security aktiv mit Policies, Zeilenzahlen aller Tabellen
(nur Zahlen, `EXPECT_MIN` erzwingt Mindestwerte), Upload-Archiv lesbar. Er misst die Dauer. Ergebnis `RESTORE-TEST: BESTANDEN`
oder Exit 1. Wenn der Test auf einer anderen Maschine als dem Server läuft (empfohlen), dort `age`, `psql`/Docker und das Repo bereitstellen und die
Backup-Dateien vom Off-site-Ziel holen: Das testet gleichzeitig, dass die Off-site-Kopie brauchbar ist.

**Nicht automatisch geprüft** (manuell nach dem Test, siehe `docs/rollback.md`): Login mit einem Konto, Entschlüsselung der
Spaltenwerte mit den Anwendungsschlüsseln, ein Rechnungs-PDF. Dafür muss die Anwendung mit einer Kopie der Schlüssel gegen
die wiederhergestellte Datenbank laufen (Staging-Stack). Erst damit gilt als erfüllt.

Häufigkeit: einmal vor dem Release, einmal nach jeder Migration, die Daten umschreibt (0036), danach monatlich.

### Was bisher tatsächlich ausgeführt wurde (14.10.2026, Entwicklungsrechner)

- **Echtes `age` 1.2.1** (aus dem offiziellen Go-Modul gebaut) und **echtes PostgreSQL** (`initdb`, `pg_dump`, `psql`).
- Quelle: eine temporäre Postgres (Port 54331) mit den Migrationen bis `0036`, der Laufzeitrolle aus `runtime_rolle.sql` und
  synthetischen Daten, erzeugt über die Anwendung selbst (3 Mandanten, 3 Nutzer, 6 Rechnungen).
- `backup.sh` lief gegen diese Quelle. **Docker und `rsync` gab es nicht**: Beide wurden durch kleine Test-Attrappen ersetzt, die nur die von den Skripten benutzten Aufrufe auf die lokale Postgres bzw. `cp` abbilden. Die Docker-spezifischen Zeilen (`compose exec`, `docker run ... tar`, `volume inspect`) sind damit **nicht gegen echtes Docker** ausgeführt, nur ihre Aufrufform.
- `restore-test.sh` (Engine "native", Port 54330, nur Unix-Socket) lief mit `EXPECT_MIN="mandanten=3,users=3,invoices=6"`: bestanden. Gefunden: 45 Tabellen, 37 mit RLS, 37 Policies, 3 `bq_*`-Funktionen, Alembic `0036`; fehlende Rollen `bilantiq` und `bilantiq_runtime` wurden angelegt (PostgreSQL lehnt `OWNER TO`/`GRANT` auf nicht vorhandene Rollen ab; dass der Import ohne diesen Schritt tatsächlich scheitert, habe ich nicht gesondert nachgestellt). Dauer: Entschlüsseln und Einspielen 0 s, gesamt 1 s. **Das sagt nichts über die Dauer mit echten Daten**: der Dump hatte 144 KB.
- Negativfälle liefen wie erwartet: falscher Schlüssel (Exit 1), manipuliertes Chiffrat (Prüfsumme schlägt an, Exit 1), verbotene Ports 5432/54329, zu hohe `EXPECT_MIN`, abweichender Alembic-Stand (Exit 1; mit `ALLOW_OLDER_HEAD=1` nur Warnung).
- `restore.sh` gegen eine zweite Datenbank derselben Test-Postgres (über die Docker-Attrappe): Erfolg; abgeschnittener Dump und falscher Schlüssel ließen die vorhandene Zieldatenbank unverändert (6 Rechnungen blieben).
- **Nicht ausgeführt:** Engine "docker" von `restore-test.sh`, jeder Lauf auf dem echten Server, Wiederherstellung des Upload-Volumes, Mehr-Gigabyte-Dumps, Wiederherstellung über Postgres-Hauptversionen hinweg.

## Zielwerte, die Sie als Betreiber festlegen müssen

- **RPO** (wie viele Stunden Daten dürfen verloren gehen): mit einem Backup pro Nacht bis zu 24 h. Wenn das zu viel ist, häufiger sichern oder WAL-Archivierung einführen (nicht vorbereitet).
- **RTO** (wie schnell muss es wieder laufen): nicht gemessen. Aus der Dauer eines Restore-Tests auf einer Testinstanz mit realistischer Datenmenge ableiten und in `docs/rollback.md` eintragen.
