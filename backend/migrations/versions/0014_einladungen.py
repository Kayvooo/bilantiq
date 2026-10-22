"""einladungen (Benutzerverwaltung / Mehrbenutzer-Beitritt)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "einladungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column("rolle", sa.String(20), nullable=False, server_default="mitglied"),
        sa.Column("erstellt_von", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ablauf_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eingeloest_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("widerrufen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    if _is_postgres():
        op.execute("ALTER TABLE einladungen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY einladungen_mandant_isolation ON einladungen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS einladungen_mandant_isolation ON einladungen")
    op.drop_table("einladungen")
