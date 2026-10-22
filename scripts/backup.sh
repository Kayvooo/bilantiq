#!/usr/bin/env bash
# Verschluesseltes Backup fuer Bilantiq (Datenbank + Upload-Volume).
#
# Pflicht: age ist installiert und BACKUP_AGE_RECIPIENT (oder BACKUP_AGE_RECIPIENTS_FILE) enthaelt
# oeffentliche age-Schluessel (age1...). Der private Schluessel gehoert NICHT auf diesen Server.
# Es gibt keinen unverschluesselten Modus und nie Klartext auf der Platte: pg_dump | gzip | age.
#
# Wichtig: Das Backup enthaelt NICHT die Anwendungsschluessel (DATA_ENCRYPTION_KEYS, FIELD_ENCRYPTION_KEY,
# BLIND_INDEX_SECRET, ...). Ohne sie sind die Daten nach einem Restore nicht lesbar. Diese Schluessel
# getrennt vom Datenbackup und offline sichern (docs/rollback.md).
#
# Ergebnis pro Lauf in $BACKUP_DIR:
#   db_<TS>.sql.gz.age, uploads_<TS>.tar.gz.age, manifest_<TS>.sha256 (Pruefsummen der Chiffrate)
#   .last_success (Epoch lokal vollstaendig), .last_offsite_success (Epoch Off-site-Kopie)
# Diese Marker liest scripts/healthcheck.sh. Exit 0 nur, wenn alles Verlangte gelang.
set -euo pipefail
umask 077

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MIN_KEEP="${MIN_KEEP:-3}"                 # so viele neueste Sicherungen bleiben immer, auch wenn aelter als RETENTION_DAYS
OFFSITE_TARGET="${OFFSITE_TARGET:-}"      # rsync-Ziel, z. B. backup@host:/pfad/bilantiq/
OFFSITE_SSH_OPTS="${OFFSITE_SSH_OPTS:-}"  # z. B. "-i /root/.ssh/backup_key -o StrictHostKeyChecking=yes"
REQUIRE_OFFSITE="${REQUIRE_OFFSITE:-1}"   # 1 = ohne Off-site-Kopie endet das Skript mit Fehler (Staging: 0)
BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
BACKUP_AGE_RECIPIENTS_FILE="${BACKUP_AGE_RECIPIENTS_FILE:-}"
VOLUME_NAME="${VOLUME_NAME:-bilantiq_backend_data}"
HELPER_IMAGE="${HELPER_IMAGE:-alpine:3.20}"
DB_MIN_BYTES="${DB_MIN_BYTES:-2000}"      # kleinere komprimierte Dumps gelten als fehlgeschlagen
MIN_FREE_MB="${MIN_FREE_MB:-500}"

log()  { echo "backup.sh: $(date '+%H:%M:%S') $*"; }
fail() { echo "backup.sh: FEHLER: $*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || fail "$ENV_FILE nicht gefunden."
command -v docker >/dev/null || fail "docker nicht gefunden."
command -v age >/dev/null || fail "age nicht gefunden."
command -v sha256sum >/dev/null || fail "sha256sum nicht gefunden."

# Empfaenger aufbauen und validieren (kein Klartext-Fallback, kein versehentlich privater Schluessel).
AGE_ARGS=()
for r in $BACKUP_AGE_RECIPIENT; do
  case "$r" in
    AGE-SECRET-KEY-*) fail "BACKUP_AGE_RECIPIENT enthaelt einen PRIVATEN Schluessel. Hier gehoert nur der oeffentliche (age1...) hin." ;;
    age1*) AGE_ARGS+=(-r "$r") ;;
    *) fail "BACKUP_AGE_RECIPIENT ist kein age-Public-Key (erwartet age1...)." ;;
  esac
