"""Bezahlfunktion entfernen: Tarif-/Stripe-Spalten, Webhook-Tabelle und Lookup-Funktion

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-22

Bilantiq hat keine Tarife, keine Abrechnung und keinen Online-Zahllink mehr. Diese Migration entfernt,
was die Migrationen 0023 und 0026 angelegt hatten (und 0035 fuer Postgres):

* Tabelle ``webhook_ereignisse``
* Spalten ``tarif``, ``tarif_status``, ``stripe_customer_id``, ``stripe_subscription_id``,
  ``tarif_gueltig_bis`` an ``mandanten``
* Spalten ``zahllink_token_verschluesselt``, ``zahllink_token_hash``, ``stripe_checkout_session_id``,
  ``stripe_checkout_session_versuch``, ``stripe_checkout_session_expires_at``, ``online_bezahlt_am`` an ``invoices``
* Postgres: Funktion ``bq_mandant_aus_stripe_kunde``

Nicht angefasst werden RLS-Policies (sie greifen auf ``id`` bzw. ``mandant_id`` zu, nicht auf die entfernten
Spalten), der Append-only-Trigger und alle Zeilen des Audit-Logs (die Hash-Kette haengt nur an dessen eigenen
Spalten). Historische Audit-Eintraege wie ``rechnung_online_bezahlt`` bleiben unveraendert erhalten.

SQLite kann nur ueber ``batch_alter_table`` (Tabelle neu anlegen) Spalten samt UNIQUE-Constraints entfernen.
Das Entfernen ist verlustbehaftet: Tarifstand, Stripe-IDs und Zahllink-Token sind danach weg. Der Rueckweg
legt die Spalten leer (Tarif ``free``) wieder an, stellt die Daten aber nicht wieder her.
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        op.execute("DROP FUNCTION IF EXISTS bq_mandant_aus_stripe_kunde(text)")

    op.drop_table("webhook_ereignisse")

    # Constraints zuerst ausdruecklich entfernen: Unter SQLite wird die Tabelle neu aufgebaut, und die
    # Constraints duerfen dabei nicht auf entfernte Spalten verweisen.
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_constraint("uq_invoices_zahllink_token_hash", type_="unique")
        batch_op.drop_column("online_bezahlt_am")
        batch_op.drop_column("stripe_checkout_session_expires_at")
        batch_op.drop_column("stripe_checkout_session_versuch")
        batch_op.drop_column("stripe_checkout_session_id")
        batch_op.drop_column("zahllink_token_hash")
        batch_op.drop_column("zahllink_token_verschluesselt")

    with op.batch_alter_table("mandanten") as batch_op:
        batch_op.drop_constraint("uq_mandanten_stripe_subscription_id", type_="unique")
        batch_op.drop_constraint("uq_mandanten_stripe_customer_id", type_="unique")
        batch_op.drop_column("tarif_gueltig_bis")
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
        batch_op.drop_column("tarif_status")
        batch_op.drop_column("tarif")


def downgrade() -> None:
    with op.batch_alter_table("mandanten") as batch_op:
        batch_op.add_column(sa.Column("tarif", sa.String(20), nullable=False, server_default="free"))
        batch_op.add_column(sa.Column("tarif_status", sa.String(30), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("tarif_gueltig_bis", sa.Date(), nullable=True))
        batch_op.create_unique_constraint("uq_mandanten_stripe_customer_id", ["stripe_customer_id"])
        batch_op.create_unique_constraint("uq_mandanten_stripe_subscription_id", ["stripe_subscription_id"])

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("zahllink_token_verschluesselt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("zahllink_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("stripe_checkout_session_versuch", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("stripe_checkout_session_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("online_bezahlt_am", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_invoices_zahllink_token_hash", ["zahllink_token_hash"])

    op.create_table(
        "webhook_ereignisse",
        sa.Column("stripe_event_id", sa.String(255), primary_key=True),
        sa.Column("verarbeitet_am", sa.DateTime(timezone=True), nullable=False),
    )

    if _is_postgres():
        op.execute(
            "CREATE OR REPLACE FUNCTION bq_mandant_aus_stripe_kunde(p_kunde text) RETURNS varchar "
            "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp "
            "AS $$ SELECT id FROM mandanten WHERE stripe_customer_id = p_kunde LIMIT 1 $$"
        )
        op.execute("REVOKE ALL ON FUNCTION bq_mandant_aus_stripe_kunde(text) FROM PUBLIC")
