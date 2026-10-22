"""Security hardening: AES-GCM fields, sessions and verified email changes.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

from cryptography.fernet import Fernet

from app.config import settings
from app.core.crypto import decrypt_field_compat
from app.core.key_management import decrypt_text, encrypt_text, is_encrypted_text


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


_LEGACY_ENCRYPTED_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "email_encrypted": "legacy-field",
        "mfa_secret_encrypted": "legacy-field",
    },
    "mitarbeitende": {
        "vorname_encrypted": "legacy-field",
        "nachname_encrypted": "legacy-field",
    },
    "invoices": {
        "zahllink_token_verschluesselt": "legacy-field",
    },
}

_ENCRYPTED_COLUMNS: dict[str, dict[str, str]] = {
    "mandanten": {
        "firmenname": "mandant.firmenname",
        "ust_id": "mandant.ust_id",
        "steuernummer": "mandant.steuernummer",
        "adresse": "mandant.adresse",
        "datev_beraternummer": "mandant.datev_beraternummer",
        "datev_mandantennummer": "mandant.datev_mandantennummer",
        "steuerberater_name": "mandant.steuerberater_name",
        "steuerberater_email": "mandant.steuerberater_email",
        "steuerberater_telefon": "mandant.steuerberater_telefon",
        "fusszeile_text": "mandant.fusszeile_text",
        "iban": "mandant.iban",
        "bic": "mandant.bic",
    },
    "briefpapiere": {"name": "briefpapier.name"},
    "kontakte": {
        "name": "kontakt.name",
        "strasse": "kontakt.strasse",
        "plz": "kontakt.plz",
        "ort": "kontakt.ort",
        "ust_id": "kontakt.ust_id",
        "email": "kontakt.email",
        "kundennummer": "kontakt.kundennummer",
    },
    "invoices": {
        "betreff": "invoice.betreff",
        "kopftext": "invoice.kopftext",
        "fusstext": "invoice.fusstext",
        "referenznummer": "invoice.referenznummer",
        "kostenstelle": "invoice.kostenstelle",
    },
    "invoice_positionen": {"beschreibung": "invoice_position.beschreibung"},
    "receipts": {
        "anbieter": "receipt.anbieter",
        "begruendung": "receipt.begruendung",
    },
    "ausgaben": {"anbieter": "ausgabe.anbieter"},
    "quote_positionen": {"beschreibung": "quote_position.beschreibung"},
    "auftragsbestaetigung_positionen": {"beschreibung": "auftrag_position.beschreibung"},
    "lieferschein_positionen": {"beschreibung": "auftrag_position.beschreibung"},
    "kassenbuch_eintraege": {"beschreibung": "kassenbuch.beschreibung"},
    "sonstige_einnahmen": {
        "bezeichnung": "einnahme.bezeichnung",
        "verwendungszweck": "einnahme.verwendungszweck",
    },
    "anlagen": {
        "bezeichnung": "anlage.bezeichnung",
        "kategorie": "anlage.kategorie",
    },
    "wiederkehrende_rechnungen": {"bezeichnung": "wiederkehrend.bezeichnung"},
    "wiederkehrende_rechnung_positionen": {"beschreibung": "wiederkehrend_position.beschreibung"},
    "wiederkehrende_ausgaben": {
        "bezeichnung": "wiederkehrende_ausgabe.bezeichnung",
        "anbieter": "wiederkehrende_ausgabe.anbieter",
    },
    "produkte": {
        "bezeichnung": "produkt.bezeichnung",
        "beschreibung": "produkt.beschreibung",
    },
    "lagerbewegungen": {
        "grund": "lagerbewegung.grund",
    },
    "audit_log_eintraege": {
        "kontext": "audit.kontext",
    },
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _widen_sensitive_columns() -> None:
    for table, columns in _ENCRYPTED_COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(column, type_=sa.Text())
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email_encrypted", type_=sa.Text())
        batch.alter_column("mfa_secret_encrypted", type_=sa.Text())


def _encrypt_existing() -> None:
    bind = op.get_bind()
    for table, columns in _ENCRYPTED_COLUMNS.items():
        for column, purpose in columns.items():
            rows = bind.execute(
                sa.text(f'SELECT id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).mappings()
            for row in rows:
                value = row["value"]
                if value is None or is_encrypted_text(str(value)):
                    continue
                encrypted = encrypt_text(str(value), purpose=purpose)
                bind.execute(
                    sa.text(f'UPDATE "{table}" SET "{column}" = :value WHERE id = :id'),
                    {"value": encrypted, "id": row["id"]},
                )


def _reencrypt_legacy_ciphertexts() -> None:
    bind = op.get_bind()
    for table, columns in _LEGACY_ENCRYPTED_COLUMNS.items():
        for column, purpose in columns.items():
            rows = bind.execute(
                sa.text(f'SELECT id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).mappings()
            for row in rows:
                value = str(row["value"])
                if is_encrypted_text(value):
                    continue
                plaintext = decrypt_field_compat(value, purpose=purpose)
                encrypted = encrypt_text(plaintext, purpose=purpose)
                bind.execute(
                    sa.text(f'UPDATE "{table}" SET "{column}" = :value WHERE id = :id'),
                    {"value": encrypted, "id": row["id"]},
                )


def _restore_legacy_ciphertexts() -> None:
    bind = op.get_bind()
    legacy = Fernet(settings.field_encryption_key.encode())
    for table, columns in _LEGACY_ENCRYPTED_COLUMNS.items():
        for column, purpose in columns.items():
            rows = bind.execute(
                sa.text(f'SELECT id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).mappings()
            for row in rows:
                value = str(row["value"])
                if not is_encrypted_text(value):
                    continue
                plaintext = decrypt_text(value, purpose=purpose)
                restored = legacy.encrypt(plaintext.encode()).decode()
                bind.execute(
                    sa.text(f'UPDATE "{table}" SET "{column}" = :value WHERE id = :id'),
                    {"value": restored, "id": row["id"]},
                )


def _decrypt_existing() -> None:
    bind = op.get_bind()
    for table, columns in _ENCRYPTED_COLUMNS.items():
        for column, purpose in columns.items():
            rows = bind.execute(
                sa.text(f'SELECT id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
            ).mappings()
            for row in rows:
                value = str(row["value"])
                if not is_encrypted_text(value):
                    continue
                plaintext = decrypt_text(value, purpose=purpose)
                bind.execute(
                    sa.text(f'UPDATE "{table}" SET "{column}" = :value WHERE id = :id'),
                    {"value": plaintext, "id": row["id"]},
                )


def upgrade() -> None:
    _widen_sensitive_columns()

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_pending_secret_encrypted", sa.Text(), nullable=True))
        batch.add_column(sa.Column("mfa_pending_erstellt_am", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("security_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("passwort_geaendert_am", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("email_geaendert_am", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("laeuft_ab_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("widerrufen_am", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_mandant_id", "auth_sessions", ["mandant_id"])

    op.create_table(
        "email_aenderungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False),
        sa.Column("neue_email", sa.Text(), nullable=False),
        sa.Column("neue_email_lookup_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("versuche", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ablauf_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_aenderungen_user_id", "email_aenderungen", ["user_id"])
    op.create_index("ix_email_aenderungen_mandant_id", "email_aenderungen", ["mandant_id"])
    op.create_index("ix_email_aenderungen_neue_email_lookup_hash", "email_aenderungen", ["neue_email_lookup_hash"])

    _encrypt_existing()
    _reencrypt_legacy_ciphertexts()

    if _is_postgres():
        op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY auth_sessions_mandant_isolation ON auth_sessions
            USING (mandant_id::text = current_setting('app.current_mandant_id', true))
            """
        )
        op.execute("ALTER TABLE email_aenderungen ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY email_aenderungen_mandant_isolation ON email_aenderungen
            USING (mandant_id::text = current_setting('app.current_mandant_id', true))
            """
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS email_aenderungen_mandant_isolation ON email_aenderungen")
        op.execute("DROP POLICY IF EXISTS auth_sessions_mandant_isolation ON auth_sessions")

    _decrypt_existing()
    _restore_legacy_ciphertexts()
    op.drop_index("ix_email_aenderungen_neue_email_lookup_hash", table_name="email_aenderungen")
    op.drop_index("ix_email_aenderungen_mandant_id", table_name="email_aenderungen")
    op.drop_index("ix_email_aenderungen_user_id", table_name="email_aenderungen")
    op.drop_table("email_aenderungen")
    op.drop_index("ix_auth_sessions_mandant_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_geaendert_am")
        batch.drop_column("passwort_geaendert_am")
        batch.drop_column("security_version")
        batch.drop_column("mfa_pending_erstellt_am")
        batch.drop_column("mfa_pending_secret_encrypted")
