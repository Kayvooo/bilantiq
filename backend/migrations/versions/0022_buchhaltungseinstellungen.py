"""buchhaltungseinstellungen

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "buchhaltungseinstellungen",
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), primary_key=True),
        sa.Column("standard_zahlungsziel_tage", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("standard_ust_satz", sa.Numeric(5, 2), nullable=False, server_default="19.00"),
        sa.Column("kleinunternehmer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    if _is_postgres():
        op.execute("ALTER TABLE buchhaltungseinstellungen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY buchhaltungseinstellungen_mandant_isolation ON buchhaltungseinstellungen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute(
            "DROP POLICY IF EXISTS buchhaltungseinstellungen_mandant_isolation "
            "ON buchhaltungseinstellungen"
        )
    op.drop_table("buchhaltungseinstellungen")
