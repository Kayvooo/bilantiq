from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.config import settings

_TEXT_PREFIX_V1 = "enc:v1:"
_TEXT_PREFIX_V2 = "enc:v2:"
_FILE_MAGIC_V1 = b"BQENC1"
_FILE_MAGIC_V2 = b"BQENC2"


class CryptoConfigurationError(RuntimeError):
    pass


def _decode_key(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    try:
        key = base64.urlsafe_b64decode(padded.encode())
    except Exception as exc:
        raise CryptoConfigurationError("DATA_ENCRYPTION_KEYS enthaelt keinen gueltigen Base64-Key.") from exc
    if len(key) != 32:
        raise CryptoConfigurationError("Jeder DATA_ENCRYPTION_KEYS-Key muss genau 32 Bytes haben.")
    return key


@lru_cache(maxsize=1)
def keyring() -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for entry in settings.data_encryption_keys.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise CryptoConfigurationError("DATA_ENCRYPTION_KEYS muss als kid:base64[,kid:base64] gesetzt sein.")
        kid, raw = entry.split(":", 1)
        kid = kid.strip()
        if not kid or kid in result:
            raise CryptoConfigurationError("DATA_ENCRYPTION_KEYS enthaelt eine leere oder doppelte Key-ID.")
        result[kid] = _decode_key(raw.strip())
    if not result:
        raise CryptoConfigurationError("DATA_ENCRYPTION_KEYS enthaelt keinen Key.")
    if settings.data_encryption_active_kid not in result:
        raise CryptoConfigurationError("DATA_ENCRYPTION_ACTIVE_KID ist nicht im Keyring vorhanden.")
    return result


@lru_cache(maxsize=2048)
def _derive(master: bytes, purpose: str) -> bytes:
    # Gecacht, weil das Ergebnis nur von (Schluessel, Zweck) abhaengt: ohne Cache laeuft bei
    # jedem entschluesselten Wert ein HKDF, das dominierte Listen und Suche. Die Hauptschluessel
    # liegen ohnehin im Prozessspeicher (keyring), abgeleitete Schluessel sind nicht sensibler.
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=("bilantiq:" + purpose).encode(),
    ).derive(master)


def active_kid() -> str:
    keyring()
    return settings.data_encryption_active_kid


def is_encrypted_text(value: str | None) -> bool:
    return bool(value and (value.startswith(_TEXT_PREFIX_V1) or value.startswith(_TEXT_PREFIX_V2)))


def encrypt_text(value: str, *, purpose: str) -> str:
    """Envelope Encryption: zufaelliger DEK pro Wert, gewrappt mit dem aktiven KEK."""
    kid = active_kid()
    kek = _derive(keyring()[kid], "wrap:" + purpose)
    dek = os.urandom(32)

    wrap_nonce = os.urandom(12)
    wrap_aad = f"bilantiq|text|v2|wrap|{kid}|{purpose}".encode()
    wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, dek, wrap_aad)

    data_nonce = os.urandom(12)
    data_aad = f"bilantiq|text|v2|data|{kid}|{purpose}".encode()
    ciphertext = AESGCM(dek).encrypt(data_nonce, value.encode(), data_aad)

    payload = base64.urlsafe_b64encode(wrap_nonce + wrapped_dek + data_nonce + ciphertext).decode().rstrip("=")
    return f"{_TEXT_PREFIX_V2}{kid}:{payload}"


