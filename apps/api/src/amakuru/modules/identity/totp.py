"""TOTP two-factor authentication helpers."""

from __future__ import annotations

import io
from typing import Any

import pyotp
import qrcode

from amakuru.core.security import decrypt_secret, encrypt_secret
from amakuru.core.settings import Settings
from amakuru.modules.identity.models import User


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def qr_data_url(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    import base64

    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def store_pending_secret(settings: Settings, user: User, secret: str) -> None:
    user.totp_secret_encrypted = encrypt_secret(settings, secret)
    user.totp_enabled = False


def enable_totp(settings: Settings, user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt_secret(settings, user.totp_secret_encrypted)
    if not verify_totp(secret, code):
        return False
    user.totp_enabled = True
    return True


def check_user_totp(settings: Settings, user: User, code: str) -> bool:
    if not user.totp_enabled or not user.totp_secret_encrypted:
        return False
    secret = decrypt_secret(settings, user.totp_secret_encrypted)
    return verify_totp(secret, code)


def setup_payload(settings: Settings, user: User) -> dict[str, Any]:
    secret = generate_totp_secret()
    store_pending_secret(settings, user, secret)
    uri = provisioning_uri(secret=secret, email=user.email, issuer=settings.app_name)
    return {
        "secret": secret,
        "otpauth_url": uri,
        "qr_data_url": qr_data_url(uri),
    }
