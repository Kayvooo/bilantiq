"""Zahlungsdatum und gemischte USt-Saetze fuer Ausgaben.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-07

Die Lohn-Migration 0027 ist integriert; diese Migration haengt bewusst direkt
dahinter, damit Alembic genau einen linearen Head behaelt.
"""
from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ausgaben") as batch_op:
        batch_op.add_column(sa.Column("zahlungsdatum", sa.Date(), nullable=True))
        batch_op.alter_column("ust_satz", existing_type=sa.Numeric(5, 2), nullable=True)

    op.execute("UPDATE ausgaben SET zahlungsdatum = datum WHERE zahlungsdatum IS NULL")

    with op.batch_alter_table("ausgaben") as batch_op:
        batch_op.alter_column("zahlungsdatum", existing_type=sa.Date(), nullable=False)

    op.create_table(
        "ausgabe_steueranteile",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False),
        sa.Column("ausgabe_id", sa.String(36), sa.ForeignKey("ausgaben.id"), nullable=False),
        sa.Column("bruttobetrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
    )
    op.create_index("ix_ausgabe_steueranteile_mandant_id", "ausgabe_steueranteile", ["mandant_id"])
    op.create_index("ix_ausgabe_steueranteile_ausgabe_id", "ausgabe_steueranteile", ["ausgabe_id"])


def downgrade() -> None:
    op.drop_index("ix_ausgabe_steueranteile_ausgabe_id", table_name="ausgabe_steueranteile")
    op.drop_index("ix_ausgabe_steueranteile_mandant_id", table_name="ausgabe_steueranteile")
    op.drop_table("ausgabe_steueranteile")

    op.execute("UPDATE ausgaben SET ust_satz = 0 WHERE ust_satz IS NULL")
    with op.batch_alter_table("ausgaben") as batch_op:
        batch_op.alter_column("ust_satz", existing_type=sa.Numeric(5, 2), nullable=False)
        batch_op.drop_column("zahlungsdatum")
