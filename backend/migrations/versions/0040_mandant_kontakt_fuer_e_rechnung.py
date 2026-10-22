"""Telefon und Kontakt-E-Mail des Mandanten fuer die XRechnung

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-22

Die XRechnung verlangt eine Ansprechstelle des Verkaeufers mit Telefonnummer und E-Mail (BG-6, Regeln BR-DE-2, BR-DE-5,
BR-DE-7) sowie eine elektronische Adresse (BT-34). Beides gab es am Mandanten bisher nicht. Beide Spalten sind optional
und wie die uebrigen Firmenfelder application-level verschluesselt (physisch TEXT, siehe 0036).
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mandanten") as batch:
        batch.add_column(sa.Column("telefon", sa.Text(), nullable=True))
        batch.add_column(sa.Column("kontakt_email", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mandanten") as batch:
        batch.drop_column("kontakt_email")
        batch.drop_column("telefon")
