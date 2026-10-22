#!/usr/bin/env bash
# Restore-Test: spielt ein Backup in eine ISOLIERTE Wegwerf-Postgres ein und prueft es (Release-Plan 2.5).
# Beruehrt weder Produktion noch Staging: eigene, nur lokal erreichbare Instanz, die am Ende geloescht wird.
#
# Aufruf:
#   BACKUP_AGE_IDENTITY_FILE=/pfad/privater-schluessel \
#     ./scripts/restore-test.sh backups/db_<TS>.sql.gz.age [backups/uploads_<TS>.tar.gz.age]
#
# Pruefungen (alle muessen bestehen, sonst Exit 1):
#   - Pruefsumme gegen manifest_<TS>.sha256 (falls vorhanden)
#   - Einspielen in EINER Transaktion ohne Fehler (fehlende Rollen aus dem Dump werden als NOLOGIN angelegt)
#   - alembic_version == Alembic-Head des Repos (ALLOW_OLDER_HEAD=1 macht daraus nur eine Warnung)
#   - Tabellen vorhanden, Row-Level-Security aktiv und Policies vorhanden
#   - Zeilenzahlen aller Tabellen werden ausgegeben; EXPECT_MIN="mandanten=1,users=1" erzwingt Mindestzahlen
#   - optional: Upload-Archiv entschluesselbar und als tar.gz lesbar
# Misst die Dauer (Entschluesseln+Einspielen und Gesamt).
#
# NICHT geprueft (manuell, siehe docs/rollback.md): Login, Entschluesselung der Spaltenwerte mit den Anwendungsschluesseln
# und Rechnungs-PDF. Dafuer braucht es die Anwendung samt DATA_ENCRYPTION_KEYS.
#
# Engine: RESTORE_TEST_ENGINE=auto|native|docker (auto = docker, wenn vorhanden, sonst native PostgreSQL-Binaries).
# Native: RESTORE_TEST_PORT (Default 54330; 5432 und 54329 sind verboten), PG_BIN fuer das Binaries-Verzeichnis.
# Klartext-SQL liegt waehrend des Tests in einem 0700-Verzeichnis unter RESTORE_TEST_TMP (Default: $XDG_RUNTIME_DIR
# oder /dev/shm, sonst /tmp) und wird am Ende geloescht. Den Test nur auf einer Maschine mit Zugriff auf den privaten Schluessel laufen lassen.
set -euo pipefail
umask 077

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="${RESTORE_TEST_ENGINE:-auto}"
PORT="${RESTORE_TEST_PORT:-54330}"
IDENTITY="${BACKUP_AGE_IDENTITY_FILE:-}"
EXPECT_MIN="${EXPECT_MIN:-}"
ALLOW_OLDER_HEAD="${ALLOW_OLDER_HEAD:-0}"
PG_IMAGE="${PG_IMAGE:-postgres:16}"

fail() { echo "restore-test.sh: FEHLER: $*" >&2; FAILED=1; }
die()  { echo "restore-test.sh: FEHLER: $*" >&2; exit 1; }
info() { echo "restore-test.sh: $*"; }
FAILED=0

DUMP="${1:-}"; UPLOADS="${2:-}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || die "Usage: ./scripts/restore-test.sh <db_dump.sql.gz.age> [uploads.tar.gz.age]"
[ -n "$IDENTITY" ] && [ -f "$IDENTITY" ] || die "BACKUP_AGE_IDENTITY_FILE fehlt oder Datei nicht gefunden."
[ -z "$UPLOADS" ] || [ -f "$UPLOADS" ] || die "Upload-Archiv nicht gefunden: $UPLOADS"
command -v age >/dev/null || die "age nicht gefunden."
case "$PORT" in 5432|54329) die "Port $PORT ist reserviert (lokale Entwicklungs-/Testdatenbank). Anderen RESTORE_TEST_PORT waehlen." ;; esac
case "$PORT" in ''|*[!0-9]*) die "RESTORE_TEST_PORT ist keine Zahl." ;; esac

if [ "$ENGINE" = "auto" ]; then
  if command -v docker >/dev/null 2>&1; then ENGINE=docker; else ENGINE=native; fi
