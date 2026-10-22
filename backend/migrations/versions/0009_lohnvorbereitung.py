"""mitarbeitende und lohn_monatsentwuerfe

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "mitarbeitende",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("personalnummer", sa.String(30), nullable=False),
        sa.Column("vorname_encrypted", sa.String(500), nullable=False),
        sa.Column("nachname_encrypted", sa.String(500), nullable=False),
        sa.Column("eintrittsdatum", sa.Date(), nullable=False),
        sa.Column("austrittsdatum", sa.Date(), nullable=True),
        sa.Column("monatsbrutto", sa.Numeric(12, 2), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mandant_id", "personalnummer", name="uq_mitarbeitende_personalnummer"),
    )
    op.create_table(
        "lohn_monatsentwuerfe",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("mitarbeiter_id", sa.String(36), sa.ForeignKey("mitarbeitende.id"), nullable=False, index=True),
        sa.Column("jahr", sa.Integer(), nullable=False),
        sa.Column("monat", sa.Integer(), nullable=False),
        sa.Column("grundbrutto", sa.Numeric(12, 2), nullable=False),
        sa.Column("steuerpflichtige_zuschlaege", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("steuerfreie_erstattungen", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("sonstige_abzuege", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("gesamtbrutto", sa.Numeric(12, 2), nullable=False),
        sa.Column("zwischenbetrag_vor_abgaben", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="vorbereitung"),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mitarbeiter_id", "jahr", "monat", name="uq_lohn_mitarbeiter_monat"),
    )
    if _is_postgres():
        for table in ("mitarbeitende", "lohn_monatsentwuerfe"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY {table}_mandant_isolation ON {table} USING (mandant_id::text = current_setting('app.current_mandant_id', true))")


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS lohn_monatsentwuerfe_mandant_isolation ON lohn_monatsentwuerfe")
        op.execute("DROP POLICY IF EXISTS mitarbeitende_mandant_isolation ON mitarbeitende")
    op.drop_table("lohn_monatsentwuerfe")
    op.drop_table("mitarbeitende")
