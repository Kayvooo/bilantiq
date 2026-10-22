"""angebotsnummernkreise, quotes, quote_positionen + Postgres RLS

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _mandant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_mandant_isolation ON {table}
        USING (mandant_id::text = current_setting('app.current_mandant_id', true))
        """
    )


def upgrade() -> None:
    op.create_table(
        "angebotsnummernkreise",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("jahr", sa.Integer, nullable=False),
        sa.Column("naechste_nummer", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("mandant_id", "jahr", name="uq_angebotsnummernkreis_mandant_jahr"),
    )

    op.create_table(
        "quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False),
        sa.Column("nummer", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="entwurf"),
        sa.Column("gueltig_bis", sa.Date, nullable=False),
        sa.Column("waehrung", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("netto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ust_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("brutto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("umgewandelt_in_invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("versendet_am", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "quote_positionen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("quote_id", sa.String(36), sa.ForeignKey("quotes.id"), nullable=False, index=True),
        sa.Column("reihenfolge", sa.Integer, nullable=False, server_default="0"),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("menge", sa.Numeric(12, 3), nullable=False),
        sa.Column("einzelpreis", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
    )

    if not _is_postgres():
        return

    for table in ("angebotsnummernkreise", "quotes"):
        _mandant_rls(table)

    op.execute("ALTER TABLE quote_positionen ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY quote_positionen_mandant_isolation ON quote_positionen
        USING (
            quote_id IN (
                SELECT id FROM quotes
                WHERE mandant_id::text = current_setting('app.current_mandant_id', true)
            )
        )
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS quote_positionen_mandant_isolation ON quote_positionen")
        op.execute("DROP POLICY IF EXISTS quotes_mandant_isolation ON quotes")
        op.execute("DROP POLICY IF EXISTS angebotsnummernkreise_mandant_isolation ON angebotsnummernkreise")

    op.drop_table("quote_positionen")
    op.drop_table("quotes")
    op.drop_table("angebotsnummernkreise")
