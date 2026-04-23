"""add_decision_forward_returns_table

Revision ID: f91b8c3d2a74
Revises: e7a9c2d4f6b8
Create Date: 2026-04-23 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f91b8c3d2a74"
down_revision: Union[str, Sequence[str], None] = "e7a9c2d4f6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_forward_returns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_event_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("horizon", sa.String(length=20), nullable=False),
        sa.Column("target_at", sa.DateTime(), nullable=False),
        sa.Column("reference_price", sa.Float(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("return_pct", sa.Float(), nullable=True),
        sa.Column("label_status", sa.String(length=30), nullable=False),
        sa.Column("price_source", sa.String(length=40), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["decision_event_id"], ["decision_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_event_id", "horizon", name="uq_decision_forward_return_horizon"),
    )
    with op.batch_alter_table("decision_forward_returns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_decision_forward_returns_decision_event_id"),
            ["decision_event_id"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_decision_forward_returns_symbol"), ["symbol"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_forward_returns_horizon"), ["horizon"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_forward_returns_target_at"), ["target_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_decision_forward_returns_label_status"),
            ["label_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("decision_forward_returns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_decision_forward_returns_label_status"))
        batch_op.drop_index(batch_op.f("ix_decision_forward_returns_target_at"))
        batch_op.drop_index(batch_op.f("ix_decision_forward_returns_horizon"))
        batch_op.drop_index(batch_op.f("ix_decision_forward_returns_symbol"))
        batch_op.drop_index(batch_op.f("ix_decision_forward_returns_decision_event_id"))
    op.drop_table("decision_forward_returns")
