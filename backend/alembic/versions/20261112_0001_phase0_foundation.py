"""Phase 0 foundation: tenants, users, memberships, sessions, audit_log, RLS.

Revision ID: 20261112_0001
Revises:
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261112_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Optional RLS app role — skipped on hosted Postgres (e.g. Neon) without CREATEROLE.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
            BEGIN
              CREATE ROLE amakuru_app LOGIN PASSWORD 'change-me-app';
            EXCEPTION
              WHEN insufficient_privilege THEN
                RAISE NOTICE 'amakuru_app role not created (insufficient privilege); USE_APP_ROLE=false';
              WHEN OTHERS THEN
                RAISE NOTICE 'amakuru_app role not created: %', SQLERRM;
            END;
          END IF;
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
            BEGIN
              ALTER ROLE amakuru_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            EXCEPTION
              WHEN insufficient_privilege THEN
                RAISE NOTICE 'skipping ALTER ROLE amakuru_app';
              WHEN OTHERS THEN
                RAISE NOTICE 'skipping ALTER ROLE amakuru_app: %', SQLERRM;
            END;
            BEGIN
              EXECUTE format('GRANT amakuru_app TO %I', current_user);
            EXCEPTION
              WHEN OTHERS THEN
                RAISE NOTICE 'skipping GRANT amakuru_app TO current_user: %', SQLERRM;
            END;
          END IF;
        END
        $$;
        """
    )

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("branding", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("default_language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("plan", sa.String(32), nullable=False, server_default="starter"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("residency_mode", sa.String(32), nullable=False, server_default="hosted"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("demo_label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("totp_secret_encrypted", sa.String(512), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "role", name="uq_membership"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False),
        sa.Column("csrf_token", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_refresh_token_hash", "sessions", ["refresh_token_hash"], unique=True)

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])

    # Append-only: revoke UPDATE/DELETE from application role later via grants.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION amakuru_forbid_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION amakuru_forbid_audit_mutation();
        """
    )

    # Row Level Security on tenant-scoped tables.
    # tenants: visible when id matches app.tenant_id, or when app.tenant_id is empty
    # (platform/admin path using owner role). App role always needs tenant set.
    for table in ("tenants", "memberships"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY tenants_isolation ON tenants
        FOR ALL
        USING (
          current_setting('app.tenant_id', true) IS NULL
          OR current_setting('app.tenant_id', true) = ''
          OR id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
          current_setting('app.tenant_id', true) IS NULL
          OR current_setting('app.tenant_id', true) = ''
          OR id::text = current_setting('app.tenant_id', true)
        );
        """
    )
    op.execute(
        """
        CREATE POLICY memberships_isolation ON memberships
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
    op.execute(
        """
        CREATE POLICY audit_log_isolation ON audit_log
        FOR SELECT
        USING (
          tenant_id IS NULL
          OR current_setting('app.tenant_id', true) IS NULL
          OR current_setting('app.tenant_id', true) = ''
          OR tenant_id::text = current_setting('app.tenant_id', true)
        );
        """
    )
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_log_insert ON audit_log
        FOR INSERT
        WITH CHECK (true);
        """
    )

    # Grants for application role (no-op when role was not created).
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
            GRANT USAGE ON SCHEMA public TO amakuru_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE tenants, users, memberships, sessions TO amakuru_app;
            GRANT SELECT, INSERT ON TABLE audit_log TO amakuru_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO amakuru_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS amakuru_forbid_audit_mutation")
    op.drop_table("audit_log")
    op.drop_table("sessions")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
