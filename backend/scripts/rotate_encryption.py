"""Rotiert Bilantiq-Ciphertexte auf DATA_ENCRYPTION_ACTIVE_KID.

Ablauf:
1. Neuen Key ZUSAETZLICH in DATA_ENCRYPTION_KEYS aufnehmen.
2. DATA_ENCRYPTION_ACTIVE_KID auf dessen kid setzen und Backend neu starten.
3. Vollstaendiges verschluesseltes Backup erstellen.
4. Dieses Skript ausfuehren.
5. `python -m scripts.rotate_encryption --pruefen` ausfuehren: es muss "alles auf dem aktiven Key" melden.
6. Regression/Smoke-Test.
7. Alten Key erst entfernen, wenn `--pruefen` alles auf dem aktiven Key meldet und ein Backup
   mit dem alten Key nicht mehr gebraucht wird.

Welche Spalten rotiert werden, wird aus den Modellen abgeleitet (jede EncryptedText- und
EncryptedDecimal-Spalte kennt ihren Verwendungszweck). Eine neue verschluesselte Spalte ist damit
automatisch dabei. Frueher stand hier eine handgepflegte Liste, der 42 Spalten fehlten, darunter alle
Rechnungs- und Belegbetraege: Bei einer Rotation waeren sie mit dem alten Key verschluesselt geblieben.
Nur Spalten, die per Hand ueber encrypt_field() gefuellt werden (LEGACY_FIELDS), stehen weiter hier.
"""
import argparse

from sqlalchemy import text

import app.main  # noqa: F401 (registriert alle Modelle an Base.metadata)
from app.config import settings
from app.core.crypto import decrypt_field_compat, encrypt_field
from app.core.encrypted_types import EncryptedDecimal, EncryptedText
from app.core.key_management import decrypt_text, encrypt_text, is_encrypted_text
from app.core.secure_storage import rotate_tree
from app.db import Base, SessionLocal


def verschluesselte_spalten() -> dict[str, dict[str, str]]:
    """tabelle -> {spalte: verwendungszweck}, abgeleitet aus den Modellen."""
    ergebnis: dict[str, dict[str, str]] = {}
    for tabelle in Base.metadata.sorted_tables:
        for spalte in tabelle.columns:
            if isinstance(spalte.type, (EncryptedText, EncryptedDecimal)):
                ergebnis.setdefault(tabelle.name, {})[spalte.name] = spalte.type.purpose
    return ergebnis


def _primaerschluessel(tabelle: str) -> str:
    spalten = list(Base.metadata.tables[tabelle].primary_key.columns)
    if len(spalten) != 1:
        raise SystemExit(f"Tabelle {tabelle} hat keinen einfachen Primaerschluessel, Rotation nicht moeglich.")
    return spalten[0].name


FIELDS: dict[str, dict[str, str]] = verschluesselte_spalten()

LEGACY_FIELDS: dict[str, tuple[str, ...]] = {
    "users": ("email_encrypted", "mfa_secret_encrypted", "mfa_pending_secret_encrypted"),
    "mitarbeitende": ("vorname_encrypted", "nachname_encrypted"),
}


def _klartext(raw: str, purpose: str) -> str:
    """Entschluesselt einen gespeicherten Wert. Altbestand wird nicht verschluckt: ein altes Fernet-Token
    wird erst entschluesselt, nur wirklich nie verschluesselter Text wird unveraendert neu verschluesselt."""
    if is_encrypted_text(raw):
        return decrypt_text(raw, purpose=purpose)
    try:
        return decrypt_field_compat(raw, purpose=purpose)
    except ValueError:
        return raw


AUDIT_TABELLE = "audit_log_eintraege"


def _audit_ist_gesperrt(db) -> bool:
    """Auf Postgres verbietet ein Trigger jede Aenderung am Audit-Log (Migration 0001), auch das Neuverschluesseln."""
    if db.get_bind().dialect.name != "postgresql":
        return False
    return bool(db.execute(text(
        "SELECT 1 FROM pg_trigger WHERE tgname = 'audit_log_append_only' AND NOT tgisinternal"
    )).first())


