from __future__ import annotations

import os
from pathlib import Path

from app.core.key_management import decrypt_blob, encrypt_blob, is_encrypted_blob


def _purpose(prefix: str, relative_path: str) -> str:
    parts = Path(relative_path).parts
    if not parts or parts[0] in {"", ".", ".."}:
        raise ValueError("Ungueltige Storage-Referenz.")
    return f"{prefix}:{parts[0]}"


def _safe_path(root: str, relative_path: str) -> Path:
    base = Path(root).resolve()
    full = (base / relative_path).resolve()
    if full != base and base not in full.parents:
        raise ValueError("Storage-Referenz verlaesst das konfigurierte Datenverzeichnis.")
    return full


def write_encrypted(root: str, relative_path: str, data: bytes, *, purpose_prefix: str) -> None:
    full_path = _safe_path(root, relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(full_path.parent, 0o700)
    if full_path.exists():
        return
    encrypted = encrypt_blob(data, purpose=_purpose(purpose_prefix, relative_path))
    tmp = full_path.with_name(full_path.name + ".tmp")
    tmp.write_bytes(encrypted)
    os.replace(tmp, full_path)
    os.chmod(full_path, 0o600)


def read_encrypted(root: str, relative_path: str, *, purpose_prefix: str) -> bytes:
    data = _safe_path(root, relative_path).read_bytes()
    if not is_encrypted_blob(data):
        # Bestandsdateien aus Releases vor Security Phase 3 bleiben bis zum einmaligen
        # reencrypt_storage.py-Lauf lesbar. Neue Writes sind immer verschluesselt.
        return data
    return decrypt_blob(data, purpose=_purpose(purpose_prefix, relative_path))


def reencrypt_tree(root: str, *, purpose_prefix: str) -> tuple[int, int]:
    base = Path(root)
    if not base.exists():
        return 0, 0
    encrypted_count = 0
    skipped_count = 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(base))
        data = path.read_bytes()
        if is_encrypted_blob(data):
            skipped_count += 1
            continue
        encrypted = encrypt_blob(data, purpose=_purpose(purpose_prefix, relative))
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(encrypted)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        encrypted_count += 1
    return encrypted_count, skipped_count


def rotate_tree(root: str, *, purpose_prefix: str) -> tuple[int, int]:
    """Schreibt vorhandene Ciphertexte mit dem aktuell aktiven Key neu.

    Legacy-Klartext wird dabei ebenfalls verschluesselt. Vor dem Entfernen eines alten
    Key aus DATA_ENCRYPTION_KEYS muss dieser Lauf erfolgreich abgeschlossen sein.
    """
    base = Path(root)
    if not base.exists():
        return 0, 0
    rotated = 0
    failed = 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(base))
        try:
            data = path.read_bytes()
            plaintext = decrypt_blob(data, purpose=_purpose(purpose_prefix, relative)) if is_encrypted_blob(data) else data
            encrypted = encrypt_blob(plaintext, purpose=_purpose(purpose_prefix, relative))
            tmp = path.with_name(path.name + ".rotate")
            tmp.write_bytes(encrypted)
            os.replace(tmp, path)
            os.chmod(path, 0o600)
            rotated += 1
        except Exception:
            failed += 1
    return rotated, failed
