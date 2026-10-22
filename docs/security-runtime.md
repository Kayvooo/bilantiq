# Datenbankrechte: Migration und laufende API

## Neue Installationen

Beide Compose-Profile (`prod` und `home`) verwenden zwei Verbindungen:

| Secret | Benutzer | Verwendung |
| --- | --- | --- |
| `migration_database_url` | initialer PostgreSQL-Administrator | ausschließlich einmaliger Dienst `migrate` |
| `database_url` | eigene Rolle `bilantiq_runtime` | laufende API; im Migrator zur Einrichtung als `runtime_database_url` |

`scripts/init-secrets.sh` erzeugt beide URLs mit unterschiedlichen Passwörtern. Abweichende Datenbanknamen/-rollen müssen
beim Aufruf über `POSTGRES_USER`, `POSTGRES_DB` und optional `POSTGRES_RUNTIME_USER` übergeben werden, passend zur
Compose-Konfiguration. Zulässig sind kleine SQL-Bezeichner (`a-z`, `0-9`, `_`, kein führender Ziffernwert).

`migrate` führt Alembic aus, richtet die Laufzeitrolle ein und prüft ihre effektiven Rechte. Erst nach erfolgreichem
Abschluss startet die API. Der API-Container enthält weder das Admin-Secret noch eine automatische Schema-Migration.
Der Migrator läuft einmalig als UID 1000 ohne Capabilities, ohne Ports und ohne Dateidatenvolume. Er benötigt
Kryptoschlüssel für bestehende Datenmigrationen; nach Abschluss bleibt kein Verwaltungsprozess aktiv.

Die Startprüfung gilt in `APP_ENV=staging|production`. Sie lehnt insbesondere Superuser, BYPASSRLS, Verwaltungsattribute,
Rollenmitgliedschaften, Objekt-/Datenbankbesitz, Schema-CREATE und verändernde Audit-Rechte ab. Ein Fehler verhindert den
Start. SQLite und eine ungeprüfte DB-Verbindung sind ausschließlich für `APP_ENV=development` vorgesehen.

## Secret-Rechte bei lokalen Compose-Dateien

Lokale Compose-Secrets sind Datei-Bind-Mounts. Sie übernehmen die Host-Rechte; die Angabe von uid/gid im Compose-Secret
ist hier kein Ersatz für einen passenden Eigentümer. Das Backend läuft als UID 1000.

Bei Einrichtung als root setzt `init-secrets.sh` die Dateien für **API und Migrator** auf UID/GID 1000 und 0600. Das äußere
Verzeichnis bleibt 0700; die Admin-URL wird ausschließlich in den Migrator gemountet. Bei Aufruf als Benutzer 1000 funktionieren die
API-Dateien ebenfalls. Andere Benutzer müssen die Einrichtung mit root-Rechten ausführen. Keine Dateien auf 0644 setzen.
`BILANTIQ_APP_UID` ist nur für eigene Images mit entsprechend geänderter Container-UID gedacht.

## Bestehende Installation umstellen

Vorher: aktuelles verschlüsseltes Daten-/Dateibackup und getrennte Sicherung aller Schlüssel; Restore-Fähigkeit prüfen.
Ein Wartungsfenster nutzen und die alte API stoppen. Vorhandene Volumes und Kryptoschlüssel bleiben erhalten.

Wenn `database_url` bereits eine unprivilegierte eigene Laufzeitrolle enthält, diese beibehalten und eine getrennte
Admin-Verbindung in `migration_database_url` hinterlegen. Eine Rolle mit vorhandenen Eigentumsrechten/Mitgliedschaften
wird bewusst nicht automatisch umfunktioniert; dafür eine neue, eigene Rolle verwenden.

Wenn `database_url` noch den ursprünglichen Administrator enthält, ist der folgende Umstieg **einmalig** nötig
(Pfade anpassen; existiert `.before-runtime` bereits, vorher den früheren Versuch prüfen):

```bash
sudo test ! -e /opt/bilantiq/secrets/database_url.before-runtime
sudo mv /opt/bilantiq/secrets/database_url /opt/bilantiq/secrets/database_url.before-runtime
sudo install -o root -g root -m 600 /opt/bilantiq/secrets/database_url.before-runtime /opt/bilantiq/secrets/migration_database_url
sudo BILANTIQ_SECRETS_DIR=/opt/bilantiq/secrets ./scripts/init-secrets.sh
```

Bei abweichenden `POSTGRES_USER`/`POSTGRES_DB` diese dem letzten Aufruf zusätzlich mitgeben. Das Skript erhält vorhandene
Secrets und erzeugt nur die fehlende neue Laufzeit-URL. Es ändert nicht das Passwort eines bestehenden PostgreSQL-Volumes.
Nach dem Umstieg sind Alt-URL und Admin-URL weiterhin sensible Betriebsgeheimnisse.

Danach für das Produktionsprofil (Heimserver entsprechend mit `.env.home`/`docker-compose.home.yml`):

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config > /dev/null
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build --force-recreate migrate backend caddy
docker compose --env-file .env.prod -f docker-compose.prod.yml logs migrate backend
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T backend python -m app.core.runtime_security
```

Auch bei künftigen Releases `migrate` erneut ausführen/recreaten, bevor die neue API Fachanfragen annimmt. Alte API vorher
stoppen; neue Migrationen sind nicht automatisch mit einer parallel laufenden älteren API kompatibel. Ein fehlgeschlagener
Migrator muss zuerst untersucht werden; die API darf dann nicht manuell unter Umgehung der Abhängigkeit gestartet werden.

## Abnahme und Rückweg

- `migrate` endet erfolgreich; API-Startprüfung erfolgreich; kein Admin-Secret im API-Container.
- Registrierung/Einladung, Login/MFA, Rechnung, Originalbeleg-Download und Export mit Testdaten prüfen.
- PostgreSQL-RLS-Suite mit unprivilegierter Rolle ausführen; reine SQLite-Tests prüfen diese Grenze nicht.
- Bei Fehlern die API geschlossen halten. Rechte, Secret-Eigentümer und Migrationsergebnis prüfen; Schlüssel nicht ersetzen.
- Ein Code-Rollback nach Schemaänderungen benötigt die jeweilige Migrations-/Restore-Strategie. Nicht durch Rückgabe der
  Admin-Verbindung an die API „reparieren“. Keine Datenvolumes löschen.

Grenze: Der Schutz überprüft die Datenbankrolle bei jedem Prozessstart, nicht kontinuierlich nach späteren manuellen
Rechteänderungen. Administratorzugriff bleibt separat abzusichern. RLS-Kontext kommt aus der Anwendung und ist keine
unabhängige Grenze gegen einen vollständig übernommenen Backend-Prozess.
