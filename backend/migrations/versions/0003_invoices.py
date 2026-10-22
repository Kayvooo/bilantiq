"""kontakte, rechnungsnummernkreise, invoices, invoice_positionen + Postgres RLS

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
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
        "kontakte",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("strasse", sa.String(255), nullable=True),
        sa.Column("plz", sa.String(10), nullable=True),
        sa.Column("ort", sa.String(255), nullable=True),
        sa.Column("land", sa.String(2), nullable=False, server_default="DE"),
        sa.Column("ust_id", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("ist_geschaeftskunde", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "rechnungsnummernkreise",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("jahr", sa.Integer, nullable=False),
        sa.Column("naechste_nummer", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("mandant_id", "jahr", name="uq_nummernkreis_mandant_jahr"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False),
        sa.Column("nummer", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="entwurf"),
        sa.Column("leistungsdatum", sa.Date, nullable=False),
        sa.Column("faelligkeitsdatum", sa.Date, nullable=False),
        sa.Column("waehrung", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("netto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ust_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("brutto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("e_invoice_format", sa.String(20), nullable=True),
        sa.Column("korrigiert_invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalisiert_am", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "invoice_positionen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False, index=True),
        sa.Column("reihenfolge", sa.Integer, nullable=False, server_default="0"),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("menge", sa.Numeric(12, 3), nullable=False),
        sa.Column("einzelpreis", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
    )

    if not _is_postgres():
        return

    for table in ("kontakte", "rechnungsnummernkreise", "invoices"):
        _mandant_rls(table)

    # invoice_positionen has no mandant_id of its own; scope it via its parent invoice.
    op.execute("ALTER TABLE invoice_positionen ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY invoice_positionen_mandant_isolation ON invoice_positionen
        USING (
            invoice_id IN (
                SELECT id FROM invoices
                WHERE mandant_id::text = current_setting('app.current_mandant_id', true)
            )
        )
        """
    )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS invoice_positionen_mandant_isolation ON invoice_positionen")
        for table in ("invoices", "rechnungsnummernkreise", "kontakte"):
            op.execute(f"DROP POLICY IF EXISTS {table}_mandant_isolation ON {table}")

    op.drop_table("invoice_positionen")
    op.drop_table("invoices")
    op.drop_table("rechnungsnummernkreise")
    op.drop_table("kontakte")
