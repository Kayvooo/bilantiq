"""initial schema: mandanten, users, mitgliedschaften, audit log + Postgres RLS

Revision ID: 0001
Revises:
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "mandanten",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("firmenname", sa.String(255), nullable=False),
        sa.Column("ust_id", sa.String(20), nullable=True),
        sa.Column("adresse", sa.String(500), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_encrypted", sa.String(500), nullable=False),
        sa.Column("email_lookup_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("passwort_hash", sa.String(255), nullable=False),
        sa.Column("mfa_secret_encrypted", sa.String(500), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geloescht_am", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "mitgliedschaften",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("rolle", sa.String(20), nullable=False, server_default="owner"),
    )

    op.create_table(
        "audit_log_eintraege",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("aktion", sa.String(100), nullable=False),
        sa.Column("kontext", sa.String(2000), nullable=False, server_default=""),
        sa.Column("zeitpunkt", sa.DateTime(timezone=True), nullable=False),
    )

    if not _is_postgres():
        return

    # --- Row-level security -------------------------------------------------
    # app.current_mandant_id is set per-transaction in app/db.py::set_rls_mandant.
    # Every mandant-scoped table gets a policy; the app-level filters in
    # app/core/rls.py stay in place too (SQLite has no RLS, and RLS alone can
    # silently miss a table someone forgot to add a policy for).
    op.execute("ALTER TABLE mitgliedschaften ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mitgliedschaften_mandant_isolation ON mitgliedschaften
        USING (mandant_id::text = current_setting('app.current_mandant_id', true))
        """
    )

    op.execute("ALTER TABLE audit_log_eintraege ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_log_mandant_isolation ON audit_log_eintraege
        USING (mandant_id IS NULL OR mandant_id::text = current_setting('app.current_mandant_id', true))
        """
    )

    op.execute("ALTER TABLE mandanten ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mandanten_self_only ON mandanten
        USING (id::text = current_setting('app.current_mandant_id', true))
        """
    )

    # --- Append-only audit log, enforced in the database too ----------------
    # Defense in depth alongside the SQLAlchemy before_flush guard in
    # app/core/audit_log.py: even a raw SQL UPDATE/DELETE against this table
    # is rejected by Postgres itself, not just by the ORM.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_audit_log_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log_eintraege ist unveraenderlich (append-only)';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log_eintraege
        FOR EACH ROW EXECUTE FUNCTION forbid_audit_log_mutation()
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log_eintraege")
        op.execute("DROP FUNCTION IF EXISTS forbid_audit_log_mutation")
        op.execute("DROP POLICY IF EXISTS mandanten_self_only ON mandanten")
        op.execute("DROP POLICY IF EXISTS audit_log_mandant_isolation ON audit_log_eintraege")
        op.execute("DROP POLICY IF EXISTS mitgliedschaften_mandant_isolation ON mitgliedschaften")

    op.drop_table("audit_log_eintraege")
    op.drop_table("mitgliedschaften")
    op.drop_table("users")
    op.drop_table("mandanten")
