"""bezahlt_am on invoices, mahnungen table + Postgres RLS

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column("invoices", sa.Column("bezahlt_am", sa.Date, nullable=True))

    op.create_table(
        "mahnungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False, index=True),
        sa.Column("stufe", sa.Integer, nullable=False),
        sa.Column("mahngebuehr", sa.Numeric(12, 2), nullable=False),
        sa.Column("neue_faelligkeit", sa.Date, nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )

    if not _is_postgres():
        return

    op.execute("ALTER TABLE mahnungen ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mahnungen_mandant_isolation ON mahnungen
        USING (mandant_id::text = current_setting('app.current_mandant_id', true))
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS mahnungen_mandant_isolation ON mahnungen")
    op.drop_table("mahnungen")
    op.drop_column("invoices", "bezahlt_am")
