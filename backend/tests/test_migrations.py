from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.core.crypto import decrypt_field_compat


def test_fresh_sqlite_database_migrates_to_head(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "fresh.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    expected_revision = ScriptDirectory.from_config(config).get_current_head()
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert revision == expected_revision


def test_fresh_sqlite_database_hat_keine_billing_spuren_mehr(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'ohne-billing.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        pruefer = inspect(engine)
        mandant_spalten = {s["name"] for s in pruefer.get_columns("mandanten")}
        rechnung_spalten = {s["name"] for s in pruefer.get_columns("invoices")}
        tabellen = set(pruefer.get_table_names())
    finally:
        engine.dispose()

    assert not {"tarif", "tarif_status", "stripe_customer_id", "stripe_subscription_id", "tarif_gueltig_bis"} & mandant_spalten
    assert not {
        "zahllink_token_verschluesselt", "zahllink_token_hash", "stripe_checkout_session_id",
        "stripe_checkout_session_versuch", "stripe_checkout_session_expires_at", "online_bezahlt_am",
    } & rechnung_spalten
    assert "webhook_ereignisse" not in tabellen


def test_migration_0039_entfernt_billing_und_erhaelt_bestandsdaten(tmp_path: Path, monkeypatch) -> None:
    """Upgrade von 0038 mit Beispieldaten: Mandant, Rechnung und Audit-Eintrag bleiben unveraendert lesbar."""
    database_url = f"sqlite:///{(tmp_path / 'm0039.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0038")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO mandanten (id, firmenname, tarif, tarif_status, stripe_customer_id, erstellt_am) "
                "VALUES ('m-1', 'Beispiel GmbH', 'business', 'active', 'cus_beispiel', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO kontakte (id, mandant_id, name, land, ist_geschaeftskunde, erstellt_am) "
                "VALUES ('k-1', 'm-1', 'Kunde', 'DE', 1, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO invoices (id, mandant_id, kontakt_id, status, leistungsdatum, faelligkeitsdatum, waehrung, "
                "netto_gesamt, ust_gesamt, brutto_gesamt, erstellt_am, zahllink_token_hash, stripe_checkout_session_versuch) "
                "VALUES ('i-1', 'm-1', 'k-1', 'final', '2026-10-01', '2026-10-15', 'EUR', '100.00', '19.00', '119.00', "
                "CURRENT_TIMESTAMP, 'hash-beispiel', 2)"
            )
        )
        connection.execute(text("INSERT INTO webhook_ereignisse (stripe_event_id, verarbeitet_am) VALUES ('evt_1', CURRENT_TIMESTAMP)"))
        connection.execute(
            text(
                "INSERT INTO audit_log_eintraege (id, mandant_id, aktion, kontext, zeitpunkt) "
                "VALUES ('a-1', 'm-1', 'rechnung_online_bezahlt', 'RE-1', CURRENT_TIMESTAMP)"
            )
        )
        audit_vorher = connection.execute(text("SELECT * FROM audit_log_eintraege WHERE id = 'a-1'")).fetchall()
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            mandant = connection.execute(text("SELECT id, firmenname FROM mandanten WHERE id = 'm-1'")).one()
            rechnung = connection.execute(text("SELECT id, status, brutto_gesamt FROM invoices WHERE id = 'i-1'")).one()
            audit_nachher = connection.execute(text("SELECT * FROM audit_log_eintraege WHERE id = 'a-1'")).fetchall()
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert "webhook_ereignisse" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    assert tuple(mandant) == ("m-1", "Beispiel GmbH")
    assert tuple(rechnung)[:2] == ("i-1", "final")
    assert audit_nachher == audit_vorher  # Audit-Log (inkl. Hash-Kette) bleibt unveraendert
    assert revision == ScriptDirectory.from_config(config).get_current_head()

    # Rueckweg 0039 -> 0038 -> 0039 laeuft durch (die Billing-Daten selbst kommen dabei nicht zurueck).
    command.downgrade(config, "0038")
    engine = create_engine(database_url)
    try:
        assert "tarif" in {s["name"] for s in inspect(engine).get_columns("mandanten")}
        assert "webhook_ereignisse" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
    command.upgrade(config, "head")