fi

T0=$SECONDS
TMPBASE="${RESTORE_TEST_TMP:-${XDG_RUNTIME_DIR:-/dev/shm}}"
[ -d "$TMPBASE" ] && [ -w "$TMPBASE" ] || { info "WARNUNG: $TMPBASE nicht nutzbar, weiche auf /tmp aus (Klartext-SQL kurzzeitig auf Platte)."; TMPBASE=/tmp; }
WORK="$(mktemp -d "$TMPBASE/bilantiq-restoretest.XXXXXX")"
CNAME="bilantiq-restoretest-$$"
PGSOCK="$(mktemp -d /tmp/bqrt.XXXXXX)"   # kurzer Pfad: Unix-Socket-Pfade vertragen hoechstens 107 Zeichen

cleanup() {
  set +e
  if [ "$ENGINE" = "native" ] && [ -f "$WORK/data/postmaster.pid" ]; then
    "$PG_BIN/pg_ctl" -D "$WORK/data" -m immediate stop >/dev/null 2>&1
  fi
  if [ "$ENGINE" = "docker" ]; then docker rm -f "$CNAME" >/dev/null 2>&1; fi
  rm -rf "$WORK" "$PGSOCK"
}
trap cleanup EXIT

# --- Pruefsumme -----------------------------------------------------------------------------
DUMP_DIR="$(cd "$(dirname "$DUMP")" && pwd)"; DUMP_BASE="$(basename "$DUMP")"
TS="${DUMP_BASE#db_}"; TS="${TS%.sql.gz.age}"
MANIFEST="$DUMP_DIR/manifest_${TS}.sha256"
if [ -f "$MANIFEST" ]; then
  if ( cd "$DUMP_DIR" && grep -F " $DUMP_BASE" "$MANIFEST" | sha256sum -c --quiet - ) ; then info "Pruefsumme ok ($(basename "$MANIFEST"))"
  else die "Pruefsumme des Dumps stimmt nicht mit dem Manifest ueberein (beschaedigt oder unvollstaendig kopiert)."; fi
else
  info "WARNUNG: kein Manifest gefunden, Pruefsumme nicht geprueft."
fi

# --- Alembic-Head des Repos (nur stdlib, ohne Datenbank und ohne App-Secrets) -----------------
REPO_HEAD="$(python3 -I - "$REPO_DIR/backend/migrations/versions" <<'PY'
import ast, pathlib, sys
revs, downs = {}, set()
for f in pathlib.Path(sys.argv[1]).glob("*.py"):
    rev = down = None
    for node in ast.parse(f.read_text()).body:
        t = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            t = node.targets[0].id; v = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            t = node.target.id; v = node.value
        if t == "revision": rev = ast.literal_eval(v)
        elif t == "down_revision": down = ast.literal_eval(v)
    if rev:
        revs[rev] = down
        for d in ([down] if isinstance(down, str) else (down or [])): downs.add(d)
heads = [r for r in revs if r not in downs]
print(heads[0] if len(heads) == 1 else "")
PY
)"
[ -n "$REPO_HEAD" ] || die "Alembic-Head im Repo nicht eindeutig bestimmbar."
info "Alembic-Head im Repo: $REPO_HEAD (Engine: $ENGINE)"

# --- Wegwerf-Postgres starten -----------------------------------------------------------------
if [ "$ENGINE" = "native" ]; then
  PG_BIN="${PG_BIN:-}"
  if [ -z "$PG_BIN" ]; then
    command -v initdb >/dev/null && PG_BIN="$(dirname "$(command -v initdb)")"
    [ -n "$PG_BIN" ] || PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -n1)"
  fi
  [ -x "$PG_BIN/initdb" ] && [ -x "$PG_BIN/pg_ctl" ] && [ -x "$PG_BIN/psql" ] || die "PostgreSQL-Binaries nicht gefunden (PG_BIN setzen)."
  "$PG_BIN/initdb" -D "$WORK/data" -U postgres -A trust --no-sync >/dev/null
  # Nur Unix-Socket im Arbeitsverzeichnis: kein Netzwerkzugriff, kein Konflikt mit laufenden Instanzen.
  "$PG_BIN/pg_ctl" -D "$WORK/data" -o "-p $PORT -k $PGSOCK -c listen_addresses='' -c fsync=off -c synchronous_commit=off -c full_page_writes=off" -w -l "$WORK/pg.log" start >/dev/null \
    || { cat "$WORK/pg.log" >&2; die "Wegwerf-Postgres liess sich nicht starten (Port $PORT belegt?)."; }
  psql_run() { "$PG_BIN/psql" -h "$PGSOCK" -p "$PORT" -U postgres -v ON_ERROR_STOP=1 -X "$@"; }
