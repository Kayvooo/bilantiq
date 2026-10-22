"""Rechnungs-Designer: Briefpapiere, Mandant-Designfelder/-Toggles, Kundennummer, Artikelnummer

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "briefpapiere",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("datei_referenz", sa.String(500), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE briefpapiere ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY briefpapiere_mandant_isolation ON briefpapiere "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )

    op.add_column("mandanten", sa.Column("design_variante", sa.String(20), nullable=True))
    op.add_column("mandanten", sa.Column("logo_groesse", sa.String(1), nullable=True))
    # Kein FK-Constraint -- siehe app/auth/models.py::Mandant.briefpapier_id
    # (Abhaengigkeitszyklus mit briefpapiere.mandant_id, gleiches Muster wie
    # ausgaben.receipt_id).
    op.add_column("mandanten", sa.Column("briefpapier_id", sa.String(36), nullable=True))
    op.add_column("mandanten", sa.Column("sprache", sa.String(2), nullable=True))
    op.add_column("mandanten", sa.Column("iban", sa.String(34), nullable=True))
    op.add_column("mandanten", sa.Column("bic", sa.String(11), nullable=True))
    op.add_column("mandanten", sa.Column("zeige_absenderzeile", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("mandanten", sa.Column("zeige_kundennummer", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mandanten", sa.Column("zeige_kontaktperson", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mandanten", sa.Column("zeige_artikelnummer", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mandanten", sa.Column("zeige_positionsbeschreibung", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("mandanten", sa.Column("zeige_ust_pro_position", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("mandanten", sa.Column("zeige_girocode", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mandanten", sa.Column("zeige_fusszeile", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("mandanten", sa.Column("zeige_seitenzahlen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mandanten", sa.Column("zeige_falz_lochmarken", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("kontakte", sa.Column("kundennummer", sa.String(50), nullable=True))
    op.add_column("invoice_positionen", sa.Column("artikelnummer", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_positionen", "artikelnummer")
    op.drop_column("kontakte", "kundennummer")

    for spalte in (
        "zeige_falz_lochmarken", "zeige_seitenzahlen", "zeige_fusszeile", "zeige_girocode",
        "zeige_ust_pro_position", "zeige_positionsbeschreibung", "zeige_artikelnummer",
        "zeige_kontaktperson", "zeige_kundennummer", "zeige_absenderzeile",
        "bic", "iban", "sprache", "briefpapier_id", "logo_groesse", "design_variante",
    ):
        op.drop_column("mandanten", spalte)

    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS briefpapiere_mandant_isolation ON briefpapiere")
    op.drop_table("briefpapiere")
