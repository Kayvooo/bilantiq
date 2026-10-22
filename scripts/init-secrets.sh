#!/usr/bin/env bash
# Erstellt lokale Produktionssecrets mit restriktiven Rechten.
# Das SMTP-Passwort wird als SET_ME-Platzhalter angelegt; die App behandelt SET_ME wie "nicht gesetzt", E-Mail-Versand
# und "Passwort vergessen" bleiben dann abgeschaltet (SMTP ist optional). Wer E-Mail nutzen will, ersetzt die Datei
# smtp_password durch das echte Passwort und setzt SMTP_HOST/SMTP_USER/SMTP_ABSENDER in .env.prod.
set -euo pipefail

SECRET_DIR="${BILANTIQ_SECRETS_DIR:-/opt/bilantiq/secrets}"
POSTGRES_USER="${POSTGRES_USER:-bilantiq}"
POSTGRES_DB="${POSTGRES_DB:-bilantiq}"
POSTGRES_RUNTIME_USER="${POSTGRES_RUNTIME_USER:-bilantiq_runtime}"
APP_UID="${BILANTIQ_APP_UID:-1000}"

# Namen werden in eine URL geschrieben; die Passwortgeneratoren liefern URL-sichere Zeichen.
for name in "$POSTGRES_USER" "$POSTGRES_DB" "$POSTGRES_RUNTIME_USER"; do
  [[ "$name" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || { echo "Datenbank-/Rollennamen: nur kleine SQL-Bezeichner erlaubt." >&2; exit 1; }
done
[[ "$APP_UID" =~ ^[0-9]+$ ]] || { echo "BILANTIQ_APP_UID muss numerisch sein." >&2; exit 1; }
[ "$POSTGRES_RUNTIME_USER" != "$POSTGRES_USER" ] || { echo "Admin- und Laufzeitrolle muessen verschieden sein." >&2; exit 1; }

umask 077
mkdir -p "$SECRET_DIR"
chmod 700 "$SECRET_DIR"

write_if_missing() {
  local path="$1"
  local value="$2"
  if [ ! -e "$path" ]; then
    printf '%s' "$value" > "$path"
    chmod 600 "$path"
  fi
}

py() { python3 -c "$1"; }

DB_PASSWORD="$(py 'import secrets; print(secrets.token_urlsafe(36))')"
write_if_missing "$SECRET_DIR/postgres_password" "$DB_PASSWORD"
# Falls das Passwort bereits existierte, fuer die URL genau dieses lesen.
DB_PASSWORD="$(cat "$SECRET_DIR/postgres_password")"
write_if_missing "$SECRET_DIR/migration_database_url" "postgresql+psycopg://${POSTGRES_USER}:${DB_PASSWORD}@postgres:5432/${POSTGRES_DB}"
write_if_missing "$SECRET_DIR/database_url" "postgresql+psycopg://${POSTGRES_RUNTIME_USER}:$(py 'import secrets; print(secrets.token_urlsafe(36))')@postgres:5432/${POSTGRES_DB}"

write_if_missing "$SECRET_DIR/jwt_secret" "$(py 'import secrets; print(secrets.token_hex(32))')"
write_if_missing "$SECRET_DIR/field_encryption_key" "$(py 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
write_if_missing "$SECRET_DIR/email_lookup_secret" "$(py 'import secrets; print(secrets.token_hex(32))')"
write_if_missing "$SECRET_DIR/blind_index_secret" "$(py 'import secrets; print(secrets.token_urlsafe(48))')"
write_if_missing "$SECRET_DIR/data_encryption_keys" "$(py 'import base64,secrets; print("v1:"+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))')"

write_if_missing "$SECRET_DIR/smtp_password" "SET_ME"

# Lokale Compose-Secrets sind Bind-Mounts: 0600/root waere fuer USER app (UID 1000) unlesbar.
# Beide Backend-Prozesse laufen als UID 1000. Die Admin-URL ist nur im Migrator gemountet;
# die Host-Verzeichnissperre bleibt bestehen. Das Postgres-Initialpasswort bleibt beim Betreiber.
CONTAINER_SECRETS=(migration_database_url database_url jwt_secret field_encryption_key email_lookup_secret blind_index_secret data_encryption_keys smtp_password)
for name in "${CONTAINER_SECRETS[@]}"; do
  chmod 600 "$SECRET_DIR/$name"
  if [ "$(id -u)" = "0" ]; then
    chown "$APP_UID:$APP_UID" "$SECRET_DIR/$name"
  elif [ "$(id -u)" != "$APP_UID" ]; then
    echo "Secret-Eigentuemer passt nicht zur Container-UID $APP_UID. Siehe docs/security-runtime.md." >&2
    exit 1
  fi
done

# Alte Admin-URLs niemals still durch neue Credentials ersetzen.
if ! python3 - "$SECRET_DIR/database_url" "$POSTGRES_USER" <<'PY'
import sys
from pathlib import Path
from urllib.parse import urlsplit
url = urlsplit(Path(sys.argv[1]).read_text().strip().replace('postgresql+psycopg:', 'postgresql:', 1))
raise SystemExit(1 if url.username == sys.argv[2] else 0)
PY
then
  echo "database_url enthaelt noch die Admin-Rolle. Expliziter Upgrade-Schritt in docs/security-runtime.md erforderlich." >&2
  exit 1
fi

echo "Secrets liegen unter: $SECRET_DIR"
echo "Rechte: Verzeichnis 700, Dateien 600; API-Secrets fuer Container-UID $APP_UID lesbar."
echo "Optional: SET_ME in smtp_password durch das SMTP-Passwort ersetzen (sonst ist E-Mail abgeschaltet)."
echo
echo "WICHTIG: Sichere data_encryption_keys (und die uebrigen Dateien) GETRENNT vom Datenbank-Backup,"
echo "z. B. im Passwortmanager und ausgedruckt im Safe. Ohne diesen Schluessel sind alle verschluesselten"
echo "Daten (Belege, Kontakte, Rechnungsdetails ...) unwiederbringlich verloren, auch mit intaktem Backup."
