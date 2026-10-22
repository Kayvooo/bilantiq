import hmac
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$argon2"):
        try:
            return _password_hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    if not password_hash.startswith("$argon2"):
        return True
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_token(
    *,
    user_id: str,
    scope: str,
    mandant_id: str | None = None,
    minutes: int | None = None,
    session_id: str | None = None,
    security_version: int | None = None,
) -> str:
    """Pre-MFA tokens bleiben kurzlebig; Full-Tokens sind zusaetzlich serverseitig widerrufbar."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.access_token_minutes)
    payload = {"sub": user_id, "scope": scope, "mandant_id": mandant_id, "exp": expires_at}
    if session_id is not None:
        payload["sid"] = session_id
    if security_version is not None:
        payload["sv"] = security_version
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def mfa_provisioning_uri(*, secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.mfa_issuer)


TOTP_INTERVALL_SEKUNDEN = 30


def aktueller_zeitschritt() -> int:
    """Aktueller TOTP-Zeitschritt (Unix-Zeit // 30). Eigene Funktion, damit Tests die Uhr kontrolliert verschieben koennen."""
    return int(time.time() // TOTP_INTERVALL_SEKUNDEN)


def pruefe_mfa_zeitschritt(*, secret: str, code: str, letzter_zeitschritt: int | None) -> int | None:
    """Prueft einen TOTP-Code (Toleranz: +-1 Zeitschritt) und liefert den Zeitschritt, zu dem er passt.

    Replay-Schutz: Ein Code, dessen Zeitschritt nicht groesser ist als ``letzter_zeitschritt`` (zuletzt akzeptierter
    Schritt dieses Kontos), gilt als bereits verbraucht und wird abgelehnt. Das Ergebnis muss der Aufrufer
    zusammen mit dem Vergleich atomar speichern (``app/auth/mfa_service.py::verbrauche_totp``).
    Gibt None zurueck, wenn der Code falsch oder verbraucht ist."""
    totp = pyotp.TOTP(secret)
    jetzt = aktueller_zeitschritt()
    gegeben = code.encode()
    treffer: int | None = None
    for schritt in (jetzt - 1, jetzt, jetzt + 1):  # alle drei vergleichen, kein vorzeitiger Abbruch
        erwartet = totp.at(schritt * TOTP_INTERVALL_SEKUNDEN).encode()
        if hmac.compare_digest(erwartet, gegeben):
            treffer = schritt
    if treffer is None or (letzter_zeitschritt is not None and treffer <= letzter_zeitschritt):
        return None
    return treffer


def verify_mfa_code(*, secret: str, code: str) -> bool:
    """Zustandslose Pruefung OHNE Replay-Schutz. Fuer Anmelde- und Sicherheitspfade nicht verwenden, sondern
    ``app.auth.mfa_service.verbrauche_totp`` (einmal verbrauchbar pro Zeitschritt)."""
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
