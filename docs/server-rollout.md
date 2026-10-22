# Server-Rollout: Mandantentrennung (RLS) und verschlüsselte Spalten

Stand: 2026-10-11. Gilt für den Wechsel von der älteren Version auf `main` ab PR #9
(Migrationen 0035 und 0036). Geprüft ist alles nur gegen eine temporäre lokale Postgres-Instanz.
Der echte Server wurde nicht angefasst. Die Compose-Dienstnamen unten (`backend`, `postgres`) sind
Annahmen aus `docker-compose.prod.yml`, vor dem Ausführen am Server gegenprüfen.

## Was sich ändert
- **0035** legt drei Lookup-Funktionen an (Einladungscode, Login, Kunde der früheren Bezahlfunktion); die dritte entfernt Migration 0039 wieder.
- **0036** stellt 42 verschlüsselte Spalten auf TEXT um und verschlüsselt vorhandene Klartextwerte. Nicht umkehrbar.
- Die App verbindet sich danach als Rolle `bilantiq_runtime` ohne BYPASSRLS. Erst dadurch greift die Mandantentrennung.

## Vorher (nichts davon überspringen)
1. Verschlüsseltes Backup: `scripts/backup.sh`. Danach `scripts/restore.sh` auf einer ANDEREN Maschine/Datenbank testen.
   Ohne geprüften Restore nicht fortfahren, 0036 schreibt Produktivdaten um.
2. Backup extern ablegen (nicht nur auf dem Server).
3. `.env.prod`: `FIELD_ENCRYPTION_KEY`, `DATA_ENCRYPTION_KEYS`, `DATA_ENCRYPTION_ACTIVE_KID` sichern. Ohne sie sind die Daten nach 0036 unlesbar.
4. Wartungsfenster: kurz die App stoppen (`docker compose -f docker-compose.prod.yml stop backend`), damit während der Migration niemand schreibt.

## Ablauf
1. Neuen Stand holen und Images bauen (`git pull`, `docker compose -f docker-compose.prod.yml build backend`).
2. Migrationen mit dem Administrator-Zugang der Datenbank, nicht mit der Laufzeitrolle:
   `docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head`
   Erwartet: `0034 -> 0035` und `0035 -> 0036`, danach `alembic current` = `0036`.
3. Laufzeitrolle anlegen/aktualisieren (nach JEDER Migration erneut):
   `psql -v rolle=bilantiq_runtime -v passwort="'<neues Passwort>'" -f backend/scripts/runtime_rolle.sql <datenbank>` als Datenbank-Admin.
   Das Passwort nur in der Secrets-Datei ablegen, nie im Chat oder Repo.
4. `DATABASE_URL` der App auf `bilantiq_runtime` umstellen. Migrationen laufen weiter mit dem Admin-Zugang.
5. Falls die bisherige App-Rolle BYPASSRLS hatte: nicht mehr für die App verwenden (`ALTER ROLE <alt> NOBYPASSRLS` oder Rolle nur noch für Migrationen nutzen).
6. App starten.

## Prüfen
- Login mit einem bestehenden Konto, Rechnungsliste, eine Rechnung als PDF, einen Kontakt anlegen, eine Rechnung anlegen.
- `/berichte/dashboard` und EÜR öffnen (lesen entschlüsselte Beträge).
- Eine neue Registrierung mit Einladungscode (läuft über die Lookup-Funktionen).
- Zwei Mandanten: Konto A darf Daten von B weder sehen noch per ID abrufen (liefert 404).
- Logs auf `permission denied` oder `InsufficientPrivilege` prüfen.

## Rückweg
- Fehler vor Schritt 2: nichts zu tun, alten Stand starten.
- Fehler nach 0036: Datenbank aus dem Backup zurückspielen (`scripts/restore.sh`) und alten Image-Stand starten. `alembic downgrade` geht für 0036 absichtlich nicht.

## Offen / bekannte Grenzen
- Schlüsselrotation: das append-only Audit-Log bleibt auf dem alten Schlüssel. Beim Rotieren den alten Key im Ring behalten (das Skript meldet es).
- Nicht Teil dieses Rollouts: DNS (`@`, `www`, `api`), externes Backup-Ziel, Alarmierung, Notfallzugang zum Anbieter.
