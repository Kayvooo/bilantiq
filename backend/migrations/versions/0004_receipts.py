"""receipts, ausgaben (Beleg-KI-Erfassung) + Postgres RLS

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
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
        "ausgaben",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("receipt_id", sa.String(36), nullable=False, unique=True),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("anbieter", sa.String(255), nullable=False),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=False),
        sa.Column("kategorie", sa.String(100), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("datei_referenz", sa.String(500), nullable=False),
        sa.Column("datei_hash", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="neu"),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=True),
        sa.Column("betrag_confidence", sa.Float, nullable=True),
        sa.Column("datum", sa.Date, nullable=True),
        sa.Column("datum_confidence", sa.Float, nullable=True),
        sa.Column("anbieter", sa.String(255), nullable=True),
        sa.Column("anbieter_confidence", sa.Float, nullable=True),
        sa.Column("ust_satz", sa.Numeric(5, 2), nullable=True),
        sa.Column("ust_satz_confidence", sa.Float, nullable=True),
        sa.Column("kategorie_vorschlag", sa.String(100), nullable=True),
        sa.Column("kategorie_vorschlag_confidence", sa.Float, nullable=True),
        sa.Column("gebucht_als", sa.String(36), sa.ForeignKey("ausgaben.id"), nullable=True),
        sa.Column("hochgeladen_am", sa.DateTime(timezone=True), nullable=False),
    )

    if not _is_postgres():
        return

    for table in ("ausgaben", "receipts"):
        _mandant_rls(table)


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS receipts_mandant_isolation ON receipts")
        op.execute("DROP POLICY IF EXISTS ausgaben_mandant_isolation ON ausgaben")

    op.drop_table("receipts")
    op.drop_table("ausgaben")
