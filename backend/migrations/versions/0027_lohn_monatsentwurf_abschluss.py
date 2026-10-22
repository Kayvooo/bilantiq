"""Abschluss-Zeitstempel fuer Lohn-Monatsentwuerfe.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lohn_monatsentwuerfe") as batch_op:
        batch_op.add_column(sa.Column("abgeschlossen_am", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lohn_monatsentwuerfe") as batch_op:
        batch_op.drop_column("abgeschlossen_am")