def test_security_migration_encrypts_existing_plaintext_rows(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "security-upgrade.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0028")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO mandanten (id, firmenname, tarif, tarif_status, erstellt_am) "
                "VALUES (:id, :name, 'free', 'active', CURRENT_TIMESTAMP)"
            ),
            {"id": "mandant-security-test", "name": "Klartext Finanz GmbH"},
        )
        legacy_email = Fernet(settings.field_encryption_key.encode()).encrypt(b"legacy@example.com").decode()
        connection.execute(
            text(
                "INSERT INTO audit_log_eintraege "
                "(id, mandant_id, aktion, kontext, zeitpunkt) "
                "VALUES ('audit-security-test', 'mandant-security-test', 'legacy', 'Klartext Audit Kontext', CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email_encrypted, email_lookup_hash, passwort_hash, erstellt_am) "
                "VALUES ('user-security-test', :email, :lookup, 'legacy-hash', CURRENT_TIMESTAMP)"
            ),
            {"email": legacy_email, "lookup": "a" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO kontakte "
                "(id, mandant_id, name, land, ist_geschaeftskunde, erstellt_am) "
                "VALUES (:id, :mandant_id, :name, 'DE', 1, CURRENT_TIMESTAMP)"
            ),
            {
                "id": "kontakt-security-test",
                "mandant_id": "mandant-security-test",
                "name": "Max Klartext",
            },
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        raw_company = connection.execute(
            text("SELECT firmenname FROM mandanten WHERE id='mandant-security-test'")
        ).scalar_one()
        raw_contact = connection.execute(
            text("SELECT name FROM kontakte WHERE id='kontakt-security-test'")
        ).scalar_one()
        raw_email = connection.execute(
            text("SELECT email_encrypted FROM users WHERE id='user-security-test'")
        ).scalar_one()
        raw_audit = connection.execute(
            text("SELECT kontext FROM audit_log_eintraege WHERE id='audit-security-test'")
        ).scalar_one()
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert revision == ScriptDirectory.from_config(config).get_current_head()
    assert raw_company.startswith("enc:v2:")
    assert raw_contact.startswith("enc:v2:")
    assert raw_email.startswith("enc:v2:")
    assert raw_audit.startswith("enc:v2:")
    assert "Klartext Audit Kontext" not in raw_audit
    assert decrypt_field_compat(raw_email) == "legacy@example.com"
    assert "Klartext Finanz GmbH" not in raw_company
    assert "Max Klartext" not in raw_contact


def test_e_rechnung_migration_ergaenzt_beleg_spalten_mit_ocr_als_standard(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{(tmp_path / 'e_rechnung.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    spalten = {spalte["name"]: spalte for spalte in inspect(engine).get_columns("receipts")}
    indizes = {index["name"] for index in inspect(engine).get_indexes("receipts")}
    engine.dispose()

    assert {"beleg_typ", "rechnungsnummer", "faelligkeit", "iban", "e_rechnung_daten", "dedupe_key"} <= set(spalten)
    assert spalten["beleg_typ"]["nullable"] is False
    assert "'ocr'" in str(spalten["beleg_typ"]["default"])
    assert "ix_receipts_dedupe_key" in indizes


def test_migration_0038_legt_wiederherstellungs_und_reset_tabellen_passend_zu_den_models_an(tmp_path: Path, monkeypatch) -> None:
    """Frische SQLite bis Head: Spalten, Indizes und Eindeutigkeit der 0038-Objekte stimmen mit den Models ueberein
    (die vollstaendige Drift-Pruefung gegen Postgres steht in test_schema_drift.py)."""
    import app.main  # noqa: F401  (registriert alle Models)
    from app.db import Base

    database_url = f"sqlite:///{(tmp_path / 'm0038.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        pruefer = inspect(engine)
        for tabelle in ("mfa_wiederherstellungscodes", "passwort_reset_tokens"):
            migriert = {s["name"]: s for s in pruefer.get_columns(tabelle)}
            modell = Base.metadata.tables[tabelle].columns
            assert set(migriert) == set(modell.keys()), tabelle
            for spalte in modell:
                assert migriert[spalte.name]["nullable"] == spalte.nullable, f"{tabelle}.{spalte.name}"
            indizes = {i["name"] for i in pruefer.get_indexes(tabelle)}
            assert {f"ix_{tabelle}_user_id", f"ix_{tabelle}_mandant_id"} <= indizes
            fremdschluessel = {fk["referred_table"] for fk in pruefer.get_foreign_keys(tabelle)}
            assert fremdschluessel == {"users", "mandanten"}
        eindeutig = pruefer.get_unique_constraints("passwort_reset_tokens")
        assert [u["column_names"] for u in eindeutig] == [["token_hash"]]
        nutzer = {s["name"]: s for s in pruefer.get_columns("users")}
        assert nutzer["mfa_letzter_zeitschritt"]["nullable"] is True
    finally:
        engine.dispose()

    # Rueckweg 0038 -> 0037 -> 0038 funktioniert und raeumt vollstaendig auf.
    command.downgrade(config, "0037")
    engine = create_engine(database_url)
    try:
        tabellen = set(inspect(engine).get_table_names())
        assert not {"mfa_wiederherstellungscodes", "passwort_reset_tokens"} & tabellen
        assert "mfa_letzter_zeitschritt" not in {s["name"] for s in inspect(engine).get_columns("users")}
    finally:
        engine.dispose()
    command.upgrade(config, "head")
