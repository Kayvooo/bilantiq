import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.key_management import decrypt_text, encrypt_text, is_encrypted_text

_legacy_fernet = Fernet(settings.field_encryption_key.encode())


def encrypt_field(value: str, *, purpose: str = "legacy-field") -> str:
    return encrypt_text(value, purpose=purpose)


def decrypt_field_compat(value: str, *, purpose: str = "legacy-field") -> str:
    if is_encrypted_text(value):
        return decrypt_text(value, purpose=purpose)
    try:
        return _legacy_fernet.decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Sensibles Datenfeld ist nicht gueltig verschluesselt.") from exc


def decrypt_field(token: str, *, purpose: str = "legacy-field") -> str:
    return decrypt_field_compat(token, purpose=purpose)


def lookup_hash(value: str) -> str:
    """Deterministic HMAC for looking up an encrypted field (e.g. email) without decrypting
    every row. Not reversible, so it does not weaken the field's confidentiality."""
    return hmac.new(settings.email_lookup_secret.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()
