#!/usr/bin/env bash
# Startet eine temporäre lokale Postgres-Instanz, spielt die Migrationen ein, legt die Laufzeitrolle ohne
# BYPASSRLS an und lässt die Testsuite als diese Rolle laufen (Mandantentrennung, siehe docs/specs/rls-postgres.md).
# Voraussetzung: PostgreSQL-Binaries (initdb, pg_ctl, psql) im PATH, Python-Umgebung mit den Abhängigkeiten.
# Aufruf aus backend/:  scripts/rls_testlauf.sh [pytest-Argumente]      Python: PYTHON=… (Standard .venv/bin/python)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
PORT="${PGTEST_PORT:-54329}"
WURZEL="$(mktemp -d /tmp/bq-pg.XXXXXX)"   # kurzer Pfad: Unix-Sockets vertragen höchstens 107 Zeichen
trap 'pg_ctl -D "$WURZEL/daten" stop -m fast >/dev/null 2>&1 || true; rm -rf "$WURZEL"' EXIT

initdb -D "$WURZEL/daten" -U postgres --auth=trust -E UTF8 >/dev/null
pg_ctl -D "$WURZEL/daten" -o "-p $PORT -k $WURZEL -c listen_addresses=127.0.0.1" -l "$WURZEL/pg.log" -w start >/dev/null
psql -q -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -c "create database bq_test" >/dev/null

# Zugangsdaten aus der Umgebung oder .env, aber nie echte SMTP-Werte in Tests
if [ -f .env ]; then set -a; . ./.env; set +a; fi
# Ohne .env: Wegwerf-Schlüssel nur für diesen Testlauf
export JWT_SECRET="${JWT_SECRET:-$("$PYTHON" -c 'import secrets;print(secrets.token_hex(32))')}"
export EMAIL_LOOKUP_SECRET="${EMAIL_LOOKUP_SECRET:-$("$PYTHON" -c 'import secrets;print(secrets.token_hex(32))')}"
export FIELD_ENCRYPTION_KEY="${FIELD_ENCRYPTION_KEY:-$("$PYTHON" -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')}"
export BLIND_INDEX_SECRET="${BLIND_INDEX_SECRET:-$("$PYTHON" -c 'import secrets;print(secrets.token_urlsafe(48))')}"
export DATA_ENCRYPTION_KEYS="${DATA_ENCRYPTION_KEYS:-v1:$("$PYTHON" -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))')}"
export DATA_ENCRYPTION_ACTIVE_KID="${DATA_ENCRYPTION_ACTIVE_KID:-v1}"
export SMTP_HOST=smtp.test.invalid SMTP_USER=tests@example.invalid SMTP_PASSWORD=test-password

ADMIN="postgresql+psycopg://postgres@127.0.0.1:$PORT/bq_test"
DATABASE_URL="$ADMIN" "$PYTHON" -m alembic upgrade head >/dev/null
psql -q -h 127.0.0.1 -p "$PORT" -U postgres -d bq_test -v rolle=bilantiq_runtime -v passwort=rt-test -f scripts/runtime_rolle.sql >/dev/null

export TEST_DATABASE_ADMIN_URL="$ADMIN"
export DATABASE_URL="postgresql+psycopg://bilantiq_runtime:rt-test@127.0.0.1:$PORT/bq_test"
"$PYTHON" -m pytest -p no:cacheprovider "${@:--q}"
