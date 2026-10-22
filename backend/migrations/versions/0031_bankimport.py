"""bankimport (Kontoauszug-Import mit Zahlungsabgleich)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

TABELLEN = ("bankkonten", "bankimporte", "bankumsaetze")


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "bankkonten",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bezeichnung", sa.Text(), nullable=False),
        sa.Column("iban", sa.Text(), nullable=True),
        sa.Column("iban_hash", sa.String(64), nullable=True, index=True),
        sa.Column("csv_profil", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "bankimporte",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bankkonto_id", sa.String(36), sa.ForeignKey("bankkonten.id"), nullable=False, index=True),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("dateiname", sa.Text(), nullable=False),
        sa.Column("datei_hash", sa.String(64), nullable=False),
        sa.Column("datei_referenz", sa.String(500), nullable=False),
        sa.Column("anzahl_neu", sa.Integer(), nullable=False),
        sa.Column("anzahl_doppelt", sa.Integer(), nullable=False),
        sa.Column("zeitraum_von", sa.Date(), nullable=True),
        sa.Column("zeitraum_bis", sa.Date(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "bankumsaetze",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("bankkonto_id", sa.String(36), sa.ForeignKey("bankkonten.id"), nullable=False, index=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("bankimporte.id"), nullable=False, index=True),
        sa.Column("buchungsdatum", sa.Date(), nullable=False, index=True),
        sa.Column("wertstellung", sa.Date(), nullable=True),
        sa.Column("betrag", sa.Text(), nullable=False),
        sa.Column("waehrung", sa.String(3), nullable=False),
        sa.Column("gegenpartei_name", sa.Text(), nullable=True),
        sa.Column("gegenpartei_iban", sa.Text(), nullable=True),
        sa.Column("verwendungszweck", sa.Text(), nullable=False),
        sa.Column("end_to_end_id", sa.Text(), nullable=True),
        sa.Column("dedupe_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, index=True),
        sa.Column("zuordnung_typ", sa.String(12), nullable=True),
        sa.Column("zuordnung_id", sa.String(36), nullable=True, index=True),
        sa.Column("zugeordnet_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ignoriert_grund", sa.Text(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bankkonto_id", "dedupe_hash", name="uq_bankumsatz_dedupe"),
    )
    if _is_postgres():
        for tabelle in TABELLEN:
            op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {tabelle}_mandant_isolation ON {tabelle} "
                "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
            )


def downgrade() -> None:
    if _is_postgres():
        for tabelle in reversed(TABELLEN):
            op.execute(f"DROP POLICY IF EXISTS {tabelle}_mandant_isolation ON {tabelle}")
    op.drop_table("bankumsaetze")
    op.drop_table("bankimporte")
    op.drop_table("bankkonten")
