"""Phase 2 retrieval: embeddings, FTS, query traces, golden/eval tables.

Revision ID: 20261112_0003
Revises: 20261112_0002
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261112_0003"
down_revision: str | None = "20261112_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "embeddings",
    "query_traces",
    "golden_questions",
    "eval_runs",
    "eval_results",
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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "answer_versions",
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
    )
    op.execute(
        """
        UPDATE answer_versions
        SET search_tsv = to_tsvector('english', coalesce(answer_text, ''))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_answer_versions_search_tsv
        ON answer_versions USING GIN (search_tsv)
        """
    )

    op.add_column(
        "question_variants",
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
    )
    op.execute(
        """
        UPDATE question_variants
        SET search_tsv = to_tsvector('english', coalesce(raw_text, ''))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_variants_search_tsv
        ON question_variants USING GIN (search_tsv)
        """
    )

    # Keep tsv in sync via triggers.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION amakuru_answer_versions_tsv()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_tsv := to_tsvector('english', coalesce(NEW.answer_text, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER answer_versions_tsv_tg
        BEFORE INSERT OR UPDATE OF answer_text ON answer_versions
        FOR EACH ROW EXECUTE FUNCTION amakuru_answer_versions_tsv();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION amakuru_question_variants_tsv()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_tsv := to_tsvector('english', coalesce(NEW.raw_text, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER question_variants_tsv_tg
        BEFORE INSERT OR UPDATE OF raw_text ON question_variants
        FOR EACH ROW EXECUTE FUNCTION amakuru_question_variants_tsv();
        """
    )

    op.execute(
        """
        CREATE TABLE embeddings (
          id UUID PRIMARY KEY,
          tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          source_type VARCHAR(32) NOT NULL,
          source_id UUID NOT NULL,
          model_id VARCHAR(128) NOT NULL,
          model_version VARCHAR(64) NOT NULL DEFAULT '1',
          dense vector(1024) NOT NULL,
          sparse_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, source_type, source_id, model_id, model_version)
        )
        """
    )
    op.create_index("ix_embeddings_tenant_id", "embeddings", ["tenant_id"])
    op.create_index("ix_embeddings_source", "embeddings", ["source_type", "source_id"])
    op.execute(
        """
        CREATE INDEX ix_embeddings_dense_hnsw
        ON embeddings USING hnsw (dense vector_cosine_ops)
        """
    )

    op.create_table(
        "query_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column(
            "steps", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "candidates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd", sa.Numeric(12, 8), nullable=False, server_default="0"
        ),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_query_traces_tenant_id", "query_traces", ["tenant_id"])

    op.create_table(
        "golden_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("expected_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expected_decision", sa.String(64), nullable=False, server_default="answer"),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_golden_questions_tenant_id", "golden_questions", ["tenant_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(64), nullable=False, server_default="manual"),
        sa.Column(
            "metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("thresholds", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_eval_runs_tenant_id", "eval_runs", ["tenant_id"])

    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "golden_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("golden_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("top_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("rank_of_expected", sa.Integer(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_index("ix_eval_results_tenant_id", "eval_results", ["tenant_id"])
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])

    for table in TENANT_TABLES:
        _rls(table)

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
        + ", ".join(TENANT_TABLES)
        + " TO amakuru_app"
    )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.drop_table(table)
    op.execute("DROP TRIGGER IF EXISTS question_variants_tsv_tg ON question_variants")
    op.execute("DROP TRIGGER IF EXISTS answer_versions_tsv_tg ON answer_versions")
    op.execute("DROP FUNCTION IF EXISTS amakuru_question_variants_tsv")
    op.execute("DROP FUNCTION IF EXISTS amakuru_answer_versions_tsv")
    op.drop_index("ix_question_variants_search_tsv", table_name="question_variants")
    op.drop_column("question_variants", "search_tsv")
    op.drop_index("ix_answer_versions_search_tsv", table_name="answer_versions")
    op.drop_column("answer_versions", "search_tsv")
