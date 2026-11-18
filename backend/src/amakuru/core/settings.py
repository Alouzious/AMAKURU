"""Typed environment contract. .env.example is the source of truth."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Amakuru"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    widget_base_url: str = "http://localhost:8000/widget"
    log_level: str = "INFO"
    default_language: Literal["en", "lg", "nyn", "sw"] = "en"

    secret_key: str = Field(min_length=32)
    encryption_key: str = Field(min_length=16)

    postgres_user: str = "amakuru"
    postgres_password: str = "change-me"
    postgres_db: str = "amakuru"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = ""
    # App role used for RLS-enforced connections (optional override).
    database_app_user: str = "amakuru_app"
    database_app_password: str = "change-me-app"
    use_app_role: bool = False

    redis_url: str = "redis://localhost:6379/0"

    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    seed_demo_data: bool = True

    llm_provider: str = "groq"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model_primary: str = "openai/gpt-oss-120b"
    llm_model_fast: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: int = 20
    llm_max_output_tokens: int = 400
    llm_temperature: float = 0.0
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""

    # hash = offline deterministic (Phase 2 default for CI/eval); local/openai_compatible later
    embedding_provider: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    embedding_remote_base_url: str = ""
    embedding_remote_api_key: str = ""
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_candidates: int = 20
    hf_token: str = ""
    model_cache_dir: str = "./.models"

    retrieval_top_k: int = 30
    retrieval_final_k: int = 4
    score_verbatim_threshold: float = 0.82
    score_answer_threshold: float = 0.60
    score_clarify_threshold: float = 0.45
    enable_semantic_cache: bool = True
    cache_ttl_seconds: int = 86400

    translation_provider: str = "sunbird"
    sunbird_base_url: str = "https://api.sunbird.ai"
    sunbird_api_token: str = ""
    fasiri_base_url: str = ""
    fasiri_api_key: str = ""

    whatsapp_enabled: bool = False
    meta_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_graph_api_version: str = ""

    email_provider: str = "none"
    email_from: str = "Amakuru <no-reply@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""

    storage_backend: str = "local"
    storage_local_path: str = "./.storage"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = ""

    cors_allowed_origins: str = "http://localhost:3000"
    trusted_hosts: str = "localhost,127.0.0.1"
    session_ttl_minutes: int = 60
    refresh_ttl_days: int = 14
    rate_limit_per_minute_session: int = 20
    rate_limit_per_minute_ip: int = 60
    transcript_retention_days: int = 90
    allow_external_ai_calls: bool = True
    require_2fa_for_approvers: bool = True

    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    default_plan: Literal["starter", "campus", "enterprise"] = "starter"

    # External knowledge connectors (university DB / website)
    allow_private_db_connectors: bool = False
    connector_sync_interval_seconds: int = 900
    search_promote_min_count: int = 3
    worker_scan_interval_seconds: int = 900

    @field_validator("bootstrap_admin_password")
    @classmethod
    def password_length(cls, value: str) -> str:
        if value and len(value) < 12:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters")
        return value

    @model_validator(mode="after")
    def build_database_url(self) -> Settings:
        if not self.database_url:
            user = self.postgres_user
            password = self.postgres_password
            host = self.postgres_host
            port = self.postgres_port
            db = self.postgres_db
            object.__setattr__(
                self,
                "database_url",
                f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}",
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def app_database_url(self) -> str:
        """URL for the non-bypass RLS application role."""
        return (
            f"postgresql+asyncpg://{self.database_app_user}:{self.database_app_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
