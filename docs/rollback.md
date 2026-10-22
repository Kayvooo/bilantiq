# Rollback, Wiederherstellung, Notfall

Anleitung für Betreiber einer eigenen Instanz (siehe `docs/self-hosting.md`). Setzt voraus, dass `docs/backup-restore.md`
eingerichtet ist. Alle Befehle laufen im Repo-Verzeichnis auf Ihrem Server (im Beispiel `/opt/bilantiq`). Nichts davon wurde
auf einem echten Server ausgeführt; testen Sie den Ablauf einmal, bevor Sie ihn brauchen.

Kürzel für die Befehle unten: `dc() { docker compose --env-file .env.prod -f docker-compose.prod.yml "$@"; }`

## Wann zurückrollen (Kriterien)

Sofort handeln bei: Verdacht auf Datenverlust, Verdacht auf Mandanten-Datenleck (Konto A sieht Daten von B), Login für alle defekt,
Migration schlägt fehl, Healthcheck dauerhaft kritisch nach einem Release. Im Zweifel erst sperren, dann analysieren.

## Schritt 0: Sperren (für alle Szenarien)

1. **Registrierung sperren.** In `.env.prod` `REGISTRATION_MODE=closed` setzen und das Backend neu starten
   (`dc up -d backend`). Standardmäßig darf sich ohnehin nur das erste Konto selbst registrieren.
2. **Alles sperren, auch Logins:** den Reverse-Proxy anhalten (`dc stop caddy`). Die Instanz ist dann von außen nicht erreichbar,
   Daten und Zertifikate bleiben erhalten. Zurück mit `dc up -d caddy`.
3. **Backend anhalten**, wenn Daten gefährdet sind: `dc stop backend`.

## Szenario A: fehlerhaftes Release, **keine** Migration gelaufen

1. `git fetch --tags && git checkout <vorheriger-tag>`
2. `dc build backend caddy && dc up -d backend caddy`
3. Prüfen: `curl -fsS https://api.<domain>/health/ready`, Login, Rechnungsliste.

## Szenario B: Migration gelaufen oder fehlgeschlagen

Das `backend/Dockerfile` führt beim Start `alembic upgrade head` aus. Ein älteres Image kennt neuere Migrationsstände nicht und
startet gegen eine bereits migrierte Datenbank in der Regel nicht (Alembic meldet unbekannte Revision). `downgrade()` von
0036 ist absichtlich nicht implementiert. Rollback bedeutet deshalb: **Datenbank aus dem Backup, dann alten Stand starten.**

1. Schritt 0 (mindestens `dc stop backend`).
2. Das **letzte Backup vor der Migration** wählen (vor jedem Update direkt vor der Migration erstellen, siehe `docs/self-hosting.md`, Abschnitt Updates). Verlust: alle Änderungen seit diesem Backup.
3. Restore, siehe unten ("Datenbank wiederherstellen").
4. `git checkout <vorheriger-tag> && dc build backend && dc up -d backend`
5. Ursache klären, bevor erneut migriert wird; Migration vorher auf einer Testinstanz mit einer Kopie des Datenbankschemas wiederholen.

## Datenbank wiederherstellen (eigener Server)

Vorher einmal als Probe mit `scripts/restore-test.sh` auf einer anderen Maschine.

```
dc stop backend
BACKUP_AGE_IDENTITY_FILE=/pfad/zum/privaten/age-schluessel ./scripts/restore.sh backups/db_<TS>.sql.gz.age
```

`restore.sh` prüft die Prüfsumme, fragt nach "JA", spielt in einer Transaktion ein (bei Fehler bleibt der alte Stand) und zeigt
den Alembic-Stand. Fehlen Rollen aus dem Dump (z. B. `bilantiq_runtime`) im Cluster, vorher anlegen
(`backend/scripts/runtime_rolle.sql`, siehe `docs/server-rollout.md` Schritt 3); der Import bricht sonst ab, und weil er in einer Transaktion läuft, bleibt der alte Stand erhalten.

**Upload-Volume** (Belege, Logos): nur wenn Dateien betroffen sind. Das ersetzt den gesamten Inhalt des Volumes:

```
age -d -i /pfad/zum/privaten/age-schluessel backups/uploads_<TS>.tar.gz.age \
  | docker run --rm -i -v bilantiq_backend_data:/data alpine:3.20 sh -c 'find /data -mindepth 1 -delete && tar xzf - -C /data'
```

Dieser Befehl wurde nicht gegen echtes Docker ausgeführt. Danach: `dc up -d backend`, dann Prüfungen:

