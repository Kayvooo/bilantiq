"""e-rechnung empfang (XRechnung/ZUGFeRD lesen statt schaetzen)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.add_column(sa.Column("beleg_typ", sa.String(20), nullable=False, server_default="ocr"))
        batch_op.add_column(sa.Column("rechnungsnummer", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("faelligkeit", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("iban", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("e_rechnung_daten", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("dedupe_key", sa.String(64), nullable=True))
        batch_op.create_index("ix_receipts_dedupe_key", ["dedupe_key"])


def downgrade() -> None:
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.drop_index("ix_receipts_dedupe_key")
        batch_op.drop_column("dedupe_key")
        batch_op.drop_column("e_rechnung_daten")
        batch_op.drop_column("iban")
        batch_op.drop_column("faelligkeit")
        batch_op.drop_column("rechnungsnummer")
        batch_op.drop_column("beleg_typ")
