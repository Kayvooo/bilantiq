"""lagerbestand (manuelle Warenwirtschaft auf dem Produktkatalog)

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("produkte") as batch_op:
        batch_op.add_column(
            sa.Column("lagerbestand_aktiv", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "lagerbewegungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("produkt_id", sa.String(36), sa.ForeignKey("produkte.id"), nullable=False, index=True),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("typ", sa.String(10), nullable=False),
        sa.Column("menge", sa.Numeric(12, 3), nullable=False),
        sa.Column("grund", sa.String(500), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE lagerbewegungen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY lagerbewegungen_mandant_isolation ON lagerbewegungen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS lagerbewegungen_mandant_isolation ON lagerbewegungen")
    op.drop_table("lagerbewegungen")

    with op.batch_alter_table("produkte") as batch_op:
        batch_op.drop_column("lagerbestand_aktiv")