done
if [ -n "$BACKUP_AGE_RECIPIENTS_FILE" ]; then
  [ -f "$BACKUP_AGE_RECIPIENTS_FILE" ] || fail "BACKUP_AGE_RECIPIENTS_FILE nicht gefunden."
  if grep -q 'AGE-SECRET-KEY-' "$BACKUP_AGE_RECIPIENTS_FILE"; then fail "BACKUP_AGE_RECIPIENTS_FILE enthaelt einen privaten Schluessel."; fi
  AGE_ARGS+=(-R "$BACKUP_AGE_RECIPIENTS_FILE")
fi
[ "${#AGE_ARGS[@]}" -gt 0 ] || fail "BACKUP_AGE_RECIPIENT fehlt; unverschluesselte Backups sind nicht erlaubt."

# Nur die benoetigten Variablen lesen. Die Env-Datei wird bewusst NICHT per `source` ausgefuehrt
# (Compose-Env-Dateien sind keine Shell-Syntax; Werte mit Leerzeichen/$ wuerden sonst Code ausfuehren oder brechen).
envval() { grep -E "^[[:space:]]*$1=" "$ENV_FILE" | tail -n1 | sed -E "s/^[[:space:]]*$1=//; s/^[\"']//; s/[\"']\$//"; }
POSTGRES_USER="$(envval POSTGRES_USER)"; POSTGRES_DB="$(envval POSTGRES_DB)"
[ -n "$POSTGRES_USER" ] || fail "POSTGRES_USER fehlt in $ENV_FILE"
[ -n "$POSTGRES_DB" ] || fail "POSTGRES_DB fehlt in $ENV_FILE"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Nur ein Lauf gleichzeitig.
command -v flock >/dev/null && { exec 9>"$BACKUP_DIR/.lock"; flock -n 9 || fail "ein anderer Backup-Lauf ist aktiv."; }

free_mb="$(df -Pm "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
[ "${free_mb:-0}" -ge "$MIN_FREE_MB" ] || fail "nur ${free_mb:-?} MB frei in $BACKUP_DIR (Minimum $MIN_FREE_MB MB)."

TS="$(date +%Y-%m-%d_%H-%M-%S)"
DB_FILE="$BACKUP_DIR/db_${TS}.sql.gz.age"
UPLOADS_FILE="$BACKUP_DIR/uploads_${TS}.tar.gz.age"
MANIFEST="$BACKUP_DIR/manifest_${TS}.sha256"
SIZE_TMP="$(mktemp "$BACKUP_DIR/.size.XXXXXX")"

# Es wird erst unter .part geschrieben und nach Pruefung umbenannt: ein Abbruch hinterlaesst nie
# eine scheinbar gueltige, aber abgeschnittene .age-Datei.
cleanup() { rm -f "$DB_FILE.part" "$UPLOADS_FILE.part" "$MANIFEST.part" "$SIZE_TMP"; }
trap cleanup EXIT

compose() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

check_age_header() { # Datei muss ein age-Chiffrat sein, nicht leer und nicht Klartext
  [ -s "$1" ] || fail "$2 ist leer."
  head -c 21 "$1" | grep -q '^age-encryption.org/v1' || fail "$2 hat keinen age-Header (nicht verschluesselt?)."
}

log "Postgres-Dump (pg_dump | gzip | age)"
compose exec -T postgres pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip \
  | { tee >(wc -c > "$SIZE_TMP") | age "${AGE_ARGS[@]}" -o "$DB_FILE.part"; }
# Prozesssubstitution laeuft asynchron: kurz auf die Groessenangabe warten.
for _ in $(seq 1 50); do [ -s "$SIZE_TMP" ] && break; sleep 0.1; done
DB_GZ_BYTES="$(tr -dc '0-9' < "$SIZE_TMP")"
[ "${DB_GZ_BYTES:-0}" -ge "$DB_MIN_BYTES" ] || fail "Datenbank-Dump verdaechtig klein (${DB_GZ_BYTES:-0} Bytes komprimiert, Minimum $DB_MIN_BYTES): Backup verworfen."
check_age_header "$DB_FILE.part" "Verschluesselter Datenbank-Dump"

log "Upload-Volume ($VOLUME_NAME)"
docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1 \
  || fail "Docker-Volume '$VOLUME_NAME' existiert nicht (VOLUME_NAME pruefen). Es wuerde sonst ein leeres Volume gesichert."
