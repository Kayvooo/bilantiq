from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt_field_compat
from app.core.key_management import encrypt_text


class EncryptedText(TypeDecorator):
    """Transparent AES-256-GCM field encryption for values not queried by plaintext.

    The physical database column is Text because authenticated ciphertext is larger
    than the original value. Equality/range/order queries on this type are deliberately
    not meaningful; searchable secrets need a separate HMAC blind-index column.
    """

    impl = Text
    cache_ok = True

    def __init__(self, purpose: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        return encrypt_text(value, purpose=self.purpose)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_field_compat(value, purpose=self.purpose)


class EncryptedDecimal(TypeDecorator):
    """AES-GCM encrypted Decimal for monetary/quantity values not queried in SQL.

    Filters/sums/ranges on this physical Text column are intentionally unsupported;
    Bilantiq's accounting reports load tenant/date-scoped rows and calculate amounts
    deterministically in Python.
    """

    impl = Text
    cache_ok = True

    def __init__(self, purpose: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.purpose = purpose

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        return encrypt_text(format(decimal_value, "f"), purpose=self.purpose)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        plaintext = decrypt_field_compat(value, purpose=self.purpose)
        return Decimal(plaintext)
