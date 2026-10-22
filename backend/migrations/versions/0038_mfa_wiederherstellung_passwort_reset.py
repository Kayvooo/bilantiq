"""MFA-Wiederherstellungscodes, TOTP-Replay-Schutz und Passwort-Reset-Tokens

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-14

- ``users.mfa_letzter_zeitschritt``: letzter verbrauchter TOTP-Zeitschritt (Replay-Schutz).
- ``mfa_wiederherstellungscodes``: Einmalcodes als Ersatz fuer den TOTP-Code, nur als HMAC-Hash.
- ``passwort_reset_tokens``: Einmal-Token fuer "Passwort vergessen", nur als HMAC-Hash.

Beide neuen Tabellen tragen ``mandant_id`` und bekommen dieselbe Mandantenisolation wie auth_sessions (0029/0037).
Alle Zugriffe laufen mit gesetztem Mandantenkontext (Pre-MFA-Token bzw. Nachschlagen ueber ``bq_mandant_des_nutzers``
aus 0035), deshalb ist keine neue SECURITY-DEFINER-Funktion noetig. Nur Postgres; SQLite kennt keine RLS.
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_TABELLEN = ("mfa_wiederherstellungscodes", "passwort_reset_tokens")


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("mfa_letzter_zeitschritt", sa.Integer(), nullable=True))

    op.create_table(
        "mfa_wiederherstellungscodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verbraucht_am", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mfa_wiederherstellungscodes_user_id", "mfa_wiederherstellungscodes", ["user_id"])
    op.create_index("ix_mfa_wiederherstellungscodes_mandant_id", "mfa_wiederherstellungscodes", ["mandant_id"])

    op.create_table(
        "passwort_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ablauf_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verbraucht_am", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_passwort_reset_tokens_user_id", "passwort_reset_tokens", ["user_id"])
    op.create_index("ix_passwort_reset_tokens_mandant_id", "passwort_reset_tokens", ["mandant_id"])

    if _is_postgres():
        for tabelle in _TABELLEN:
            op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {tabelle}_mandant_isolation ON {tabelle} "
                "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
            )


def downgrade() -> None:
    if _is_postgres():
        for tabelle in reversed(_TABELLEN):
            op.execute(f"DROP POLICY IF EXISTS {tabelle}_mandant_isolation ON {tabelle}")
    op.drop_index("ix_passwort_reset_tokens_mandant_id", table_name="passwort_reset_tokens")
    op.drop_index("ix_passwort_reset_tokens_user_id", table_name="passwort_reset_tokens")
    op.drop_table("passwort_reset_tokens")
    op.drop_index("ix_mfa_wiederherstellungscodes_mandant_id", table_name="mfa_wiederherstellungscodes")
    op.drop_index("ix_mfa_wiederherstellungscodes_user_id", table_name="mfa_wiederherstellungscodes")
    op.drop_table("mfa_wiederherstellungscodes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mfa_letzter_zeitschritt")
