"""mandanten.rechnungsvorlage/-akzentfarbe/-logo/-fusszeile

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mandanten", sa.Column("rechnungsvorlage", sa.String(20), nullable=True))
    op.add_column("mandanten", sa.Column("akzentfarbe", sa.String(7), nullable=True))
    op.add_column("mandanten", sa.Column("logo_referenz", sa.String(500), nullable=True))
    op.add_column("mandanten", sa.Column("fusszeile_text", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("mandanten", "fusszeile_text")
    op.drop_column("mandanten", "logo_referenz")
    op.drop_column("mandanten", "akzentfarbe")
    op.drop_column("mandanten", "rechnungsvorlage")
