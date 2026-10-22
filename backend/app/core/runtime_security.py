"""Fail closed when a deployed API can bypass its database security boundaries."""
from __future__ import annotations

import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine


class DatenbankSicherheitsFehler(RuntimeError):
    pass


def pruefe_datenbankrolle(engine: Engine, umgebung: str) -> None:
    if umgebung == "development":
        return
    if engine.dialect.name != "postgresql":
        raise DatenbankSicherheitsFehler("Staging/Produktion braucht PostgreSQL mit eingeschraenkter Laufzeitrolle.")
    with engine.connect() as connection:
        rechte = connection.execute(text("""
            SELECT r.rolsuper AS superuser, r.rolbypassrls AS bypassrls,
                   r.rolcreaterole AS rollenverwaltung, r.rolcreatedb AS datenbankanlage,
                   r.rolreplication AS replikation,
                   EXISTS (SELECT 1 FROM pg_auth_members WHERE member = r.oid) AS rollenmitgliedschaft,
                   EXISTS (SELECT 1 FROM pg_database WHERE datdba = r.oid) AS datenbankbesitz,
                   EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = r.oid) AS schemabesitz,
                   EXISTS (SELECT 1 FROM pg_class WHERE relowner = r.oid) AS objektbesitz,
                   has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create,
                   has_database_privilege(current_user, current_database(), 'CREATE') AS datenbank_create,
                   to_regclass('public.audit_log_eintraege') IS NOT NULL AS audit_vorhanden,
                   has_table_privilege(current_user, to_regclass('public.audit_log_eintraege'), 'UPDATE') AS audit_update,
                   has_table_privilege(current_user, to_regclass('public.audit_log_eintraege'), 'DELETE') AS audit_delete,
                   has_table_privilege(current_user, to_regclass('public.audit_log_eintraege'), 'TRUNCATE') AS audit_truncate,
                   has_table_privilege(current_user, to_regclass('public.audit_log_eintraege'), 'TRIGGER') AS audit_trigger
            FROM pg_roles r WHERE r.rolname = current_user
        """)).mappings().one()
    fehler = [name for name, erlaubt in rechte.items() if name != "audit_vorhanden" and erlaubt]
    if not rechte["audit_vorhanden"]:
        fehler.append("audit_schema_fehlt")
    if fehler:
        # Only control names, never connection strings, SQL parameters or credentials.
        raise DatenbankSicherheitsFehler(
            "Unsichere API-Datenbankrolle: " + ", ".join(fehler)
            + ". Migrationen separat ausfuehren; siehe docs/security-runtime.md."
        )


def main() -> int:
    from app.config import settings
    from app.db import engine

    try:
        pruefe_datenbankrolle(engine, settings.app_env)
    except Exception as exc:
        meldung = str(exc) if isinstance(exc, DatenbankSicherheitsFehler) else type(exc).__name__
        print(f"Datenbank-Startpruefung fehlgeschlagen: {meldung}", file=sys.stderr)
        return 1
    print("Datenbank-Startpruefung erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
