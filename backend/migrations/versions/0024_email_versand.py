"""E-Mail-Versand: versendet_am auf invoices/mahnungen, email_versendet_am auf quotes.

quotes.versendet_am existiert bereits (seit 0005) und bedeutet dort "Entwurf
abgeschlossen, Angebotsnummer vergeben" (siehe app/quotes/routes.py::send_quote) --
lange bevor es ueberhaupt E-Mail-Versand gab. Um diese bestehende, getestete
Bedeutung nicht zu ueberschreiben, bekommt der tatsaechliche E-Mail-Versand bei
Angeboten ein eigenes Feld email_versendet_am statt versendet_am wiederzuverwenden.
Bei invoices/mahnungen gibt es keine solche Kollision, dort heisst das neue Feld
wie in der Aufgabenstellung versendet_am.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("versendet_am", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mahnungen", sa.Column("versendet_am", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quotes", sa.Column("email_versendet_am", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "email_versendet_am")
    op.drop_column("mahnungen", "versendet_am")
    op.drop_column("invoices", "versendet_am")
