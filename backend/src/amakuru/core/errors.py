"""Typed application errors."""

from __future__ import annotations


class AmakuruError(Exception):
    def __init__(self, message: str, *, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(AmakuruError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, code="not_found")


class AuthError(AmakuruError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, code="auth_error")


class ForbiddenError(AmakuruError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, code="forbidden")


class ValidationAppError(AmakuruError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="validation_error")


class QuotaExceededError(AmakuruError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="quota_exceeded")
