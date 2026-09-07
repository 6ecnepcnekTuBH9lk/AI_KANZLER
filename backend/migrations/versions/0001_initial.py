"""Initial platform schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "files",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("role", sa.String()),
        sa.Column("path", sa.String(), nullable=False),
    )
    op.create_index("ix_files_sha256", "files", ["sha256"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("file_ids", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON()),
        sa.Column("result", sa.JSON()),
        sa.Column("output_path", sa.String()),
        sa.Column("output_name", sa.String()),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_table(
        "analysis_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    for column in ("job_id", "section", "item_key"):
        op.create_index(f"ix_analysis_rows_{column}", "analysis_rows", [column])
    op.create_table(
        "merchandise_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("article", sa.String(), nullable=False),
        sa.Column("week_start", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float()),
    )
    for column in ("job_id", "article"):
        op.create_index(f"ix_merchandise_weekly_{column}", "merchandise_weekly", [column])
    op.create_table(
        "tnved_cache",
        sa.Column("signature", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )


def downgrade():
    for table in ("tnved_cache", "merchandise_weekly", "analysis_rows", "app_settings", "jobs", "files"):
        op.drop_table(table)
