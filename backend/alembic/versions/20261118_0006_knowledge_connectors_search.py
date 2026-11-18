"""Live search events + connector intelligence.

Revision ID: 20261118_0006
Revises: 20261112_0005
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261118_0006"
down_revision: str | None = "20261112_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "search_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.String(2000), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("channel", sa.String(32), nullable=False, server_default="widget"),
        sa.Column("decision", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "last_asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "normalized_question", name="uq_search_events_tenant_norm"
        ),
    )
    op.create_index("ix_search_events_tenant_id", "search_events", ["tenant_id"])
    op.create_index("ix_search_events_count", "search_events", ["tenant_id", "count"])
    _rls("search_events")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON search_events TO amakuru_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS search_events_isolation ON search_events")
    op.drop_table("search_events")
