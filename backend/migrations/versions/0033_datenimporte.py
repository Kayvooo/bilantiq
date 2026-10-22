"""stammdaten-import: protokoll und herkunft der importierten datensaetze

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "datenimporte",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ziel", sa.String(20), nullable=False),
        sa.Column("dateiname", sa.Text(), nullable=False),
        sa.Column("datei_hash", sa.String(64), nullable=False),
        sa.Column("anzahl_neu", sa.Integer(), nullable=False),
        sa.Column("anzahl_ergaenzt", sa.Integer(), nullable=False),
        sa.Column("anzahl_uebersprungen", sa.Integer(), nullable=False),
        sa.Column("anzahl_fehler", sa.Integer(), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rueckgaengig_am", sa.DateTime(timezone=True), nullable=True),
    )
    for tabelle in ("kontakte", "produkte"):
        with op.batch_alter_table(tabelle) as batch_op:
            batch_op.add_column(sa.Column("import_id", sa.String(36), nullable=True))
            batch_op.create_index(f"ix_{tabelle}_import_id", ["import_id"])
            batch_op.create_foreign_key(f"fk_{tabelle}_import_id", "datenimporte", ["import_id"], ["id"])
    if _is_postgres():
        op.execute("ALTER TABLE datenimporte ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY datenimporte_mandant_isolation ON datenimporte "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS datenimporte_mandant_isolation ON datenimporte")
    for tabelle in ("produkte", "kontakte"):
        with op.batch_alter_table(tabelle) as batch_op:
            batch_op.drop_constraint(f"fk_{tabelle}_import_id", type_="foreignkey")
            batch_op.drop_index(f"ix_{tabelle}_import_id")
            batch_op.drop_column("import_id")
    op.drop_table("datenimporte")
