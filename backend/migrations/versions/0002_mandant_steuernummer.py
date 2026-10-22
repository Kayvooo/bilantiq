"""add steuernummer to mandanten (EN16931 seller tax id fallback when no USt-IdNr)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mandanten", sa.Column("steuernummer", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("mandanten", "steuernummer")