elif [ "$ENGINE" = "docker" ]; then
  docker run -d --rm --name "$CNAME" --network none --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_HOST_AUTH_METHOD=trust "$PG_IMAGE" -c fsync=off >/dev/null || die "Docker-Container liess sich nicht starten."
  for _ in $(seq 1 60); do docker exec "$CNAME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
  docker exec "$CNAME" pg_isready -U postgres >/dev/null 2>&1 || die "Wegwerf-Postgres wurde nicht bereit."
  psql_run() { docker exec -i "$CNAME" psql -U postgres -v ON_ERROR_STOP=1 -X "$@"; }
else
  die "Unbekannte RESTORE_TEST_ENGINE: $ENGINE"
fi
psql_run -d postgres -qc "CREATE DATABASE restoretest" >/dev/null

# --- Entschluesseln (Dauer messen) und Rollen aus dem Dump anlegen ------------------------------
T1=$SECONDS
PLAIN="$WORK/dump.sql"
if ! { age -d -i "$IDENTITY" "$DUMP" | gunzip -c > "$PLAIN"; }; then
  die "Entschluesseln/Entpacken fehlgeschlagen (falscher Schluessel oder beschaedigte Datei)."
fi
[ -s "$PLAIN" ] || die "entschluesselter Dump ist leer."
ROLES="$(python3 -I - "$PLAIN" <<'PY'
import re, sys
rollen = set()
muster = [r'\bOWNER TO ("[^"]+"|\w+);', r'^GRANT\b.*\bTO ("[^"]+"|\w+)(?: WITH GRANT OPTION)?;$',
          r'^REVOKE\b.*\bFROM ("[^"]+"|\w+);$', r'^CREATE POLICY\b.*\bTO ("[^"]+"|\w+)']
for zeile in open(sys.argv[1], encoding="utf-8", errors="replace"):
    zeile = zeile.rstrip("\n")
    for m in muster:
        for g in re.findall(m, zeile):
            g = g.strip('"')
            if g.lower() not in {"public", "current_user", "session_user", "current_role"}:
                rollen.add(g)
print("\n".join(sorted(rollen)))
PY
)"
for r in $ROLES; do
  psql_run -d postgres -qtAc "SELECT 1 FROM pg_roles WHERE rolname='$r'" | grep -q 1 || { psql_run -d postgres -qc "CREATE ROLE \"$r\" NOLOGIN" >/dev/null; info "Rolle aus dem Dump angelegt (NOLOGIN): $r"; }
done

# --- Einspielen in einer Transaktion ------------------------------------------------------------
info "spiele ein ($(du -h "$PLAIN" | cut -f1) SQL) ..."
if ! { echo "BEGIN;"; cat "$PLAIN"; echo "COMMIT;"; } | psql_run -d restoretest -q >"$WORK/restore.out" 2>"$WORK/restore.err"; then
  head -n 20 "$WORK/restore.err" >&2
  fail "Einspielen fehlgeschlagen (Transaktion zurueckgerollt)."
fi
T2=$SECONDS
rm -f "$PLAIN"

q() { psql_run -d restoretest -qtAF'|' -c "$1"; }

