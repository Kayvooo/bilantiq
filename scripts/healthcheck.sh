#!/usr/bin/env bash
# Betriebs-Healthcheck fuer Bilantiq (Release-Plan 2.6).
#
# Prueft: Erreichbarkeit App/API/Website, TLS-Ablauf in Tagen, Festplatte, Alter und
# Unversehrtheit des letzten Backups (inkl. Off-site-Marker). Meldet Probleme per Webhook
# und/oder E-Mail (vom Owner einzutragen) und beendet sich mit einem Exit-Code:
#   0 = alles in Ordnung,  1 = Warnung,  2 = kritisch
#
# Aufruf:
#   ./scripts/healthcheck.sh                 # normaler Lauf (Timer/Cron)
#   ./scripts/healthcheck.sh --dry-run       # prueft und gibt aus, benachrichtigt nicht
#   ./scripts/healthcheck.sh --test-notify   # schickt eine Testnachricht (Alarmweg pruefen)
#
# Konfiguration: Umgebungsvariablen oder Datei HEALTHCHECK_CONF (Default /etc/bilantiq/healthcheck.env,
# einfache KEY=Wert-Zeilen, wird NICHT als Shell-Code ausgefuehrt). Vorlage: docs/betrieb-monitoring.md.
#
# Grenze: Ein Skript auf dem Server kann nicht melden, dass der Server selbst (oder dessen Netz) ausgefallen ist.
# Dafuer gibt es HEARTBEAT_URL (Dead-Man's-Switch bei einem externen Dienst) und/oder einen externen Uptime-Monitor.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="run"
case "${1:-}" in
  --dry-run) MODE="dry" ;;
  --test-notify) MODE="test" ;;
  "") ;;
  -h|--help) sed -n 2,18p "${BASH_SOURCE[0]}"; exit 0 ;;
  *) echo "healthcheck.sh: unbekannte Option: $1" >&2; exit 64 ;;
esac

# --- Konfiguration laden (nur bekannte Schluessel, kein eval) -------------------------------
CONF="${HEALTHCHECK_CONF:-/etc/bilantiq/healthcheck.env}"
KNOWN_KEYS="APP_URL API_URL WEBSITE_URL TLS_HOSTS TLS_WARN_DAYS TLS_CRIT_DAYS DISK_PATHS DISK_WARN_PCT DISK_CRIT_PCT \
BACKUP_DIR BACKUP_MAX_AGE_HOURS BACKUP_MIN_BYTES OFFSITE_EXPECTED NOTIFY_WEBHOOK_URL NOTIFY_WEBHOOK_FORMAT \
NOTIFY_EMAIL NOTIFY_MAIL_FROM HEARTBEAT_URL STATE_DIR REMIND_HOURS SERVER_NAME CURL_TIMEOUT"
if [ -r "$CONF" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    key="${key//[[:space:]]/}"
    val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
    for k in $KNOWN_KEYS; do
      # Umgebungsvariablen haben Vorrang vor der Datei.
      if [ "$key" = "$k" ] && [ -z "${!k+x}" ]; then export "$k=$val"; fi
    done
  done < "$CONF"
elif [ -n "${HEALTHCHECK_CONF:-}" ]; then
  echo "healthcheck.sh: Konfigurationsdatei nicht lesbar: $CONF" >&2; exit 64
fi

APP_URL="${APP_URL:-}"
API_URL="${API_URL:-}"
WEBSITE_URL="${WEBSITE_URL:-}"
TLS_HOSTS="${TLS_HOSTS:-}"
TLS_WARN_DAYS="${TLS_WARN_DAYS:-21}"
TLS_CRIT_DAYS="${TLS_CRIT_DAYS:-7}"
DISK_PATHS="${DISK_PATHS:-/}"
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
DISK_CRIT_PCT="${DISK_CRIT_PCT:-92}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_DIR/backups}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-30}"
BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-1024}"
OFFSITE_EXPECTED="${OFFSITE_EXPECTED:-1}"
NOTIFY_WEBHOOK_URL="${NOTIFY_WEBHOOK_URL:-}"
NOTIFY_WEBHOOK_FORMAT="${NOTIFY_WEBHOOK_FORMAT:-text}"   # text = {"text":..}, content = {"content":..}, plain = Klartext-Body (z. B. ntfy)
NOTIFY_EMAIL="${NOTIFY_EMAIL:-}"
NOTIFY_MAIL_FROM="${NOTIFY_MAIL_FROM:-}"
HEARTBEAT_URL="${HEARTBEAT_URL:-}"
STATE_DIR="${STATE_DIR:-/var/lib/bilantiq-healthcheck}"
REMIND_HOURS="${REMIND_HOURS:-12}"
SERVER_NAME="${SERVER_NAME:-$(hostname 2>/dev/null || echo server)}"
CURL_TIMEOUT="${CURL_TIMEOUT:-10}"

