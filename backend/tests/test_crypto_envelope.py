import base64
import os

import pytest

from app.config import settings
from app.core.key_management import decrypt_blob, decrypt_text, encrypt_blob, encrypt_text, keyring


def test_envelope_text_is_randomized_and_roundtrips():
    first = encrypt_text("Max Mustermann", purpose="test.person")
    second = encrypt_text("Max Mustermann", purpose="test.person")

    assert first.startswith("enc:v2:")
    assert second.startswith("enc:v2:")
    assert first != second
    assert decrypt_text(first, purpose="test.person") == "Max Mustermann"
    assert decrypt_text(second, purpose="test.person") == "Max Mustermann"


def test_envelope_text_rejects_wrong_purpose_and_tampering():
    encrypted = encrypt_text("DE123456789", purpose="test.tax")

    with pytest.raises(ValueError):
        decrypt_text(encrypted, purpose="test.other")

    prefix, version, kid, payload = encrypted.split(":", 3)
    raw = bytearray(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    raw[-1] ^= 1
    tampered = f"{prefix}:{version}:{kid}:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(ValueError):
        decrypt_text(tampered, purpose="test.tax")


def test_envelope_blob_is_randomized_authenticated_and_roundtrips():
    original = b"%PDF-sensitive-financial-document"
    first = encrypt_blob(original, purpose="test.file")
    second = encrypt_blob(original, purpose="test.file")

    assert first.startswith(b"BQENC2")
    assert second.startswith(b"BQENC2")
    assert first != second
    assert decrypt_blob(first, purpose="test.file") == original

    tampered = bytearray(first)
    tampered[-1] ^= 1
    with pytest.raises(ValueError):
        decrypt_blob(bytes(tampered), purpose="test.file")



def test_old_ciphertext_remains_readable_during_key_rotation(monkeypatch):
    old_keys = settings.data_encryption_keys
    old_active = settings.data_encryption_active_kid
    try:
        key_one = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        key_two = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")

        monkeypatch.setattr(settings, "data_encryption_keys", f"old:{key_one}")
        monkeypatch.setattr(settings, "data_encryption_active_kid", "old")
        keyring.cache_clear()
        old_ciphertext = encrypt_text("rotierbarer Wert", purpose="test.rotation")

        monkeypatch.setattr(settings, "data_encryption_keys", f"old:{key_one},new:{key_two}")
        monkeypatch.setattr(settings, "data_encryption_active_kid", "new")
        keyring.cache_clear()

        assert decrypt_text(old_ciphertext, purpose="test.rotation") == "rotierbarer Wert"
        new_ciphertext = encrypt_text("neuer Wert", purpose="test.rotation")
        assert new_ciphertext.startswith("enc:v2:new:")
        assert decrypt_text(new_ciphertext, purpose="test.rotation") == "neuer Wert"
    finally:
        monkeypatch.setattr(settings, "data_encryption_keys", old_keys)
        monkeypatch.setattr(settings, "data_encryption_active_kid", old_active)
        keyring.cache_clear()
