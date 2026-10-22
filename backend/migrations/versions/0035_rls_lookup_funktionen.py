"""Privilegierte Lookup-Funktionen für Vorgänge ohne Mandantenkontext

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-11

Registrierung mit Einladungscode, Anmeldung und der Stripe-Webhook müssen einen Mandanten
finden, bevor sie dessen RLS-geschützte Zeilen lesen dürfen. Ohne BYPASSRLS der App-Rolle
geht das nur über diese engen SECURITY-DEFINER-Funktionen: Sie liefern ausschließlich eine
Mandanten-ID zu einem nicht erratbaren Schlüssel (Einladungscode, Nutzer-ID, Stripe-Kunde).
"""
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_FUNKTIONEN = {
    "bq_mandant_aus_einladung": ("p_code text", "SELECT mandant_id FROM einladungen WHERE code = p_code LIMIT 1"),
    "bq_mandant_des_nutzers": (
        "p_user_id text",
        "SELECT mandant_id FROM mitgliedschaften WHERE user_id = p_user_id ORDER BY id LIMIT 1",
    ),
    "bq_mandant_aus_stripe_kunde": ("p_kunde text", "SELECT id FROM mandanten WHERE stripe_customer_id = p_kunde LIMIT 1"),
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for name, (parameter, abfrage) in _FUNKTIONEN.items():
        op.execute(
            f"CREATE OR REPLACE FUNCTION {name}({parameter}) RETURNS varchar "
            f"LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp "
            f"AS $$ {abfrage} $$"
        )
        op.execute(f"REVOKE ALL ON FUNCTION {name}(text) FROM PUBLIC")
        # Die App-Rolle heißt je Umgebung anders; EXECUTE erhält sie über runtime_rolle.sql.


def downgrade() -> None:
    if not _is_postgres():
        return
    for name in _FUNKTIONEN:
        op.execute(f"DROP FUNCTION IF EXISTS {name}(text)")