PROBLEMS=()     # "KRIT|text" oder "WARN|text"
INFOS=()
level=0

add() { # add <0|1|2> <text>
  local lv="$1"; shift
  case "$lv" in
    2) PROBLEMS+=("KRITISCH: $*"); [ "$level" -lt 2 ] && level=2 ;;
    1) PROBLEMS+=("WARNUNG: $*"); [ "$level" -lt 1 ] && level=1 ;;
    *) INFOS+=("ok: $*") ;;
  esac
}

command -v curl >/dev/null || { echo "healthcheck.sh: curl fehlt" >&2; exit 64; }

# --- 1. Erreichbarkeit ----------------------------------------------------------------------
check_http() { # check_http <name> <url> <erwarteter-body-teil|"">
  local name="$1" url="$2" expect="$3" tmp code
  [ -n "$url" ] || return 0
  tmp="$(mktemp)"
  code="$(curl -sS -o "$tmp" -m "$CURL_TIMEOUT" -w '%{http_code}' -A 'bilantiq-healthcheck/1' "$url" 2>/dev/null || true)"
  code="${code:-000}"
  if [ "$code" != "200" ]; then
    add 2 "$name nicht erreichbar oder unerwartet (HTTP $code)"
  elif [ -n "$expect" ] && ! grep -q "$expect" "$tmp"; then
    add 2 "$name antwortet 200, aber ohne erwarteten Inhalt"
  else
    add 0 "$name erreichbar"
  fi
  rm -f "$tmp"
}
if [ "$MODE" != "test" ]; then
  [ -n "$APP_URL$API_URL$WEBSITE_URL" ] || add 1 "weder APP_URL noch API_URL noch WEBSITE_URL konfiguriert: Erreichbarkeit wird nicht geprueft"
  check_http "App ($APP_URL)" "$APP_URL" "<div id=\"root\""
  check_http "API ($API_URL)" "$API_URL" '"status":"ok"'
  check_http "Website ($WEBSITE_URL)" "$WEBSITE_URL" ""

  # --- 2. TLS-Ablauf ----------------------------------------------------------------------
  if [ -n "$TLS_HOSTS" ]; then
    command -v openssl >/dev/null || add 1 "openssl fehlt: TLS-Ablauf nicht pruefbar"
    for hp in $TLS_HOSTS; do
      host="${hp%%:*}"; port=443; [ "$hp" != "$host" ] && port="${hp##*:}"
      end="$(echo | timeout 15 openssl s_client -servername "$host" -connect "$host:$port" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//')"
      if [ -z "$end" ]; then add 2 "TLS $hp: Zertifikat nicht abrufbar"; continue; fi
      end_ts="$(date -d "$end" +%s 2>/dev/null || echo 0)"
      days=$(( (end_ts - $(date +%s)) / 86400 ))
      if [ "$end_ts" -eq 0 ]; then add 1 "TLS $hp: Ablaufdatum nicht lesbar ($end)"
      elif [ "$days" -lt "$TLS_CRIT_DAYS" ]; then add 2 "TLS $hp laeuft in $days Tagen ab (Erneuerung pruefen: Caddy-Log, Port 80/443, DNS)"
      elif [ "$days" -lt "$TLS_WARN_DAYS" ]; then add 1 "TLS $hp laeuft in $days Tagen ab (Caddy erneuert normalerweise ab 30 Tagen vorher)"
      else add 0 "TLS $hp noch $days Tage gueltig"; fi
    done
  fi

  # --- 3. Festplatte ----------------------------------------------------------------------
  for p in $DISK_PATHS; do
    if [ ! -d "$p" ]; then add 1 "Pfad fuer Plattenpruefung fehlt: $p"; continue; fi
    pct="$(df -P "$p" | awk 'NR==2 {gsub("%","",$5); print $5}')"
    if [ -z "$pct" ]; then add 1 "Plattenbelegung von $p nicht lesbar"
    elif [ "$pct" -ge "$DISK_CRIT_PCT" ]; then add 2 "Festplatte $p zu ${pct}% belegt"
    elif [ "$pct" -ge "$DISK_WARN_PCT" ]; then add 1 "Festplatte $p zu ${pct}% belegt"
    else add 0 "Festplatte $p ${pct}% belegt"; fi
  done

  # --- 4. Backup --------------------------------------------------------------------------
  now="$(date +%s)"
  if [ ! -d "$BACKUP_DIR" ]; then
    add 2 "Backup-Verzeichnis fehlt: $BACKUP_DIR"
  else
    marker="$BACKUP_DIR/.last_success"
    if [ -r "$marker" ]; then last="$(head -n1 "$marker" | tr -dc '0-9')"; else last=""; fi
    if [ -z "$last" ]; then
      add 2 "kein Backup-Erfolgsmarker ($marker): Backup lief noch nie erfolgreich oder aelteres backup.sh"
    else
      age_h=$(( (now - last) / 3600 ))
      if [ "$age_h" -gt "$BACKUP_MAX_AGE_HOURS" ]; then add 2 "letztes erfolgreiches Backup ist ${age_h}h alt (Grenze ${BACKUP_MAX_AGE_HOURS}h)"
      else add 0 "letztes Backup vor ${age_h}h"; fi
    fi
    newest_db="$(ls -1t "$BACKUP_DIR"/db_*.sql.gz.age 2>/dev/null | head -n1)"
    if [ -z "$newest_db" ]; then add 2 "keine Datenbank-Sicherung in $BACKUP_DIR"
    else
      size="$(stat -c '%s' "$newest_db")"
      if [ "$size" -lt "$BACKUP_MIN_BYTES" ]; then add 2 "neueste DB-Sicherung ist verdaechtig klein (${size} Bytes)"; fi
      ts_name="$(basename "$newest_db")"; ts_name="${ts_name#db_}"; ts_name="${ts_name%.sql.gz.age}"
      sumfile="$BACKUP_DIR/manifest_${ts_name}.sha256"
      if [ -f "$sumfile" ]; then
        if ! (cd "$BACKUP_DIR" && sha256sum -c --quiet "$(basename "$sumfile")" >/dev/null 2>&1); then
          add 2 "Pruefsumme der neuesten Sicherung stimmt nicht ($(basename "$sumfile"))"
        fi
      else
        add 1 "keine Pruefsummendatei zur neuesten Sicherung"
      fi
    fi
    if [ "$OFFSITE_EXPECTED" = "1" ]; then
      om="$BACKUP_DIR/.last_offsite_success"
      if [ -r "$om" ]; then
        olast="$(head -n1 "$om" | tr -dc '0-9')"
        oage_h=$(( (now - ${olast:-0}) / 3600 ))
        if [ "$oage_h" -gt "$BACKUP_MAX_AGE_HOURS" ]; then add 2 "letzte Off-site-Kopie ist ${oage_h}h alt"; else add 0 "letzte Off-site-Kopie vor ${oage_h}h"; fi
      else
        add 2 "keine Off-site-Kopie nachgewiesen ($om fehlt)"
      fi
    fi
  fi
