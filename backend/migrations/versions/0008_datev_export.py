"""datev_beraternummer, datev_mandantennummer on mandanten (DATEV-Export)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mandanten", sa.Column("datev_beraternummer", sa.String(10), nullable=True))
    op.add_column("mandanten", sa.Column("datev_mandantennummer", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("mandanten", "datev_mandantennummer")
    op.drop_column("mandanten", "datev_beraternummer")
