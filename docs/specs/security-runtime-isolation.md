# Spec: getrennte Datenbankrechte für Migration und API

## Ziel und Annahmen, die ich getroffen habe

- Bilantiq bleibt vollständig selbst hostbar; keine neue Cloud-Abhängigkeit.
- PostgreSQL ist für staging/production Pflicht. SQLite bleibt für lokale Entwicklung und Tests verfügbar.
- Die Compose-Profile für öffentliches Hosting und Heimserver bekommen dieselbe Privilegientrennung.
- Migrationen dürfen Verwaltungsrechte und die für Datenmigrationen benötigten Kryptoschlüssel nutzen. Der laufende
  API-Prozess erhält ausschließlich eine eigene Laufzeitverbindung; die Admin-Verbindung wird dort nicht gemountet.
- Bestehende Schlüssel und Daten dürfen durch den Upgrade-Weg weder ersetzt noch gelöscht werden.

## Problem

`init-secrets.sh` erzeugte `database_url` mit `POSTGRES_USER`; das offizielle Postgres-Image initialisiert diesen Benutzer
als Superuser. Der API-Container führte zudem Alembic mit dieser Verbindung aus. Eine frische Standardinstallation
arbeitete deshalb mit Rechten, welche die RLS-Policies umgehen. Die CI testete dagegen bereits mit einer Laufzeitrolle.

## Umsetzung

1. Ein einmaliger Compose-Dienst `migrate` führt Alembic mit `migration_database_url` aus und richtet anschließend die
   eigene Laufzeitrolle ein. Er besitzt keinen Netzwerk-Port und kein Datenvolume.
2. `database_url` bezeichnet ausschließlich die Laufzeitverbindung. Die API startet keine Schema-Migrationen.
3. Vor Annahme von Anfragen prüft die API in staging/production: PostgreSQL, keine privilegierten Rollenattribute,
   keine weiteren Rollenmitgliedschaften, kein Datenbank-/Tabellenbesitz, kein CREATE im Anwendungsschema,
   kein Änderungs-/Lösch-/TRUNCATE-/TRIGGER-Recht am Audit-Log. Unsichere Konfiguration verhindert den Start.
4. Der Migrator richtet nur eine eigene, unprivilegierte Rolle ohne Mitgliedschaften ein. Er verweigert vorhandene
   Eigentümerrollen und die Wiederverwendung seines eigenen Administratorkontos.
5. Ein bestehendes altes `database_url` wird nicht still überschrieben. Die Anleitung beschreibt den Umstieg unter
   Wartung mit gesichertem Altstand und neuer Laufzeitverbindung.
6. Secret-Dateien bleiben 0600. Bei rootgestützter Einrichtung bekommen die Dateien für API/Migrator UID 1000;
   die Admin-URL wird ausschließlich in den Migrator gemountet. Compose-Secrets aus lokalen Dateien sind Bind-Mounts: deklarative
   uid/gid-Werte ersetzen keine passenden Rechte auf dem Host.

## Abnahme

- Frische Installation: Migrator erfolgreich, API als eigene Rolle, kein Admin-Secret im API-Container.
- Upgrade einer alten Installation: vorhandene Kryptoschlüssel bytegleich; expliziter Umstieg, keine Volumenlöschung.
- API-Start mit Superuser, BYPASSRLS, Mitgliedschaft oder Eigentümerrechten wird abgewiesen.
- Wiederholtes Migrieren vergibt Rechte für neue Tabellen, ohne die Rolle aufzuwerten.
- Mandantentrennung, Registrierung, Login, MFA und Audit-Append-only funktionieren mit der tatsächlichen Laufzeitrolle.
- Compose-Validierung und Docker-Smoke-Test für beide Profile; vollständige SQLite- und PostgreSQL-Suite.

## Grenzen

RLS schützt gegen fehlende Mandantenfilter und begrenzt Datenbankrechte. Der Mandantenkontext wird von der Anwendung
gesetzt; dies ist keine unabhängige Sicherheitsgrenze gegen vollständig kompromittierten Backend-Code. Die API benötigt
weiterhin Kryptoschlüssel für ihre Aufgaben. Produktiver Rollout und vollständiger Restore bleiben Betreiberaufgaben.
