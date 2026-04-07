"""add_observability_rollup_tables

Revision ID: 8c9a5f2e1b44
Revises: 4f2d6d7b9c10, f04b7f2d9f11
Create Date: 2026-04-08 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c9a5f2e1b44"
down_revision: Union[str, Sequence[str], None] = ("4f2d6d7b9c10", "f04b7f2d9f11")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_metric_hourly_rollups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("partial_error_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("item_total", sa.Integer(), nullable=False),
        sa.Column("success_total", sa.Integer(), nullable=False),
        sa.Column("error_total", sa.Integer(), nullable=False),
        sa.Column("retry_total", sa.Integer(), nullable=False),
        sa.Column("avg_elapsed_ms", sa.Float(), nullable=True),
        sa.Column("p95_elapsed_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_start",
            "metric_type",
            "metric_name",
            "provider",
            "model",
            name="uq_execution_metric_hourly_rollups_bucket_dimensions",
        ),
    )
    with op.batch_alter_table("execution_metric_hourly_rollups", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_execution_metric_hourly_rollups_bucket_start"), ["bucket_start"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metric_hourly_rollups_metric_type"), ["metric_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metric_hourly_rollups_metric_name"), ["metric_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metric_hourly_rollups_provider"), ["provider"], unique=False)

    op.create_table(
        "resource_hourly_rollups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("host", sa.String(length=120), nullable=False),
        sa.Column("app_name", sa.String(length=80), nullable=True),
        sa.Column("environment", sa.String(length=30), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("avg_cpu_load_ratio_1m", sa.Float(), nullable=True),
        sa.Column("peak_cpu_load_ratio_1m", sa.Float(), nullable=True),
        sa.Column("avg_memory_percent", sa.Float(), nullable=True),
        sa.Column("peak_memory_percent", sa.Float(), nullable=True),
        sa.Column("avg_app_rss_mb", sa.Float(), nullable=True),
        sa.Column("peak_app_rss_mb", sa.Float(), nullable=True),
        sa.Column("avg_ollama_rss_mb", sa.Float(), nullable=True),
        sa.Column("peak_ollama_rss_mb", sa.Float(), nullable=True),
        sa.Column("avg_disk_used_percent", sa.Float(), nullable=True),
        sa.Column("peak_disk_used_percent", sa.Float(), nullable=True),
        sa.Column("ollama_running_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_start",
            "scope",
            "host",
            "environment",
            name="uq_resource_hourly_rollups_bucket_scope_host_env",
        ),
    )
    with op.batch_alter_table("resource_hourly_rollups", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_resource_hourly_rollups_bucket_start"), ["bucket_start"], unique=False)
        batch_op.create_index(batch_op.f("ix_resource_hourly_rollups_scope"), ["scope"], unique=False)
        batch_op.create_index(batch_op.f("ix_resource_hourly_rollups_host"), ["host"], unique=False)
        batch_op.create_index(batch_op.f("ix_resource_hourly_rollups_environment"), ["environment"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("resource_hourly_rollups", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_resource_hourly_rollups_environment"))
        batch_op.drop_index(batch_op.f("ix_resource_hourly_rollups_host"))
        batch_op.drop_index(batch_op.f("ix_resource_hourly_rollups_scope"))
        batch_op.drop_index(batch_op.f("ix_resource_hourly_rollups_bucket_start"))
    op.drop_table("resource_hourly_rollups")

    with op.batch_alter_table("execution_metric_hourly_rollups", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_execution_metric_hourly_rollups_provider"))
        batch_op.drop_index(batch_op.f("ix_execution_metric_hourly_rollups_metric_name"))
        batch_op.drop_index(batch_op.f("ix_execution_metric_hourly_rollups_metric_type"))
        batch_op.drop_index(batch_op.f("ix_execution_metric_hourly_rollups_bucket_start"))
    op.drop_table("execution_metric_hourly_rollups")
