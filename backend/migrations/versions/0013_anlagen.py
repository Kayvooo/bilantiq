"""anlagen (Anlagevermoegen/AfA)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "anlagen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bezeichnung", sa.String(255), nullable=False),
        sa.Column("anschaffungsdatum", sa.Date(), nullable=False),
        sa.Column("anschaffungskosten_netto", sa.Numeric(12, 2), nullable=False),
        sa.Column("nutzungsdauer_jahre", sa.Integer(), nullable=False),
        sa.Column("kategorie", sa.String(100), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE anlagen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY anlagen_mandant_isolation ON anlagen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS anlagen_mandant_isolation ON anlagen")
    op.drop_table("anlagen")
