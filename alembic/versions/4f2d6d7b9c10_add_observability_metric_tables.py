"""add_observability_metric_tables

Revision ID: 4f2d6d7b9c10
Revises: e6f885d3ac30
Create Date: 2026-04-07 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f2d6d7b9c10"
down_revision: Union[str, None] = "e6f885d3ac30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("execution_metrics", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_execution_metrics_metric_type"), ["metric_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metrics_metric_name"), ["metric_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metrics_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metrics_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_execution_metrics_symbol"), ["symbol"], unique=False)

    op.create_table(
        "resource_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("host", sa.String(length=120), nullable=False),
        sa.Column("app_name", sa.String(length=80), nullable=True),
        sa.Column("environment", sa.String(length=30), nullable=True),
        sa.Column("python_version", sa.String(length=40), nullable=True),
        sa.Column("platform_system", sa.String(length=40), nullable=True),
        sa.Column("platform_release", sa.String(length=60), nullable=True),
        sa.Column("platform_machine", sa.String(length=40), nullable=True),
        sa.Column("cpu_count", sa.Integer(), nullable=True),
        sa.Column("app_pid", sa.Integer(), nullable=True),
        sa.Column("cpu_load_1m", sa.Float(), nullable=True),
        sa.Column("cpu_load_5m", sa.Float(), nullable=True),
        sa.Column("cpu_load_15m", sa.Float(), nullable=True),
        sa.Column("cpu_load_ratio_1m", sa.Float(), nullable=True),
        sa.Column("cpu_load_ratio_5m", sa.Float(), nullable=True),
        sa.Column("cpu_load_ratio_15m", sa.Float(), nullable=True),
        sa.Column("process_cpu_time_sec", sa.Float(), nullable=True),
        sa.Column("total_memory_mb", sa.Float(), nullable=True),
        sa.Column("memory_used_mb", sa.Float(), nullable=True),
        sa.Column("memory_available_mb", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("swap_used_mb", sa.Float(), nullable=True),
        sa.Column("disk_total_gb", sa.Float(), nullable=True),
        sa.Column("disk_used_gb", sa.Float(), nullable=True),
        sa.Column("disk_available_gb", sa.Float(), nullable=True),
        sa.Column("disk_used_percent", sa.Float(), nullable=True),
        sa.Column("app_rss_mb", sa.Float(), nullable=True),
        sa.Column("ollama_rss_mb", sa.Float(), nullable=True),
        sa.Column("ollama_pid_count", sa.Integer(), nullable=True),
        sa.Column("ollama_running", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("resource_snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_resource_snapshots_scope"), ["scope"], unique=False)
        batch_op.create_index(batch_op.f("ix_resource_snapshots_host"), ["host"], unique=False)
        batch_op.create_index(batch_op.f("ix_resource_snapshots_environment"), ["environment"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("resource_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_resource_snapshots_host"))
        batch_op.drop_index(batch_op.f("ix_resource_snapshots_scope"))
    op.drop_table("resource_snapshots")

    with op.batch_alter_table("execution_metrics", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_execution_metrics_symbol"))
        batch_op.drop_index(batch_op.f("ix_execution_metrics_cycle_id"))
        batch_op.drop_index(batch_op.f("ix_execution_metrics_status"))
        batch_op.drop_index(batch_op.f("ix_execution_metrics_metric_name"))
        batch_op.drop_index(batch_op.f("ix_execution_metrics_metric_type"))
    op.drop_table("execution_metrics")