- `curl -fsS https://api.<domain>/health/ready`
- Login mit einem Konto, Rechnungsliste, ein Rechnungs-PDF (beweist: Datenbank, Anwendungsschlüssel und Uploads passen zusammen)
- `dc logs backend --tail 100` ohne `permission denied` / `InsufficientPrivilege`
- `dc exec -T postgres psql -U bilantiq -d bilantiq -Atc "select version_num from alembic_version"`

## Szenario C: Login für alle defekt

Typische Ursachen: Anwendungsschlüssel falsch/vertauscht (Rechnungs-PDF und Login schlagen gleichzeitig fehl), Laufzeitrolle ohne Rechte
(`permission denied` im Log), JWT-Secret geändert (alle Sitzungen ungültig, Neuanmeldung wäre dann aber möglich).
1. `dc logs backend --tail 200`.
2. Secrets-Dateien gegen die gesicherten Originale vergleichen (Prüfsummen, nicht Inhalt anzeigen): `sha256sum /opt/bilantiq/secrets/*`.
3. Nach `docs/server-rollout.md` Schritt 3 die Rechte der Laufzeitrolle erneut setzen (nach jeder Migration nötig).
4. Hilft nichts: Szenario B.

## Szenario D: Verdacht auf Datenverlust oder Mandanten-Datenleck

1. Schritt 0 vollständig (Proxy und Backend stoppen). Nichts löschen, Beweise sichern:
   `dc logs --no-color > /root/vorfall-<datum>-logs.txt`, Audit-Log aus der Datenbank exportieren
   (`dc exec -T postgres psql -U bilantiq -d bilantiq -c "\copy (select id, mandant_id, user_id, aktion, zeitpunkt from audit_log_eintraege order by zeitpunkt) to stdout csv header" > /root/vorfall-<datum>-audit.csv`).
2. Letzten guten Backup-Stand und Zeitpunkt des Vorfalls bestimmen.
3. **Meldefristen (keine Rechtsberatung):** Sie sind als Betreiber selbst verantwortlich. Datenpanne mit Risiko für Betroffene: Meldung an die zuständige Datenschutz-Aufsichtsbehörde **innerhalb von 72 Stunden** nach Bekanntwerden (Art. 33 DSGVO); Benachrichtigung der Betroffenen bei hohem Risiko (Art. 34). Bei Verdacht frühzeitig Anwalt oder Datenschutzbeauftragte einbinden. Ablauf und Vorlagen: `docs/incident-response.md`.
4. Wiederinbetriebnahme erst nach Ursachenanalyse und, bei Datenleck, nach einem Test mit zwei getrennten Mandanten.

## Szenario E: Anwendungsschlüssel verloren

Ohne `DATA_ENCRYPTION_KEYS` (und `FIELD_ENCRYPTION_KEY`, `BLIND_INDEX_SECRET`) sind verschlüsselte Spalten **nicht wiederherstellbar**,
auch nicht aus dem Backup. Deshalb: Schlüssel offline an zwei Orten, getrennt vom Datenbackup (`docs/backup-restore.md`). Beim Verlust
bleibt nur: Schlüssel aus den Offline-Kopien holen. Es gibt keinen Umweg.

## Notfallzugang und Wiederherstellungswege

Diese Tabelle ausfüllen und **ausgedruckt/offline an zwei Orten** aufbewahren. Keine Passwörter hineinschreiben, nur wo sie liegen.

| Was | Wo / wie | Zweiter Weg |
| --- | --- | --- |
| Server-Konsole des Hosters (Rescue/VNC/KVM) | | |
| Hoster-Konto (2FA, Wiederherstellungscodes) | | |
| SSH-Schlüssel für den Server | | |
| DNS-/Registrar-Konto | | |
| Domain-Inhaber-Kontakt und Autorisierungscode | | |
| age-Privatschlüssel (Backup) | | |
| Anwendungsschlüssel (`DATA_ENCRYPTION_KEYS` u. a.) | | |
| Off-site-Backup-Ziel (Zugang) | | |
| SMTP-Anbieter (2FA) | | |
| GitHub-Konto (Repo) | | |
| Passwortmanager (Master, Notfallkontakt) | | |
| Wer kann im Notfall vertreten? | | |

## Was nicht vorbereitet bzw. nicht getestet ist

- Keiner dieser Abläufe wurde auf dem echten Server oder mit Docker ausgeführt. `restore.sh`/`restore-test.sh` laufen nur in den im Backup-Doc genannten Testumgebungen.
- Ein Rollback-Zeitaufwand (RTO) ist nicht gemessen. Ein Restore-Test auf einer Testinstanz mit realistischer Datenmenge liefert den ersten echten Wert.