def decrypt_text(value: str, *, purpose: str) -> str:
    try:
        if value.startswith(_TEXT_PREFIX_V1):
            rest = value[len(_TEXT_PREFIX_V1):]
            kid, encoded = rest.split(":", 1)
            padded = encoded + "=" * (-len(encoded) % 4)
            raw = base64.urlsafe_b64decode(padded.encode())
            nonce, ciphertext = raw[:12], raw[12:]
            key = _derive(keyring()[kid], purpose)
            aad = f"bilantiq|text|v1|{kid}|{purpose}".encode()
            return AESGCM(key).decrypt(nonce, ciphertext, aad).decode()

        if value.startswith(_TEXT_PREFIX_V2):
            rest = value[len(_TEXT_PREFIX_V2):]
            kid, encoded = rest.split(":", 1)
            padded = encoded + "=" * (-len(encoded) % 4)
            raw = base64.urlsafe_b64decode(padded.encode())
            wrap_nonce = raw[:12]
            wrapped_dek = raw[12:60]
            data_nonce = raw[60:72]
            ciphertext = raw[72:]

            kek = _derive(keyring()[kid], "wrap:" + purpose)
            wrap_aad = f"bilantiq|text|v2|wrap|{kid}|{purpose}".encode()
            dek = AESGCM(kek).decrypt(wrap_nonce, wrapped_dek, wrap_aad)
            data_aad = f"bilantiq|text|v2|data|{kid}|{purpose}".encode()
            return AESGCM(dek).decrypt(data_nonce, ciphertext, data_aad).decode()
    except Exception as exc:
        raise ValueError("Verschluesselter Wert konnte nicht authentifiziert/entschluesselt werden.") from exc
    raise ValueError("Wert ist kein Bilantiq-AES-GCM-Ciphertext.")


def is_encrypted_blob(data: bytes) -> bool:
    return data.startswith(_FILE_MAGIC_V1) or data.startswith(_FILE_MAGIC_V2)


def encrypt_blob(data: bytes, *, purpose: str) -> bytes:
    kid = active_kid()
    kid_raw = kid.encode()
    if len(kid_raw) > 255:
        raise CryptoConfigurationError("Key-ID ist zu lang.")

    kek = _derive(keyring()[kid], "wrap:" + purpose)
    dek = os.urandom(32)
    wrap_nonce = os.urandom(12)
    wrap_aad = b"bilantiq|file|v2|wrap|" + kid_raw + b"|" + purpose.encode()
    wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, dek, wrap_aad)

    data_nonce = os.urandom(12)
    data_aad = b"bilantiq|file|v2|data|" + kid_raw + b"|" + purpose.encode()
    ciphertext = AESGCM(dek).encrypt(data_nonce, data, data_aad)
    return _FILE_MAGIC_V2 + bytes([len(kid_raw)]) + kid_raw + wrap_nonce + wrapped_dek + data_nonce + ciphertext


def decrypt_blob(data: bytes, *, purpose: str) -> bytes:
    try:
        if data.startswith(_FILE_MAGIC_V1):
            pos = len(_FILE_MAGIC_V1)
            kid_len = data[pos]
            pos += 1
            kid = data[pos:pos + kid_len].decode()
            pos += kid_len
            nonce = data[pos:pos + 12]
            ciphertext = data[pos + 12:]
            key = _derive(keyring()[kid], purpose)
            aad = b"bilantiq|file|v1|" + kid.encode() + b"|" + purpose.encode()
            return AESGCM(key).decrypt(nonce, ciphertext, aad)

        if data.startswith(_FILE_MAGIC_V2):
            pos = len(_FILE_MAGIC_V2)
            kid_len = data[pos]
            pos += 1
            kid = data[pos:pos + kid_len].decode()
            pos += kid_len
            wrap_nonce = data[pos:pos + 12]
            pos += 12
            wrapped_dek = data[pos:pos + 48]
            pos += 48
            data_nonce = data[pos:pos + 12]
            pos += 12
            ciphertext = data[pos:]

            kek = _derive(keyring()[kid], "wrap:" + purpose)
            wrap_aad = b"bilantiq|file|v2|wrap|" + kid.encode() + b"|" + purpose.encode()
            dek = AESGCM(kek).decrypt(wrap_nonce, wrapped_dek, wrap_aad)
            data_aad = b"bilantiq|file|v2|data|" + kid.encode() + b"|" + purpose.encode()
            return AESGCM(dek).decrypt(data_nonce, ciphertext, data_aad)
    except Exception as exc:
        raise ValueError("Verschluesselte Datei konnte nicht authentifiziert/entschluesselt werden.") from exc
    raise ValueError("Datei ist kein Bilantiq-AES-GCM-Ciphertext.")


def blind_index(value: str, *, purpose: str) -> str:
    normalized = value.strip().casefold().encode()
    key = _derive(settings.blind_index_secret.encode(), "blind-index:" + purpose)
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()
