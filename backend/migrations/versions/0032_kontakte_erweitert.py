"""kontakte erweitert (lieferanten, ansprechpartner, zahlung, leitweg-id), produkt-artikelnummer

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_TEXTFELDER = ("anrede", "vorname", "nachname", "telefon", "notiz", "steuernummer", "iban", "bic", "leitweg_id")


def upgrade() -> None:
    with op.batch_alter_table("kontakte") as batch_op:
        batch_op.add_column(sa.Column("typ", sa.String(10), nullable=False, server_default="kunde"))
        for feld in _TEXTFELDER:
            batch_op.add_column(sa.Column(feld, sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("iban_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("zahlungsziel_tage", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("skonto_prozent", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("skonto_tage", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archiviert_am", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_kontakte_iban_hash", ["iban_hash"])
    with op.batch_alter_table("produkte") as batch_op:
        batch_op.add_column(sa.Column("artikelnummer", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("produkte") as batch_op:
        batch_op.drop_column("artikelnummer")
    with op.batch_alter_table("kontakte") as batch_op:
        batch_op.drop_index("ix_kontakte_iban_hash")
        for feld in ("archiviert_am", "skonto_tage", "skonto_prozent", "zahlungsziel_tage", "iban_hash", *reversed(_TEXTFELDER), "typ"):
            batch_op.drop_column(feld)
