"""Premium-Tarife und globale Stripe-Webhook-Idempotenz.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Diese Tabelle enthaelt ausschliesslich Stripe-Event-IDs zur technischen
    # Idempotenz. Sie hat bewusst keine Mandantendaten, keinen FK und keine RLS.
    op.create_table(
        "webhook_ereignisse",
        sa.Column("stripe_event_id", sa.String(255), primary_key=True),
        sa.Column("verarbeitet_am", sa.DateTime(timezone=True), nullable=False),
    )

    # batch_alter_table erzeugt die UNIQUE-Constraints auch bei SQLite, dessen
    # ALTER TABLE keine nachtraeglichen Constraints unterstuetzt.
    with op.batch_alter_table("mandanten") as batch_op:
        batch_op.add_column(
            sa.Column("tarif", sa.String(20), nullable=False, server_default="free")
        )
        batch_op.add_column(
            sa.Column("tarif_status", sa.String(30), nullable=False, server_default="active")
        )
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("tarif_gueltig_bis", sa.Date(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_mandanten_stripe_customer_id", ["stripe_customer_id"]
        )
        batch_op.create_unique_constraint(
            "uq_mandanten_stripe_subscription_id", ["stripe_subscription_id"]
        )


def downgrade() -> None:
    # Die globale Tabelle zuerst entfernen, anschliessend die fuenf Mandant-Felder.
    op.drop_table("webhook_ereignisse")

    with op.batch_alter_table("mandanten") as batch_op:
        batch_op.drop_constraint("uq_mandanten_stripe_subscription_id", type_="unique")
        batch_op.drop_constraint("uq_mandanten_stripe_customer_id", type_="unique")
        batch_op.drop_column("tarif_gueltig_bis")
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
        batch_op.drop_column("tarif_status")
        batch_op.drop_column("tarif")