docker run --rm -v "$VOLUME_NAME":/data:ro "$HELPER_IMAGE" tar czf - -C /data . \
  | age "${AGE_ARGS[@]}" -o "$UPLOADS_FILE.part"
check_age_header "$UPLOADS_FILE.part" "Verschluesseltes Upload-Backup"

mv "$DB_FILE.part" "$DB_FILE"
mv "$UPLOADS_FILE.part" "$UPLOADS_FILE"
chmod 600 "$DB_FILE" "$UPLOADS_FILE"
( cd "$BACKUP_DIR" && sha256sum "$(basename "$DB_FILE")" "$(basename "$UPLOADS_FILE")" > "$MANIFEST.part" )
mv "$MANIFEST.part" "$MANIFEST"
chmod 600 "$MANIFEST"
( cd "$BACKUP_DIR" && sha256sum -c --quiet "$(basename "$MANIFEST")" ) || fail "Pruefsummen direkt nach dem Schreiben nicht konsistent."
date +%s > "$BACKUP_DIR/.last_success"
log "lokal vollstaendig: $(basename "$DB_FILE") ($(stat -c %s "$DB_FILE") B), $(basename "$UPLOADS_FILE") ($(stat -c %s "$UPLOADS_FILE") B)"

# Aufraeumen: Sicherungen aelter als RETENTION_DAYS, aber die neuesten MIN_KEEP bleiben immer.
# So loescht ein tagelang fehlschlagendes Backup nie den letzten guten Stand.
log "Prune (> ${RETENTION_DAYS} Tage, mindestens ${MIN_KEEP} bleiben)"
mapfile -t SETS < <(ls -1 "$BACKUP_DIR"/db_*.sql.gz.age 2>/dev/null | sort -r)
idx=0
for f in "${SETS[@]:-}"; do
  [ -n "$f" ] || continue
  idx=$((idx + 1))
  [ "$idx" -gt "$MIN_KEEP" ] || continue
  if [ -n "$(find "$f" -maxdepth 0 -mtime +"$RETENTION_DAYS" -print)" ]; then
    set_ts="$(basename "$f")"; set_ts="${set_ts#db_}"; set_ts="${set_ts%.sql.gz.age}"
    rm -f "$f" "$BACKUP_DIR/uploads_${set_ts}.tar.gz.age" "$BACKUP_DIR/manifest_${set_ts}.sha256"
    log "geloescht: Sicherung $set_ts"
  fi
done
find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.part' -mtime +1 -delete

if [ -n "$OFFSITE_TARGET" ]; then
  command -v rsync >/dev/null || fail "rsync nicht gefunden (Off-site-Kopie nicht moeglich)."
  log "Off-site-Kopie nach $OFFSITE_TARGET (ohne --delete: Loeschungen am Ziel nie von hier aus)"
  # shellcheck disable=SC2086
  rsync -a --checksum ${OFFSITE_SSH_OPTS:+-e "ssh $OFFSITE_SSH_OPTS"} "$DB_FILE" "$UPLOADS_FILE" "$MANIFEST" "$OFFSITE_TARGET" \
    || fail "Off-site-Kopie fehlgeschlagen (lokales Backup ist vorhanden)."
  date +%s > "$BACKUP_DIR/.last_offsite_success"
  log "Off-site-Kopie erfolgreich. Alterung am Ziel selbst regeln (siehe docs/rollback.md)."
elif [ "$REQUIRE_OFFSITE" = "1" ]; then
  echo "backup.sh: FEHLER: OFFSITE_TARGET fehlt. Das Backup ist lokal verschluesselt vorhanden, aber nicht off-site (REQUIRE_OFFSITE=0 nur fuer Staging)." >&2
  exit 2
else
  log "WARNUNG: OFFSITE_TARGET fehlt (REQUIRE_OFFSITE=0): Backup ist nur lokal."
fi

log "fertig ($TS). Erinnerung: Anwendungsschluessel sind nicht im Backup."