def rotate_db() -> int:
    changed = 0
    with SessionLocal() as db:
        audit_gesperrt = _audit_ist_gesperrt(db)
        for table, columns in FIELDS.items():
            if table == AUDIT_TABELLE and audit_gesperrt:
                continue  # bleibt auf dem alten Key, pruefe_aktiven_key() meldet das
            pk = _primaerschluessel(table)
            for column, purpose in columns.items():
                rows = db.execute(
                    text(f'SELECT "{pk}" AS id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
                ).mappings().all()
                for row in rows:
                    new_value = encrypt_text(_klartext(str(row["value"]), purpose), purpose=purpose)
                    db.execute(
                        text(f'UPDATE "{table}" SET "{column}" = :value WHERE "{pk}" = :id'),
                        {"value": new_value, "id": row["id"]},
                    )
                    changed += 1

        for table, columns in LEGACY_FIELDS.items():
            pk = _primaerschluessel(table)
            for column in columns:
                rows = db.execute(
                    text(f'SELECT "{pk}" AS id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')
                ).mappings().all()
                for row in rows:
                    plaintext = decrypt_field_compat(str(row["value"]))
                    new_value = encrypt_field(plaintext)
                    db.execute(
                        text(f'UPDATE "{table}" SET "{column}" = :value WHERE "{pk}" = :id'),
                        {"value": new_value, "id": row["id"]},
                    )
                    changed += 1
        db.commit()
    return changed


def kid_von(wert: str) -> str | None:
    """Der kid eines gespeicherten Werts (enc:v2:<kid>:...), None bei Altformat oder Klartext."""
    if not is_encrypted_text(wert):
        return None
    teile = wert.split(":", 3)
    return teile[2] if len(teile) == 4 else None


def pruefe_aktiven_key() -> dict[str, int]:
    """Zaehlt je Spalte die Werte, die NICHT mit dem aktiven Key verschluesselt sind (nur lesen).
    Leer = der alte Key wird fuer die Datenbank nicht mehr gebraucht."""
    offen: dict[str, int] = {}
    alle = {**{t: tuple(c) for t, c in FIELDS.items()}}
    for table, columns in LEGACY_FIELDS.items():
        alle[table] = tuple(dict.fromkeys((*alle.get(table, ()), *columns)))
    with SessionLocal() as db:
        for table, columns in alle.items():
            pk = _primaerschluessel(table)
            for column in columns:
                werte = db.execute(text(f'SELECT "{pk}" AS id, "{column}" AS value FROM "{table}" WHERE "{column}" IS NOT NULL')).mappings().all()
                veraltet = sum(1 for zeile in werte if kid_von(str(zeile["value"])) != settings.data_encryption_active_kid)
                if veraltet:
                    offen[f"{table}.{column}"] = veraltet
    return offen


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotiert Ciphertexte auf den aktiven Key.")
    parser.add_argument("--pruefen", action="store_true", help="nur pruefen, ob alles auf dem aktiven Key liegt (aendert nichts)")
    args = parser.parse_args()

    if args.pruefen:
        offen = pruefe_aktiven_key()
        if offen:
            for name, anzahl in sorted(offen.items()):
                print(f"  {name}: {anzahl} Werte nicht auf dem aktiven Key")
            raise SystemExit("Nicht alles ist rotiert. Alten Key NICHT entfernen.")
        print("Datenbank: alle verschluesselten Werte liegen auf dem aktiven Key.")
        return

    count = rotate_db()
    print(f"Datenbank: {count} sensible Werte auf aktiven Key rotiert")
    offen = pruefe_aktiven_key()
    audit_offen = {n: a for n, a in offen.items() if n.startswith(f"{AUDIT_TABELLE}.")}
    sonstige = {n: a for n, a in offen.items() if n not in audit_offen}
    if sonstige:
        for name, anzahl in sorted(sonstige.items()):
            print(f"  {name}: {anzahl} Werte nicht auf dem aktiven Key")
        raise SystemExit("Datenbankrotation unvollstaendig; alten Key NICHT entfernen.")
    for name, anzahl in sorted(audit_offen.items()):
        print(f"  {name}: {anzahl} Werte bleiben auf dem alten Key (Audit-Log ist append-only). Alten Key BEHALTEN.")

    failures = 0
    for name, root, purpose in [
        ("Belege", settings.receipt_storage_dir, "receipt-file"),
        ("Logos", settings.branding_storage_dir, "branding-file"),
        ("Briefpapier", settings.letterhead_storage_dir, "letterhead-file"),
        ("Kontoauszüge", settings.bank_storage_dir, "bank-file"),
        ("Altrechnungen", settings.altrechnung_storage_dir, "altrechnung-file"),
    ]:
        rotated, failed = rotate_tree(root, purpose_prefix=purpose)
        failures += failed
        print(f"{name}: {rotated} Dateien rotiert, {failed} Fehler")

    if failures:
        raise SystemExit("Dateirotation unvollstaendig; alten Key NICHT entfernen.")
    if audit_offen:
        raise SystemExit("Rotation fertig bis auf das Audit-Log: der alte Key wird dafuer weiter gebraucht.")


if __name__ == "__main__":
    main()
