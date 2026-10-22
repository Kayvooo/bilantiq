"""Regression tests for deployment privilege boundaries (real PostgreSQL when configured)."""
import os
import secrets
import stat
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings
from app.core.runtime_security import DatenbankSicherheitsFehler, pruefe_datenbankrolle
from app.db import engine
from app.main import app
from scripts.migrate_deployment import pruefe_verbindungen, richte_laufzeitrolle_ein


def test_production_refuses_sqlite_and_development_keeps_working():
    db = create_engine("sqlite://")
    pruefe_datenbankrolle(db, "development")
    with pytest.raises(DatenbankSicherheitsFehler, match="PostgreSQL"):
        pruefe_datenbankrolle(db, "production")
    db.dispose()


def test_api_lifespan_enforces_the_database_guard(monkeypatch):
    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite negative case")
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(DatenbankSicherheitsFehler, match="PostgreSQL"):
        with TestClient(app):
            pass


def test_admin_and_runtime_must_be_distinct_on_the_same_postgres():
    password = secrets.token_urlsafe(24)
    admin = make_url(f"postgresql+psycopg://admin:{password}@postgres/bq")
    runtime = admin.set(username="runtime")
    pruefe_verbindungen(admin, runtime)
    for invalid in (admin, runtime.set(password=""), runtime.set(database="other"), runtime.set(host="other"), make_url("sqlite://")):
        with pytest.raises(ValueError):
            pruefe_verbindungen(admin, invalid)


def test_secret_setup_preserves_keys_and_refuses_legacy_admin_url(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    env = {**os.environ, "BILANTIQ_SECRETS_DIR": str(tmp_path), "BILANTIQ_APP_UID": str(os.geteuid()),
           "POSTGRES_USER": "bilantiq", "POSTGRES_DB": "bilantiq", "POSTGRES_RUNTIME_USER": "bilantiq_runtime"}
    # init-secrets.sh needs only stdlib; use the interpreter belonging to this test environment.
    import sys
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    def run():
        return subprocess.run(["bash", str(repo / "scripts/init-secrets.sh")], env=env, capture_output=True, text=True)
    assert run().returncode == 0
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert make_url(before["database_url"].decode()).username == "bilantiq_runtime"
    assert make_url(before["migration_database_url"].decode()).username == "bilantiq"
    assert run().returncode == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in tmp_path.iterdir())
    (tmp_path / "database_url").write_bytes(before["migration_database_url"])
    result = run()
    assert result.returncode != 0
    assert "Upgrade" in result.stderr
    assert (tmp_path / "database_url").read_bytes() == before["migration_database_url"]
    assert (tmp_path / "data_encryption_keys").read_bytes() == before["data_encryption_keys"]
    assert make_url(before["database_url"].decode()).password not in result.stdout + result.stderr


@pytest.fixture
def postgres_runtime():
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip("needs a PostgreSQL administrator and migrated schema")
    admin = create_engine(admin_url, hide_parameters=True)
    runtime_url = make_url(admin_url).set(username="bq_test_" + secrets.token_hex(8), password=secrets.token_urlsafe(32))
    role = admin.dialect.identifier_preparer.quote_identifier(runtime_url.username)
    runtime = create_engine(runtime_url, hide_parameters=True)
    try:
        richte_laufzeitrolle_ein(admin, runtime_url)
        yield admin, runtime, runtime_url, role
    finally:
        runtime.dispose()
        with admin.begin() as c:
            exists = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": runtime_url.username}).scalar()
            if exists:
                c.exec_driver_sql(f"DROP OWNED BY {role}")
                c.exec_driver_sql(f"DROP ROLE {role}")
        admin.dispose()


def test_real_postgres_runtime_works_and_admin_is_rejected(postgres_runtime):
    admin, runtime, url, _ = postgres_runtime
    pruefe_datenbankrolle(runtime, "production")
    with pytest.raises(DatenbankSicherheitsFehler, match="superuser|besitz"):
        pruefe_datenbankrolle(admin, "production")
    # Re-running deployment preserves the boundary and the actual password-authenticated connection.
    richte_laufzeitrolle_ein(admin, url)
    runtime.dispose()
    pruefe_datenbankrolle(runtime, "production")


@pytest.mark.parametrize("privilege", ["BYPASSRLS", "CREATEDB", "CREATEROLE", "REPLICATION"])
def test_real_postgres_rejects_privileged_runtime(postgres_runtime, privilege):
    admin, runtime, _, role = postgres_runtime
    with admin.begin() as c:
        c.exec_driver_sql(f"ALTER ROLE {role} {privilege}")
    with pytest.raises(DatenbankSicherheitsFehler):
        pruefe_datenbankrolle(runtime, "production")


def test_real_postgres_rejects_memberships_and_migrator_does_not_ignore_them(postgres_runtime):
    admin, runtime, url, role = postgres_runtime
    with admin.begin() as c:
        c.exec_driver_sql(f"GRANT pg_monitor TO {role}")
    with pytest.raises(DatenbankSicherheitsFehler, match="rollenmitgliedschaft"):
        pruefe_datenbankrolle(runtime, "production")
    with pytest.raises(ValueError, match="Mitgliedschaften"):
        richte_laufzeitrolle_ein(admin, url)


def test_real_postgres_rejects_audit_mutation_grants(postgres_runtime):
    admin, runtime, _, role = postgres_runtime
    with admin.begin() as c:
        c.exec_driver_sql(f"GRANT UPDATE, DELETE, TRUNCATE, TRIGGER ON audit_log_eintraege TO {role}")
    with pytest.raises(DatenbankSicherheitsFehler, match="audit_"):
        pruefe_datenbankrolle(runtime, "production")
