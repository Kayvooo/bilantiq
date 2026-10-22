"""produkte (Produktkatalog)

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "produkte",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bezeichnung", sa.String(255), nullable=False),
        sa.Column("beschreibung", sa.String(500), nullable=True),
        sa.Column("einzelpreis", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
        sa.Column("einheit", sa.String(50), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    if _is_postgres():
        op.execute("ALTER TABLE produkte ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY produkte_mandant_isolation ON produkte "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS produkte_mandant_isolation ON produkte")
    op.drop_table("produkte")
