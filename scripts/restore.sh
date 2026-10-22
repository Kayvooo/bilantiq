#!/usr/bin/env bash
# Spielt einen mit scripts/backup.sh erzeugten, age-verschluesselten DB-Dump in die Compose-Datenbank ein.
#
# ACHTUNG: UEBERSCHREIBT die Datenbank (pg_dump --clean). Erst mit scripts/restore-test.sh in einer
# Wegwerf-Datenbank ueben. Der Import laeuft in EINER Transaktion mit COMMIT nur nach vollstaendigem Dump: bei einem Fehler oder
# abgeschnittenem Datenstrom bleibt der bisherige Stand unveraendert.
#
# Aufruf:  BACKUP_AGE_IDENTITY_FILE=/pfad/zum/privaten/schluessel ./scripts/restore.sh backups/db_<TS>.sql.gz.age
# Voraussetzungen: Datenbankrollen aus dem Dump (z. B. bilantiq_runtime) existieren im Zielcluster; sonst
# bricht der Import sauber ab (siehe docs/rollback.md, Abschnitt "Rollen"). Das Upload-Volume wird NICHT
# angefasst (Anleitung: docs/rollback.md).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"

fail() { echo "restore.sh: FEHLER: $*" >&2; exit 1; }

DUMP="${1:-}"
[ -n "$DUMP" ] || fail "Usage: ./scripts/restore.sh <db_dump.sql.gz.age>"
[ -f "$DUMP" ] || fail "Dump-Datei nicht gefunden: $DUMP"
[ -f "$ENV_FILE" ] || fail "$ENV_FILE nicht gefunden."
[ -n "$BACKUP_AGE_IDENTITY_FILE" ] || fail "BACKUP_AGE_IDENTITY_FILE fehlt."
[ -f "$BACKUP_AGE_IDENTITY_FILE" ] || fail "age Identity-Datei nicht gefunden."
command -v docker >/dev/null || fail "docker nicht gefunden."
command -v age >/dev/null || fail "age nicht gefunden."
command -v gunzip >/dev/null || fail "gunzip nicht gefunden."

# Nur benoetigte Variablen lesen, Env-Datei nicht als Shell ausfuehren.
envval() { grep -E "^[[:space:]]*$1=" "$ENV_FILE" | tail -n1 | sed -E "s/^[[:space:]]*$1=//; s/^[\"']//; s/[\"']\$//"; }
POSTGRES_USER="$(envval POSTGRES_USER)"; POSTGRES_DB="$(envval POSTGRES_DB)"
[ -n "$POSTGRES_USER" ] || fail "POSTGRES_USER fehlt in $ENV_FILE"
[ -n "$POSTGRES_DB" ] || fail "POSTGRES_DB fehlt in $ENV_FILE"

# Pruefsumme gegen das Manifest, falls vorhanden (erkennt Uebertragungsfehler und Beschaedigung des Chiffrats).
DUMP_DIR="$(cd "$(dirname "$DUMP")" && pwd)"
DUMP_BASE="$(basename "$DUMP")"
TS="${DUMP_BASE#db_}"; TS="${TS%.sql.gz.age}"
MANIFEST="$DUMP_DIR/manifest_${TS}.sha256"
if [ -f "$MANIFEST" ]; then
  ( cd "$DUMP_DIR" && grep -F " $DUMP_BASE" "$MANIFEST" | sha256sum -c --quiet - ) \
    || fail "Pruefsumme von $DUMP_BASE stimmt nicht mit $(basename "$MANIFEST") ueberein. Nicht einspielen, andere Kopie (Off-site) verwenden."
  echo "restore.sh: Pruefsumme ok."
else
  echo "restore.sh: WARNUNG: kein Manifest ($MANIFEST), Pruefsumme nicht ueberprueft." >&2
fi

compose() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

if [ -n "$(compose ps --status running --quiet backend 2>/dev/null || true)" ]; then
  echo "restore.sh: WARNUNG: der Backend-Container laeuft. Vor dem Restore stoppen:" >&2
  echo "            docker compose --env-file $ENV_FILE -f $COMPOSE_FILE stop backend" >&2
fi

echo "restore.sh: Dies ueberschreibt die aktuelle Datenbank '$POSTGRES_DB' (Compose: $COMPOSE_FILE)."
read -r -p "Fortfahren? Tippe JA in Grossbuchstaben: " ANTWORT
[ "$ANTWORT" = "JA" ] || fail "Abgebrochen."

echo "restore.sh: entschluesseln und in einer Transaktion einspielen ..."
# BEGIN steht vor dem Dump, COMMIT nur, wenn Entschluesseln und Entpacken vollstaendig gelangen. Bricht der
# Datenstrom ab (falscher Schluessel, abgeschnittene Datei), fehlt das COMMIT, die Verbindung endet und PostgreSQL
# rollt zurueck. (psql --single-transaction wuerde einen abgeschnittenen Dump am Dateiende noch committen.)
{
  echo "BEGIN;"
  if age -d -i "$BACKUP_AGE_IDENTITY_FILE" "$DUMP" | gunzip -c; then
    echo "COMMIT;"
  else
    echo "restore.sh: FEHLER: Entschluesseln/Entpacken fehlgeschlagen, es wird nichts committet." >&2
    exit 1
  fi
} | compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null

echo "restore.sh: Migrationsstand der wiederhergestellten Datenbank:"
compose exec -T postgres psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version" \
  || echo "restore.sh: WARNUNG: alembic_version nicht lesbar." >&2

echo "restore.sh: fertig. Naechste Schritte: Backend starten, Login + Rechnungsliste + ein PDF pruefen (docs/rollback.md)."
echo "restore.sh: Das Upload-Volume wurde NICHT veraendert (separat, siehe docs/rollback.md)."
