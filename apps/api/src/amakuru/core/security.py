"""Password hashing, session tokens, CSRF, and field encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from amakuru.core.settings import Settings

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sign_value(secret: str, value: str) -> str:
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def unsign_value(secret: str, signed: str) -> str | None:
    if "." not in signed:
        return None
    value, digest = signed.rsplit(".", 1)
    expected = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    return value


def csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _fernet(settings: Settings) -> Fernet:
    # ENCRYPTION_KEY is urlsafe base64 of 32 bytes (Fernet key), or we derive one.
    raw = settings.encryption_key.encode()
    try:
        return Fernet(raw)
    except (ValueError, InvalidToken):
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        return Fernet(derived)


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return _fernet(settings).encrypt(plaintext.encode()).decode()


def decrypt_secret(settings: Settings, ciphertext: str) -> str:
    return _fernet(settings).decrypt(ciphertext.encode()).decode()


def session_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes)


def refresh_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_ttl_days)


def parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def session_payload(
    *,
    user_id: UUID,
    session_id: str,
    csrf: str,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "user_id": str(user_id),
        "session_id": session_id,
        "csrf": csrf,
        "expires_at": expires_at.isoformat(),
    }