if [ "$FAILED" -eq 0 ]; then
  # --- Alembic-Stand ----------------------------------------------------------------------------
  DB_HEAD="$(q "SELECT string_agg(version_num, ',') FROM alembic_version" 2>/dev/null || true)"
  if [ "$DB_HEAD" = "$REPO_HEAD" ]; then info "Alembic-Stand ok: $DB_HEAD"
  elif [ "$ALLOW_OLDER_HEAD" = "1" ]; then info "WARNUNG: Alembic-Stand '$DB_HEAD' weicht vom Repo-Head '$REPO_HEAD' ab (ALLOW_OLDER_HEAD=1)."
  else fail "Alembic-Stand '${DB_HEAD:-unbekannt}' != Repo-Head '$REPO_HEAD'."; fi

  # --- Struktur, RLS ----------------------------------------------------------------------------
  NTAB="$(q "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
  NRLS="$(q "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity")"
  NPOL="$(q "SELECT count(*) FROM pg_policies WHERE schemaname='public'")"
  NFN="$(q "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'bq\\_%'")"
  info "Tabellen: $NTAB, davon mit RLS: $NRLS, Policies: $NPOL, bq_*-Funktionen: $NFN"
  [ "${NTAB:-0}" -gt 0 ] || fail "keine Tabellen im Schema public."
  [ "${NRLS:-0}" -gt 0 ] && [ "${NPOL:-0}" -gt 0 ] || fail "Row-Level-Security fehlt in der Wiederherstellung (RLS-Tabellen=$NRLS, Policies=$NPOL)."

  # --- Zeilenzahlen -----------------------------------------------------------------------------
  COUNTS="$(q "SELECT table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")"
  info "Zeilenzahlen (Stichprobe aller Tabellen, nur Zahlen, keine Inhalte):"
  echo "$COUNTS" | awk -F'|' '{printf "    %-40s %s\n", $1, $2}'
  if [ -n "$EXPECT_MIN" ]; then
    IFS=',' read -ra PAIRS <<< "$EXPECT_MIN"
    for pair in "${PAIRS[@]}"; do
      tbl="${pair%%=*}"; min="${pair##*=}"
      have="$(echo "$COUNTS" | awk -F'|' -v t="$tbl" '$1==t {print $2}')"
      if [ -z "$have" ]; then fail "erwartete Tabelle fehlt: $tbl"
      elif [ "$have" -lt "$min" ]; then fail "Tabelle $tbl hat $have Zeilen, erwartet mindestens $min."
      else info "Mindestzahl ok: $tbl >= $min ($have)"; fi
    done
  else
    info "Hinweis: EXPECT_MIN nicht gesetzt, es wurden keine Mindest-Zeilenzahlen erzwungen."
  fi
fi

# --- Upload-Archiv (optional) -----------------------------------------------------------------------
if [ -n "$UPLOADS" ]; then
  UP_BASE="$(basename "$UPLOADS")"; UP_TS="${UP_BASE#uploads_}"; UP_TS="${UP_TS%.tar.gz.age}"
  UP_MAN="$(cd "$(dirname "$UPLOADS")" && pwd)/manifest_${UP_TS}.sha256"
  if [ -f "$UP_MAN" ]; then
    ( cd "$(dirname "$UP_MAN")" && grep -F " $UP_BASE" "$UP_MAN" | sha256sum -c --quiet - ) || fail "Pruefsumme des Upload-Archivs stimmt nicht."
  fi
  if NFILES="$(age -d -i "$IDENTITY" "$UPLOADS" | tar tzf - | grep -vc '/$' )"; then info "Upload-Archiv lesbar, $NFILES Dateien"
  else
    # grep -c liefert Exit 1 bei 0 Treffern: leeres, aber lesbares Archiv von echtem Fehler unterscheiden.
    age -d -i "$IDENTITY" "$UPLOADS" | tar tzf - >/dev/null 2>&1 && info "Upload-Archiv lesbar, 0 Dateien (leeres Volume?)" || fail "Upload-Archiv nicht lesbar."
  fi
fi

T3=$SECONDS
echo
info "Dauer: Entschluesseln+Einspielen $((T2 - T1)) s, Pruefungen $((T3 - T2)) s, gesamt $((T3 - T0)) s (inkl. Start der Wegwerf-Instanz)"
if [ "$FAILED" -eq 0 ]; then
  echo "RESTORE-TEST: BESTANDEN ($DUMP_BASE)"
else
  echo "RESTORE-TEST: FEHLGESCHLAGEN ($DUMP_BASE)" >&2
  exit 1
fi
