"""API key generation and verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    return f"ak_api_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def api_key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), key_hash)
