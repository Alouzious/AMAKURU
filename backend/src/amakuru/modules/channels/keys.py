"""Widget key hashing helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_widget_key() -> str:
    return f"ak_live_{secrets.token_urlsafe(24)}"


def hash_widget_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def widget_key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def verify_widget_key(raw_key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_widget_key(raw_key), key_hash)
