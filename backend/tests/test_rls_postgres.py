"""Mandantentrennung in der Datenbank selbst (nur mit Postgres-Testmodus, siehe conftest.py).

Die Anwendung verbindet sich hier als Rolle ohne BYPASSRLS. Ohne TEST_DATABASE_ADMIN_URL
(SQLite-Standardlauf) werden die Tests übersprungen, weil SQLite keine RLS kennt.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.models import Einladung, Mandant, Mitgliedschaft, User
from app.core.rls_lookup import mandant_aus_einladung, mandant_des_nutzers
from app.db import SessionLocal, engine, set_rls_mandant
from app.invoices.models import Kontakt

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_ADMIN_URL"), reason="braucht Postgres mit RLS und Rolle ohne BYPASSRLS")


@pytest.fixture
def zwei_mandanten():
    with SessionLocal() as admin:
        a, b = Mandant(firmenname="A GmbH"), Mandant(firmenname="B GmbH")
        admin.add_all([a, b])
        admin.flush()
        admin.add_all([Kontakt(mandant_id=a.id, name="Kunde von A"), Kontakt(mandant_id=b.id, name="Kunde von B")])
        user = User(email_encrypted="x", email_lookup_hash="h" * 64, passwort_hash="x")
        admin.add(user)
        admin.flush()
        admin.add(Mitgliedschaft(user_id=user.id, mandant_id=a.id, rolle="owner"))
        admin.add(Einladung(mandant_id=b.id, code="CODE-B", erstellt_von=user.id, ablauf_am=_morgen()))
        admin.commit()
        return {"a": a.id, "b": b.id, "user": user.id}


def _morgen():
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(days=1)


def test_app_rolle_umgeht_rls_nicht():
    with Session(engine) as db:
        zeile = db.execute(text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")).one()
    assert tuple(zeile) == (False, False)


def test_ohne_mandantenkontext_sind_zeilen_unsichtbar(zwei_mandanten):
    with Session(engine) as db:
        assert db.query(Kontakt).count() == 0


def test_kontext_zeigt_nur_den_eigenen_mandanten(zwei_mandanten):
    with Session(engine) as db:
        set_rls_mandant(db, zwei_mandanten["a"])
        assert [k.name for k in db.query(Kontakt).all()] == ["Kunde von A"]
        set_rls_mandant(db, zwei_mandanten["b"])
        assert [k.name for k in db.query(Kontakt).all()] == ["Kunde von B"]


def test_kontext_ueberlebt_commit_in_derselben_session(zwei_mandanten):
    with Session(engine) as db:
        set_rls_mandant(db, zwei_mandanten["a"])
        db.add(Kontakt(mandant_id=zwei_mandanten["a"], name="Neu 1"))
        db.commit()
        # Neue Transaktion nach dem Commit: der Mandant muss automatisch wieder gesetzt sein.
        assert {k.name for k in db.query(Kontakt).all()} == {"Kunde von A", "Neu 1"}
        db.add(Kontakt(mandant_id=zwei_mandanten["a"], name="Neu 2"))
        db.commit()
        assert db.query(Kontakt).count() == 3


def test_schreiben_in_fremden_mandanten_wird_abgewiesen(zwei_mandanten):
    from sqlalchemy.exc import ProgrammingError

    with Session(engine) as db:
        set_rls_mandant(db, zwei_mandanten["a"])
        db.add(Kontakt(mandant_id=zwei_mandanten["b"], name="Einschleusen"))
        with pytest.raises(ProgrammingError):
            db.flush()


def test_lookup_funktionen_finden_mandanten_ohne_kontext(zwei_mandanten):
    with Session(engine) as db:
        assert mandant_aus_einladung(db, "CODE-B") == zwei_mandanten["b"]
        assert mandant_aus_einladung(db, "gibt-es-nicht") is None
        assert mandant_des_nutzers(db, zwei_mandanten["user"]) == zwei_mandanten["a"]
        # Die Funktionen liefern nur die ID, sie öffnen keine Tabelle.
        assert db.query(Kontakt).count() == 0


def test_audit_log_ist_fuer_app_rolle_append_only(zwei_mandanten):
    from sqlalchemy.exc import ProgrammingError

    from app.core.audit_log import AuditLogEintrag

    with Session(engine) as db:
        set_rls_mandant(db, zwei_mandanten["a"])
        db.add(AuditLogEintrag(mandant_id=zwei_mandanten["a"], user_id=zwei_mandanten["user"], aktion="test", kontext=""))
        db.commit()
        with pytest.raises(ProgrammingError):
            db.execute(text("UPDATE audit_log_eintraege SET aktion = 'manipuliert'"))
        db.rollback()
        with pytest.raises(ProgrammingError):
            db.execute(text("DELETE FROM audit_log_eintraege"))