fi

# --- Ausgabe & Benachrichtigung --------------------------------------------------------------
notify() { # notify <text>
  local text="$1" body
  if [ -n "$NOTIFY_WEBHOOK_URL" ]; then
    case "$NOTIFY_WEBHOOK_FORMAT" in
      content) body="$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps({"content": sys.stdin.read()}))')"
               curl -sS -m 15 -o /dev/null -H 'Content-Type: application/json' -d "$body" "$NOTIFY_WEBHOOK_URL" || echo "healthcheck.sh: Webhook fehlgeschlagen" >&2 ;;
      plain)   curl -sS -m 15 -o /dev/null -d "$text" "$NOTIFY_WEBHOOK_URL" || echo "healthcheck.sh: Webhook fehlgeschlagen" >&2 ;;
      *)       body="$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps({"text": sys.stdin.read()}))')"
               curl -sS -m 15 -o /dev/null -H 'Content-Type: application/json' -d "$body" "$NOTIFY_WEBHOOK_URL" || echo "healthcheck.sh: Webhook fehlgeschlagen" >&2 ;;
    esac
  fi
  if [ -n "$NOTIFY_EMAIL" ]; then
    if command -v mail >/dev/null; then
      printf '%s\n' "$text" | mail -s "Bilantiq Healthcheck ($SERVER_NAME)" ${NOTIFY_MAIL_FROM:+-r "$NOTIFY_MAIL_FROM"} "$NOTIFY_EMAIL" || echo "healthcheck.sh: mail fehlgeschlagen" >&2
    elif command -v sendmail >/dev/null; then
      printf 'To: %s\nSubject: Bilantiq Healthcheck (%s)\n\n%s\n' "$NOTIFY_EMAIL" "$SERVER_NAME" "$text" | sendmail -t || echo "healthcheck.sh: sendmail fehlgeschlagen" >&2
    else
      echo "healthcheck.sh: NOTIFY_EMAIL gesetzt, aber weder mail noch sendmail installiert" >&2
    fi
  fi
  if [ -z "$NOTIFY_WEBHOOK_URL" ] && [ -z "$NOTIFY_EMAIL" ]; then
    echo "healthcheck.sh: WARNUNG: kein Benachrichtigungsweg konfiguriert (NOTIFY_WEBHOOK_URL / NOTIFY_EMAIL)" >&2
  fi
}

