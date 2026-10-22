"""mandanten.steuerberater_name/-email/-telefon

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mandanten", sa.Column("steuerberater_name", sa.String(255), nullable=True))
    op.add_column("mandanten", sa.Column("steuerberater_email", sa.String(255), nullable=True))
    op.add_column("mandanten", sa.Column("steuerberater_telefon", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("mandanten", "steuerberater_telefon")
    op.drop_column("mandanten", "steuerberater_email")
    op.drop_column("mandanten", "steuerberater_name")
