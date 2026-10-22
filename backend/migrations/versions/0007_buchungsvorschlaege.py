"""begruendung on receipts, konto on ausgaben (KI-Buchungsvorschlaege)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("begruendung", sa.String(500), nullable=True))
    op.add_column("ausgaben", sa.Column("konto", sa.String(10), nullable=False, server_default="6800"))


def downgrade() -> None:
    op.drop_column("ausgaben", "konto")
    op.drop_column("receipts", "begruendung")
