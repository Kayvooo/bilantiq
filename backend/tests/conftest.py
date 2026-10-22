import base64
import os
import secrets
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_bilantiq.db")
os.environ.setdefault("API_DOCS_AKTIV", "true")  # Produktion: aus (Standard); die Tests pruefen /docs
os.environ.setdefault("APP_FRONTEND_URL", "https://app.test.invalid")
# No real SMTP account for tests -- app.core.mailer.smtplib.SMTP is mocked wherever a
# test actually sends (see tests/test_versand.py). SMTP ist in der App optional; diese Werte schalten den
# E-Mail-Versand fuer die Tests ein (ohne sie waeren Versand und "Passwort vergessen" abgeschaltet).
os.environ.setdefault("SMTP_HOST", "smtp.test.invalid")
os.environ.setdefault("SMTP_USER", "tests@example.invalid")
os.environ.setdefault("SMTP_PASSWORD", "test-password")
os.environ.setdefault("SMTP_ABSENDER", "noreply@example.invalid")
# Eigener Wegwerf-Speicher statt ./data im Arbeitsverzeichnis (siehe app/core/storage_check.py).
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="bilantiq-test-"))
# Die Mandantentrennungs- und Auth-Tests registrieren mehrere Firmen. Der echte Standard ist "first_account"
# (tests/test_selbst_hosten.py prueft ihn und die anderen Modi ausdruecklich).
os.environ.setdefault("REGISTRATION_MODE", "open")
os.environ.setdefault(
    "DATA_ENCRYPTION_KEYS",
    "v1:" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="),
)
os.environ.setdefault("DATA_ENCRYPTION_ACTIVE_KID", "v1")
os.environ.setdefault("BLIND_INDEX_SECRET", secrets.token_urlsafe(48))

import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


# Postgres-Modus für die Mandantentrennung (siehe docs/specs/rls-postgres.md): Das Schema kommt aus den Migrationen
# (mit RLS-Regeln), die Anwendung verbindet sich als Rolle ohne BYPASSRLS, und diese Fixture leert nur die Tabellen.
ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")


@pytest.fixture(autouse=True)
def _ratelimit_zuruecksetzen():
    """Die IP-Begrenzung (app/core/ratelimit.py) lebt im Prozessspeicher; alle Tests teilen sich die Client-IP."""
    from app.core import ratelimit

    ratelimit.zuruecksetzen()
    yield


@pytest.fixture(autouse=True)
def _totp_uhr(monkeypatch):
    """TOTP-Codes sind seit dem Replay-Schutz (app/auth/mfa_service.py) pro Konto nur einmal pro 30-Sekunden-Schritt
    verwendbar. Tests rufen ``pyotp.TOTP(secret).now()`` aber mehrmals innerhalb weniger Sekunden. Deshalb liefert
    ``.now()`` hier den Code des jeweils NAECHSTEN Zeitschritts, und die Serveruhr (``aktueller_zeitschritt``) laeuft um
    genau so viele Schritte vor. Jeder ``.now()``-Aufruf ergibt damit einen frischen, gueltigen Code, ohne echte Wartezeit.
    Wer Replay explizit testen will, sendet denselben Code zweimal."""
    from app.core import security

    verschiebung = {"schritte": 0}
    echte_uhr = security.aktueller_zeitschritt
    monkeypatch.setattr(security, "aktueller_zeitschritt", lambda: echte_uhr() + verschiebung["schritte"])

    def _naechster_code(self, *args, **kwargs):
        verschiebung["schritte"] += 1
        return self.at((int(time.time() // 30) + verschiebung["schritte"]) * 30)

    monkeypatch.setattr(pyotp.TOTP, "now", _naechster_code)
    yield verschiebung


@pytest.fixture(autouse=True)
def _fresh_db():
    if ADMIN_URL:
        from sqlalchemy import create_engine, text

        admin = create_engine(ADMIN_URL)
        tabellen = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        with admin.begin() as c:
            c.execute(text(f"TRUNCATE {tabellen} RESTART IDENTITY CASCADE"))
        admin.dispose()
        yield
        return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


if ADMIN_URL:
    # Die Anwendung arbeitet als Rolle ohne BYPASSRLS (DATABASE_URL), Testhilfen, die direkt über
    # SessionLocal Daten anlegen oder prüfen, brauchen dagegen Administratorrechte.
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    from app.db import SessionLocal, get_db

    _app_sessions = _sessionmaker(bind=engine, autoflush=False, autocommit=False)
    SessionLocal.configure(bind=_create_engine(ADMIN_URL))

    def _get_db_als_app_rolle():
        db = _app_sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_als_app_rolle


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
