"""Row-Level-Security für fünf bisher ungeschützte Tabellen

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-14

Ein Abgleich von pg_class/pg_policy gegen die Tabellen mit Mandantenbezug (RLS-Nachweis, Release-Plan 3.4) zeigte
Lücken: Bei diesen Tabellen fehlte die Mandantenisolation in der Datenbank, sie war nur durch Filter im Anwendungscode
gesichert (Defense-in-Depth fehlte):

- auftragsbestaetigungsnummernkreise, lieferscheinnummernkreise, ausgabe_steueranteile (haben ``mandant_id``)
- auftragsbestaetigung_positionen, lieferschein_positionen (Kindtabellen, Mandant über den Elternsatz)

Dieselben Regeln wie bei den übrigen Tabellen (siehe 0003). Nur Postgres; SQLite kennt keine RLS.
"""
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_MIT_MANDANT = ("auftragsbestaetigungsnummernkreise", "lieferscheinnummernkreise", "ausgabe_steueranteile")
# Kindtabelle -> (Fremdschlüsselspalte, Elterntabelle)
_KINDER = {
    "auftragsbestaetigung_positionen": ("auftragsbestaetigung_id", "auftragsbestaetigungen"),
    "lieferschein_positionen": ("lieferschein_id", "lieferscheine"),
}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for tabelle in _MIT_MANDANT:
        op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tabelle}_mandant_isolation ON {tabelle} "
            "USING (mandant_id::text = current_setting('app.current_mandant_id', true))"
        )
    for tabelle, (spalte, eltern) in _KINDER.items():
        op.execute(f"ALTER TABLE {tabelle} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tabelle}_mandant_isolation ON {tabelle} "
            f"USING ({spalte} IN (SELECT id FROM {eltern} "
            "WHERE mandant_id::text = current_setting('app.current_mandant_id', true)))"
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    for tabelle in (*_MIT_MANDANT, *_KINDER):
        op.execute(f"DROP POLICY IF EXISTS {tabelle}_mandant_isolation ON {tabelle}")
        op.execute(f"ALTER TABLE {tabelle} DISABLE ROW LEVEL SECURITY")
