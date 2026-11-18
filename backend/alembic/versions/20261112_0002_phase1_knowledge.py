"""Phase 1 knowledge: offices, entries, versions, import/connectors, RLS.

Revision ID: 20261112_0002
Revises: 20261112_0001
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261112_0002"
down_revision: str | None = "20261112_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "offices",
    "answer_entries",
    "answer_versions",
    "question_variants",
    "sources",
    "needs_answer_queue",
    "ingestion_jobs",
    "connectors",
)


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
        "offices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("contact_person", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("opening_hours", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_offices_tenant_id", "offices", ["tenant_id"])

    op.drop_constraint("uq_membership", "memberships", type_="unique")
    op.add_column(
        "memberships",
        sa.Column(
            "office_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("offices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_memberships_office_id", "memberships", ["office_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_membership_office
        ON memberships (tenant_id, user_id, role, office_id)
        NULLS NOT DISTINCT
        """
    )

    op.create_table(
        "answer_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "office_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("offices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category", sa.String(128), nullable=False, server_default=""),
        sa.Column("subcategory", sa.String(128), nullable=False, server_default=""),
        sa.Column("verbatim_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "escalate_to_human", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "applicability",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("season", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_answer_entries_tenant_id", "answer_entries", ["tenant_id"])
    op.create_index("ix_answer_entries_office_id", "answer_entries", ["office_id"])

    op.create_table(
        "answer_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answer_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("source_document", sa.Text(), nullable=True),
        sa.Column("last_verified", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column(
            "editor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approver_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_30_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_14_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_3_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("entry_id", "version_number", name="uq_answer_version_number"),
    )
    op.create_index("ix_answer_versions_tenant_id", "answer_versions", ["tenant_id"])
    op.create_index("ix_answer_versions_entry_id", "answer_versions", ["entry_id"])
    op.create_index("ix_answer_versions_status", "answer_versions", ["status"])

    op.create_table(
        "question_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answer_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("asker_type", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column("collector", sa.String(255), nullable=True),
        sa.Column("date_collected", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_question_variants_tenant_id", "question_variants", ["tenant_id"])
    op.create_index("ix_question_variants_entry_id", "question_variants", ["entry_id"])

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="upload"),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"])

    op.create_table(
        "needs_answer_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "office_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("offices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_raw", sa.Text(), nullable=False),
        sa.Column("category", sa.String(128), nullable=True),
        sa.Column("subcategory", sa.String(128), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_needs_answer_queue_tenant_id", "needs_answer_queue", ["tenant_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "mapping", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "stats", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_tenant_id", "ingestion_jobs", ["tenant_id"])

    op.create_table(
        "connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("adapter_type", sa.String(64), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "field_mapping",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_connectors_tenant_id", "connectors", ["tenant_id"])

    for table in TENANT_TABLES:
        _rls(table)

    grant_tables = ", ".join(TENANT_TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {grant_tables} TO amakuru_app;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.drop_table(table)
    op.execute("DROP INDEX IF EXISTS uq_membership_office")
    op.drop_index("ix_memberships_office_id", table_name="memberships")
    op.drop_column("memberships", "office_id")
    op.create_unique_constraint(
        "uq_membership", "memberships", ["tenant_id", "user_id", "role"]
    )
