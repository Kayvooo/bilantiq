"""auftragsbestaetigungen und lieferscheine

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _mandant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_mandant_isolation ON {table} "
        "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
    )


def upgrade() -> None:
    op.create_table(
        "auftragsbestaetigungsnummernkreise",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("jahr", sa.Integer(), nullable=False),
        sa.Column("naechste_nummer", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "lieferscheinnummernkreise",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("jahr", sa.Integer(), nullable=False),
        sa.Column("naechste_nummer", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "auftragsbestaetigungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("quote_id", sa.String(36), sa.ForeignKey("quotes.id"), nullable=False),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False),
        sa.Column("nummer", sa.String(40), nullable=False),
        sa.Column("waehrung", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("netto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ust_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("brutto_gesamt", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auftragsbestaetigung_positionen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("auftragsbestaetigung_id", sa.String(36), sa.ForeignKey("auftragsbestaetigungen.id"), nullable=False, index=True),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("menge", sa.Numeric(12, 3), nullable=False),
        sa.Column("einzelpreis", sa.Numeric(12, 2), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
    )
    op.create_table(
        "lieferscheine",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("auftragsbestaetigung_id", sa.String(36), sa.ForeignKey("auftragsbestaetigungen.id"), nullable=False),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False),
        sa.Column("nummer", sa.String(40), nullable=False),
        sa.Column("lieferdatum", sa.Date(), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "lieferschein_positionen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lieferschein_id", sa.String(36), sa.ForeignKey("lieferscheine.id"), nullable=False, index=True),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("beschreibung", sa.String(500), nullable=False),
        sa.Column("menge", sa.Numeric(12, 3), nullable=False),
    )

    if _is_postgres():
        for table in ("auftragsbestaetigungen", "lieferscheine"):
            _mandant_rls(table)


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS lieferscheine_mandant_isolation ON lieferscheine")
        op.execute("DROP POLICY IF EXISTS auftragsbestaetigungen_mandant_isolation ON auftragsbestaetigungen")
    op.drop_table("lieferschein_positionen")
    op.drop_table("lieferscheine")
    op.drop_table("auftragsbestaetigung_positionen")
    op.drop_table("auftragsbestaetigungen")
    op.drop_table("lieferscheinnummernkreise")
    op.drop_table("auftragsbestaetigungsnummernkreise")
