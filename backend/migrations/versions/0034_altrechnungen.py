"""altrechnungen: rechnungen aus dem altsystem, zahlungen darauf, quelldatei des imports

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_TABELLEN = ("altrechnungen", "altrechnung_zahlungen")


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("datenimporte") as batch_op:
        batch_op.add_column(sa.Column("datei_referenz", sa.String(500), nullable=True))

    op.create_table(
        "altrechnungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("kontakt_id", sa.String(36), sa.ForeignKey("kontakte.id"), nullable=False, index=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("datenimporte.id"), nullable=False, index=True),
        sa.Column("nummer", sa.Text(), nullable=False),
        sa.Column("nummer_hash", sa.String(64), nullable=False),
        sa.Column("rechnungsdatum", sa.Date(), nullable=False, index=True),
        sa.Column("faelligkeit", sa.Date(), nullable=True),
        sa.Column("brutto", sa.Text(), nullable=False),
        sa.Column("offen_beim_import", sa.Text(), nullable=False),
        sa.Column("steueranteile", sa.Text(), nullable=False),
        sa.Column("war_offen", sa.Boolean(), nullable=False, index=True),
        sa.Column("bezahlt_im_altsystem_am", sa.Date(), nullable=True),
        sa.Column("datei_referenz", sa.String(500), nullable=True),
        sa.Column("datei_hash", sa.String(64), nullable=True),
        sa.Column("datei_hinzugefuegt_am", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mandant_id", "nummer_hash", name="uq_altrechnung_nummer"),
    )
    op.create_table(
        "altrechnung_zahlungen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("altrechnung_id", sa.String(36), sa.ForeignKey("altrechnungen.id"), nullable=False, index=True),
        sa.Column("datum", sa.Date(), nullable=False, index=True),
        sa.Column("betrag", sa.Text(), nullable=False),
        sa.Column("quelle", sa.String(12), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )
    if _is_postgres():
        for tabelle in _TABELLEN:
            op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {tabelle}_mandant_isolation ON {tabelle} "
                "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
            )


def downgrade() -> None:
    if _is_postgres():
        for tabelle in reversed(_TABELLEN):
            op.execute(f"DROP POLICY IF EXISTS {tabelle}_mandant_isolation ON {tabelle}")
    op.drop_table("altrechnung_zahlungen")
    op.drop_table("altrechnungen")
    with op.batch_alter_table("datenimporte") as batch_op:
        batch_op.drop_column("datei_referenz")
