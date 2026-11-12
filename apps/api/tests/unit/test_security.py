"""Unit tests for password hashing and encryption."""

from __future__ import annotations

from amakuru.core.security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    sign_value,
    unsign_value,
    verify_password,
)
from amakuru.core.settings import get_settings


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password(hashed, "CorrectHorseBatteryStaple!")
    assert not verify_password(hashed, "wrong-password")


def test_sign_unsign() -> None:
    signed = sign_value("secret", "abc")
    assert unsign_value("secret", signed) == "abc"
    assert unsign_value("secret", "abc.deadbeef") is None


def test_encrypt_decrypt() -> None:
    settings = get_settings()
    token = encrypt_secret(settings, "whatsapp-token-demo")
    assert decrypt_secret(settings, token) == "whatsapp-token-demo"
    assert token != "whatsapp-token-demo"
