"""Dauerhafter Online-Zahllink fuer Rechnungen.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("zahllink_token_verschluesselt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("zahllink_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("stripe_checkout_session_versuch", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("stripe_checkout_session_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("online_bezahlt_am", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_invoices_zahllink_token_hash", ["zahllink_token_hash"])


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_constraint("uq_invoices_zahllink_token_hash", type_="unique")
        batch_op.drop_column("online_bezahlt_am")
        batch_op.drop_column("stripe_checkout_session_expires_at")
        batch_op.drop_column("stripe_checkout_session_versuch")
        batch_op.drop_column("stripe_checkout_session_id")
        batch_op.drop_column("zahllink_token_hash")
        batch_op.drop_column("zahllink_token_verschluesselt")
