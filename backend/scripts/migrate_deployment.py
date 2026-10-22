"""One-shot deployment task. Admin credentials are never mounted in the API service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.runtime_security import pruefe_datenbankrolle


def pruefe_verbindungen(admin: URL, runtime: URL) -> None:
    if admin.get_backend_name() != "postgresql" or runtime.get_backend_name() != "postgresql":
        raise ValueError("Deployment-Migrationen brauchen PostgreSQL.")
    if not runtime.username or not runtime.password or runtime.username == admin.username:
        raise ValueError("Eine eigene Laufzeitrolle mit eigenem Passwort ist erforderlich; docs/security-runtime.md.")
    if (admin.host, admin.port or 5432, admin.database) != (runtime.host, runtime.port or 5432, runtime.database):
        raise ValueError("Admin- und Laufzeitverbindung muessen auf dieselbe Datenbank zeigen.")


def richte_laufzeitrolle_ein(admin_engine, runtime: URL) -> None:
    with admin_engine.begin() as connection:
        rolle = runtime.username
        vorhanden = connection.execute(text("SELECT oid FROM pg_roles WHERE rolname = :rolle"), {"rolle": rolle}).scalar()
        if vorhanden is not None:
            unsicher = connection.execute(text("""
                SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member = :oid)
                    OR EXISTS (SELECT 1 FROM pg_database WHERE datdba = :oid)
                    OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = :oid)
                    OR EXISTS (SELECT 1 FROM pg_class WHERE relowner = :oid)
                    OR :rolle = current_user
            """), {"oid": vorhanden, "rolle": rolle}).scalar_one()
            if unsicher:
                raise ValueError("Vorhandene Laufzeitrolle besitzt Objekte oder Mitgliedschaften; eigene neue Rolle verwenden.")
        # PostgreSQL quotes identifiers/passwords itself; no SQL or shell interpolation of credentials.
        verb = "ALTER" if vorhanden is not None else "CREATE"
        befehl = connection.execute(text(
            "SELECT format('" + verb + " ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD %L', CAST(:rolle AS text), CAST(:passwort AS text))"
        ), {"rolle": rolle, "passwort": runtime.password}).scalar_one()
        connection.exec_driver_sql(befehl, execution_options={"no_parameters": True})
        for vorlage in (
            "REVOKE ALL ON SCHEMA public FROM %I",
            "GRANT USAGE ON SCHEMA public TO %I",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I",
            "REVOKE UPDATE, DELETE, TRUNCATE, TRIGGER ON audit_log_eintraege FROM %I",
            "REVOKE ALL ON alembic_version FROM %I",
            "GRANT EXECUTE ON FUNCTION bq_mandant_aus_einladung(text), bq_mandant_des_nutzers(text) TO %I",
        ):
            befehl = connection.execute(text("SELECT format(CAST(:vorlage AS text), CAST(:rolle AS text))"), {"vorlage": vorlage, "rolle": rolle}).scalar_one()
            connection.exec_driver_sql(befehl, execution_options={"no_parameters": True})
        connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")


def main() -> int:
    admin_engine = runtime_engine = None
    try:
        admin_roh = Path("/run/secrets/database_url").read_text().strip()
        runtime_roh = Path("/run/secrets/runtime_database_url").read_text().strip()
        admin, runtime = make_url(admin_roh), make_url(runtime_roh)
        pruefe_verbindungen(admin, runtime)
        # Alembic's settings read this administrative connection only inside this one-shot process.
        os.environ["DATABASE_URL"] = admin_roh
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
        admin_engine = create_engine(admin, hide_parameters=True)
        richte_laufzeitrolle_ein(admin_engine, runtime)
        runtime_engine = create_engine(runtime, hide_parameters=True)
        pruefe_datenbankrolle(runtime_engine, "production")
    except Exception as exc:
        # Driver/DDL exceptions can contain passwords; only deliberate validation messages are safe.
        meldung = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"Deployment-Migration fehlgeschlagen: {meldung}", file=sys.stderr)
        return 1
    finally:
        if admin_engine is not None:
            admin_engine.dispose()
        if runtime_engine is not None:
            runtime_engine.dispose()
    print("Migrationen und Laufzeitrolle erfolgreich eingerichtet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
