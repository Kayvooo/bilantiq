"""sonstige_einnahmen

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "sonstige_einnahmen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bezeichnung", sa.String(255), nullable=False),
        sa.Column("betrag_brutto", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("verwendungszweck", sa.String(500), nullable=True),
    )
    if _is_postgres():
        op.execute("ALTER TABLE sonstige_einnahmen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY sonstige_einnahmen_mandant_isolation ON sonstige_einnahmen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS sonstige_einnahmen_mandant_isolation ON sonstige_einnahmen")
    op.drop_table("sonstige_einnahmen")
