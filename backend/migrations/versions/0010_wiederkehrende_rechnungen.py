"""wiederkehrende_rechnungen und wiederkehrende_rechnung_positionen

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "wiederkehrende_rechnungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False),
        sa.Column("bezeichnung", sa.String(255), nullable=False),
        sa.Column("intervall", sa.String(20), nullable=False),
        sa.Column("naechstes_datum", sa.Date(), nullable=False),
        sa.Column("enddatum", sa.Date(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "wiederkehrende_rechnung_positionen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vorlage_id", sa.String(36), sa.ForeignKey("wiederkehrende_rechnungen.id"), nullable=False, index=True),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("menge", sa.Numeric(12, 2), nullable=False),
        sa.Column("einzelpreis", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
    )
    if _is_postgres():
        op.execute("ALTER TABLE wiederkehrende_rechnungen ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY wiederkehrende_rechnungen_mandant_isolation ON wiederkehrende_rechnungen "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )
        # wiederkehrende_rechnung_positionen hat kein eigenes mandant_id, wie invoice_positionen
        # (0003_invoices.py) — Absicherung ueber die Eltern-Vorlage.
        op.execute("ALTER TABLE wiederkehrende_rechnung_positionen ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY wiederkehrende_rechnung_positionen_mandant_isolation ON wiederkehrende_rechnung_positionen
            USING (
                vorlage_id IN (
                    SELECT id FROM wiederkehrende_rechnungen
                    WHERE mandant_id::text = current_setting('app.current_mandant_id', true)
                )
            )
            """
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS wiederkehrende_rechnung_positionen_mandant_isolation ON wiederkehrende_rechnung_positionen")
        op.execute("DROP POLICY IF EXISTS wiederkehrende_rechnungen_mandant_isolation ON wiederkehrende_rechnungen")
    op.drop_table("wiederkehrende_rechnung_positionen")
    op.drop_table("wiederkehrende_rechnungen")