if [ "$MODE" = "test" ]; then
  notify "Bilantiq Healthcheck auf $SERVER_NAME: Testnachricht ($(date -u '+%Y-%m-%d %H:%M UTC')). Wenn du das liest, funktioniert der Alarmweg."
  echo "Testnachricht gesendet (Zustellung am Zielkanal selbst pruefen)."
  exit 0
fi

for l in "${INFOS[@]:-}"; do [ -n "$l" ] && echo "$l"; done
for l in "${PROBLEMS[@]:-}"; do [ -n "$l" ] && echo "$l"; done
case "$level" in 0) echo "Gesamt: OK" ;; 1) echo "Gesamt: WARNUNG" ;; *) echo "Gesamt: KRITISCH" ;; esac

if [ "$MODE" = "run" ]; then
  mkdir -p "$STATE_DIR" 2>/dev/null || true
  state="$STATE_DIR/last_state"
  summary="$(printf '%s\n' "${PROBLEMS[@]:-}" | sed '/^$/d')"
  cur_hash="$(printf '%s' "$summary" | sha256sum | cut -d' ' -f1)"
  prev_hash=""; prev_ts=0
  if [ -r "$state" ]; then prev_hash="$(sed -n 1p "$state")"; prev_ts="$(sed -n 2p "$state")"; fi
  now="$(date +%s)"
  if [ "$level" -gt 0 ]; then
    if [ "$cur_hash" != "$prev_hash" ] || [ $(( now - ${prev_ts:-0} )) -ge $(( REMIND_HOURS * 3600 )) ]; then
      notify "Bilantiq Healthcheck auf $SERVER_NAME:
$summary"
      printf '%s\n%s\n' "$cur_hash" "$now" > "$state" 2>/dev/null || echo "healthcheck.sh: State-Datei nicht schreibbar ($state): Erinnerungen koennen sich wiederholen" >&2
    fi
  else
    if [ -n "$prev_hash" ] && [ "$prev_hash" != "$(printf '' | sha256sum | cut -d' ' -f1)" ]; then
      notify "Bilantiq Healthcheck auf $SERVER_NAME: wieder alles in Ordnung."
    fi
    printf '%s\n%s\n' "$(printf '' | sha256sum | cut -d' ' -f1)" "$now" > "$state" 2>/dev/null || true
  fi
  # Dead-Man's-Switch: nur melden, wenn nichts kritisch ist (Warnungen zaehlen als lebendig).
  if [ "$level" -lt 2 ] && [ -n "$HEARTBEAT_URL" ]; then
    curl -sS -m 15 -o /dev/null "$HEARTBEAT_URL" || echo "healthcheck.sh: Heartbeat fehlgeschlagen" >&2
  fi
fi

exit "$level"
