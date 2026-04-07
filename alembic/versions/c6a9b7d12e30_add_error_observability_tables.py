"""add_error_observability_tables

Revision ID: c6a9b7d12e30
Revises: 8c9a5f2e1b44
Create Date: 2026-04-08 01:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6a9b7d12e30"
down_revision: Union[str, Sequence[str], None] = "8c9a5f2e1b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("handled", sa.Boolean(), nullable=False),
        sa.Column("exception_type", sa.String(length=120), nullable=True),
        sa.Column("exception_message", sa.Text(), nullable=True),
        sa.Column("stacktrace", sa.Text(), nullable=True),
        sa.Column("cycle_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("count_hint", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("error_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_error_events_fingerprint"), ["fingerprint"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_severity"), ["severity"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_component"), ["component"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_operation"), ["operation"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_exception_type"), ["exception_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_symbol"), ["symbol"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_events_provider"), ["provider"], unique=False)

    op.create_table(
        "error_incidents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("exception_type", sa.String(length=120), nullable=True),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column("last_symbol", sa.String(length=20), nullable=True),
        sa.Column("last_provider", sa.String(length=30), nullable=True),
        sa.Column("owner_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    with op.batch_alter_table("error_incidents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_error_incidents_fingerprint"), ["fingerprint"], unique=True)
        batch_op.create_index(batch_op.f("ix_error_incidents_component"), ["component"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_incidents_operation"), ["operation"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_incidents_severity"), ["severity"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_incidents_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_incidents_last_seen_at"), ["last_seen_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_error_incidents_exception_type"), ["exception_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("error_incidents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_error_incidents_exception_type"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_last_seen_at"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_status"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_severity"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_operation"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_component"))
        batch_op.drop_index(batch_op.f("ix_error_incidents_fingerprint"))
    op.drop_table("error_incidents")

    with op.batch_alter_table("error_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_error_events_provider"))
        batch_op.drop_index(batch_op.f("ix_error_events_symbol"))
        batch_op.drop_index(batch_op.f("ix_error_events_cycle_id"))
        batch_op.drop_index(batch_op.f("ix_error_events_exception_type"))
        batch_op.drop_index(batch_op.f("ix_error_events_operation"))
        batch_op.drop_index(batch_op.f("ix_error_events_component"))
        batch_op.drop_index(batch_op.f("ix_error_events_severity"))
        batch_op.drop_index(batch_op.f("ix_error_events_fingerprint"))
    op.drop_table("error_events")
