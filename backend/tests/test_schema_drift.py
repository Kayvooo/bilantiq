"""Drift-Check: Die Migrationen und die SQLAlchemy-Models muessen dasselbe Schema beschreiben.

Hintergrund: Lokal und in den Tests entsteht das Schema per ``create_all()`` aus den Models, Produktion und Staging
bekommen es ausschliesslich aus den Alembic-Migrationen. Wird eine Spalte, ein Typ, ein Index oder eine Constraint nur in
einer der beiden Quellen angepasst, laufen Tests gruen und Produktion bricht (oder umgekehrt). Dieser Test migriert eine
frische temporaere Postgres-Datenbank bis ``head`` und laesst Alembic den Unterschied zu den Models berechnen
(``compare_metadata``). Er laeuft nur im Postgres-Modus (``TEST_DATABASE_ADMIN_URL``, siehe
``backend/scripts/rls_testlauf.sh``) und wird unter SQLite uebersprungen.

Nicht verglichen werden Server-Defaults (die Models setzen Defaults in Python, die Migrationen teils in der Datenbank)
sowie Row-Level-Security-Regeln und SQL-Funktionen, die Alembic nicht kennt; sie werden in ``test_rls_postgres.py``
getestet.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import app.main  # noqa: F401  (registriert alle Models an Base.metadata)
from app.db import Base

BACKEND = Path(__file__).parents[1]
ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")

# Bekannte, begruendete Abweichungen. Jeder Eintrag braucht eine Begruendung; leer ist der Zielzustand.
BEKANNTE_ABWEICHUNGEN: dict[str, str] = {}


def test_es_gibt_genau_einen_alembic_head():
    """Zwei parallele Branches mit je einer neuen Migration ergeben zwei Heads und scheitern erst beim Deployment."""
    skripte = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    assert len(skripte.get_heads()) == 1, f"Mehrere Alembic-Heads: {skripte.get_heads()}"


@pytest.mark.skipif(not ADMIN_URL, reason="braucht Postgres (TEST_DATABASE_ADMIN_URL, siehe scripts/rls_testlauf.sh)")
def test_frisch_migrierte_postgres_datenbank_stimmt_mit_den_models_ueberein():
    name = f"bq_drift_{uuid.uuid4().hex[:12]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    ziel_url = make_url(ADMIN_URL).set(database=name)
    with admin.connect() as verbindung:
        verbindung.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        umgebung = {**os.environ, "DATABASE_URL": ziel_url.render_as_string(hide_password=False)}
        ergebnis = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND, env=umgebung, capture_output=True, text=True, timeout=300,
        )
        assert ergebnis.returncode == 0, f"alembic upgrade head fehlgeschlagen:\n{ergebnis.stderr[-3000:]}"

        engine = create_engine(ziel_url)
        try:
            with engine.connect() as verbindung:
                kontext = MigrationContext.configure(
                    verbindung, opts={"compare_type": True, "compare_server_default": False}
                )
                unterschiede = compare_metadata(kontext, Base.metadata)
        finally:
            engine.dispose()
    finally:
        with admin.connect() as verbindung:
            verbindung.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()

    offen = [repr(eintrag) for eintrag in unterschiede if repr(eintrag) not in BEKANNTE_ABWEICHUNGEN]
    assert not offen, (
        "Schema-Drift zwischen Migrationen und Models (neue Migration schreiben oder Model angleichen):\n"
        + "\n".join(offen)
    )
