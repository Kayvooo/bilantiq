"""kassenbuch_eintraege

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "kassenbuch_eintraege",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("typ", sa.String(10), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE kassenbuch_eintraege ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY kassenbuch_eintraege_mandant_isolation ON kassenbuch_eintraege "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS kassenbuch_eintraege_mandant_isolation ON kassenbuch_eintraege")
    op.drop_table("kassenbuch_eintraege")
