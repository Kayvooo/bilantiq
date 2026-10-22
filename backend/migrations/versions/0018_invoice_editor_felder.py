"""invoices Editor-Zusatzfelder, invoice_positionen.kategorie, positionskategorien

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Batch mode keeps this migration executable on SQLite, which cannot add
    # the foreign-key constraint for interne_kontaktperson_user_id via ALTER.
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("betreff", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("kopftext", sa.String(2000), nullable=True))
        batch_op.add_column(sa.Column("fusstext", sa.String(2000), nullable=True))
        batch_op.add_column(sa.Column("referenznummer", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("kostenstelle", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("zahlungsmethode", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("skonto_tage", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("skonto_prozent", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(
            sa.Column(
                "interne_kontaktperson_user_id",
                sa.String(36),
                sa.ForeignKey(
                    "users.id",
                    name="fk_invoices_interne_kontaktperson_user_id_users",
                ),
                nullable=True,
            )
        )
    op.add_column("invoice_positionen", sa.Column("kategorie", sa.String(100), nullable=True))

    op.create_table(
        "positionskategorien",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mandant_id", sa.String(36), sa.ForeignKey("mandanten.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    if _is_postgres():
        op.execute("ALTER TABLE positionskategorien ENABLE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY positionskategorien_mandant_isolation ON positionskategorien "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS positionskategorien_mandant_isolation ON positionskategorien")
    op.drop_table("positionskategorien")
    op.drop_column("invoice_positionen", "kategorie")
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("interne_kontaktperson_user_id")
        batch_op.drop_column("skonto_prozent")
        batch_op.drop_column("skonto_tage")
        batch_op.drop_column("zahlungsmethode")
        batch_op.drop_column("kostenstelle")
        batch_op.drop_column("referenznummer")
        batch_op.drop_column("fusstext")
        batch_op.drop_column("kopftext")
        batch_op.drop_column("betreff")
