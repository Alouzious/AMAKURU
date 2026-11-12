"""Phase 7 commercial: plans, usage_events, api_keys.

Revision ID: 20261112_0005
Revises: 20261112_0004
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261112_0005"
down_revision: str | None = "20261112_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("usage_events", "api_keys")


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_isolation ON {table}
        FOR ALL
        USING (
          current_setting('app.tenant_id', true) IS NULL
          OR current_setting('app.tenant_id', true) = ''
          OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
          current_setting('app.tenant_id', true) IS NULL
          OR current_setting('app.tenant_id', true) = ''
          OR tenant_id::text = current_setting('app.tenant_id', true)
        );
        """
    )


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "entitlements",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(12, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "day", "event_type", name="uq_usage_events_tenant_day_type"
        ),
    )
    op.create_index("ix_usage_events_tenant_id", "usage_events", ["tenant_id"])
    op.create_index("ix_usage_events_day", "usage_events", ["day"])

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_hash"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])

    for table in TENANT_TABLES:
        _rls(table)

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE plans, usage_events, api_keys TO amakuru_app"
    )

    # Seed plan catalogue (source of truth also in Python catalog module).
    # Bind named params so JSON colons are not treated as SQLAlchemy bind markers.
    import json

    catalog = [
        (
            "starter",
            "Starter",
            "Single campus FAQ bot — widget only, English.",
            {
                "max_published_answers": 100,
                "monthly_answered_conversations": 2000,
                "languages": ["en"],
                "whatsapp": False,
                "api_access": False,
                "custom_domain": False,
                "white_label": False,
                "sovereign_deployment": False,
                "support_level": "community",
            },
        ),
        (
            "campus",
            "Campus",
            "Multi-language campus with WhatsApp and API access.",
            {
                "max_published_answers": 1000,
                "monthly_answered_conversations": 25000,
                "languages": ["en", "lg", "nyn", "sw"],
                "whatsapp": True,
                "api_access": True,
                "custom_domain": False,
                "white_label": False,
                "sovereign_deployment": False,
                "support_level": "standard",
            },
        ),
        (
            "enterprise",
            "Enterprise",
            "White-label, sovereign option, high volume.",
            {
                "max_published_answers": 10000,
                "monthly_answered_conversations": 500000,
                "languages": ["en", "lg", "nyn", "sw", "ach", "teo", "lgg"],
                "whatsapp": True,
                "api_access": True,
                "custom_domain": True,
                "white_label": True,
                "sovereign_deployment": True,
                "support_level": "priority",
            },
        ),
    ]
    for code, name, description, entitlements in catalog:
        op.execute(
            sa.text(
                "INSERT INTO plans (code, name, description, entitlements) "
                "VALUES (:code, :name, :description, CAST(:ents AS jsonb)) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                code=code,
                name=name,
                description=description,
                ents=json.dumps(entitlements),
            )
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.drop_table(table)
    op.drop_table("plans")
