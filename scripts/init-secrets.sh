#!/usr/bin/env bash
# Erstellt lokale Produktionssecrets mit restriktiven Rechten.
# Das SMTP-Passwort wird als SET_ME-Platzhalter angelegt; die App behandelt SET_ME wie "nicht gesetzt", E-Mail-Versand
# und "Passwort vergessen" bleiben dann abgeschaltet (SMTP ist optional). Wer E-Mail nutzen will, ersetzt die Datei
# smtp_password durch das echte Passwort und setzt SMTP_HOST/SMTP_USER/SMTP_ABSENDER in .env.prod.
set -euo pipefail

SECRET_DIR="${BILANTIQ_SECRETS_DIR:-/opt/bilantiq/secrets}"
POSTGRES_USER="${POSTGRES_USER:-bilantiq}"
POSTGRES_DB="${POSTGRES_DB:-bilantiq}"

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
write_if_missing "$SECRET_DIR/database_url" "postgresql+psycopg://${POSTGRES_USER}:${DB_PASSWORD}@postgres:5432/${POSTGRES_DB}"

write_if_missing "$SECRET_DIR/jwt_secret" "$(py 'import secrets; print(secrets.token_hex(32))')"
write_if_missing "$SECRET_DIR/field_encryption_key" "$(py 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
write_if_missing "$SECRET_DIR/email_lookup_secret" "$(py 'import secrets; print(secrets.token_hex(32))')"
write_if_missing "$SECRET_DIR/blind_index_secret" "$(py 'import secrets; print(secrets.token_urlsafe(48))')"
write_if_missing "$SECRET_DIR/data_encryption_keys" "$(py 'import base64,secrets; print("v1:"+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))')"

write_if_missing "$SECRET_DIR/smtp_password" "SET_ME"

echo "Secrets liegen unter: $SECRET_DIR"
echo "Rechte: Verzeichnis 700, Dateien 600."
echo "Optional: SET_ME in smtp_password durch das SMTP-Passwort ersetzen (sonst ist E-Mail abgeschaltet)."
echo
echo "WICHTIG: Sichere data_encryption_keys (und die uebrigen Dateien) GETRENNT vom Datenbank-Backup,"
echo "z. B. im Passwortmanager und ausgedruckt im Safe. Ohne diesen Schluessel sind alle verschluesselten"
echo "Daten (Belege, Kontakte, Rechnungsdetails ...) unwiederbringlich verloren, auch mit intaktem Backup."
