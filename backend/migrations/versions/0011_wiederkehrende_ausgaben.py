"""wiederkehrende_ausgaben + ausgaben.receipt_id nullable

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("ausgaben") as batch_op:
        batch_op.alter_column("receipt_id", existing_type=sa.String(36), nullable=True)

    op.create_table(
        "wiederkehrende_ausgaben",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bezeichnung", sa.String(255), nullable=False),
        sa.Column("anbieter", sa.String(255), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
        sa.Column("kategorie", sa.String(100), nullable=False),
        sa.Column("intervall", sa.String(20), nullable=False),
        sa.Column("naechstes_datum", sa.Date(), nullable=False),
        sa.Column("enddatum", sa.Date(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE wiederkehrende_ausgaben ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY wiederkehrende_ausgaben_mandant_isolation ON wiederkehrende_ausgaben "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS wiederkehrende_ausgaben_mandant_isolation ON wiederkehrende_ausgaben")
    op.drop_table("wiederkehrende_ausgaben")
    with op.batch_alter_table("ausgaben") as batch_op:
        batch_op.alter_column("receipt_id", existing_type=sa.String(36), nullable=False)
