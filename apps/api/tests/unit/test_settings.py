"""Settings validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from amakuru.core.settings import Settings, clear_settings_cache


def test_database_url_built_from_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcysh")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "amakuru")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "a@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMeNow123!")
    monkeypatch.setenv("LLM_API_KEY", "k")
    s = Settings()  # type: ignore[call-arg]
    assert s.database_url.startswith("postgresql+asyncpg://u:p@db.example:5433/amakuru")


def test_short_bootstrap_password_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcysh")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "a@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    monkeypatch.setenv("LLM_API_KEY", "k")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
