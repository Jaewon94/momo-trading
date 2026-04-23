"""add_decision_events_table

Revision ID: e7a9c2d4f6b8
Revises: d204f5a8b1c7, b2c3d4e5f6g7
Create Date: 2026-04-23 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a9c2d4f6b8"
down_revision: Union[str, Sequence[str], None] = ("d204f5a8b1c7", "b2c3d4e5f6g7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("decision_stage", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("strategy_type", sa.String(length=40), nullable=True),
        sa.Column("scanner_score", sa.Float(), nullable=True),
        sa.Column("tier1_decision", sa.String(length=20), nullable=True),
        sa.Column("tier2_decision", sa.String(length=20), nullable=True),
        sa.Column("risk_gate_result", sa.String(length=30), nullable=True),
        sa.Column("final_action", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reference_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("decision_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_decision_events_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_symbol"), ["symbol"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_decision_stage"), ["decision_stage"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_source"), ["source"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_strategy_type"), ["strategy_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_risk_gate_result"), ["risk_gate_result"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_final_action"), ["final_action"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_provider"), ["provider"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_decision_events_created_at"), ["created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("decision_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_decision_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_decision_events_status"))
        batch_op.drop_index(batch_op.f("ix_decision_events_provider"))
        batch_op.drop_index(batch_op.f("ix_decision_events_final_action"))
        batch_op.drop_index(batch_op.f("ix_decision_events_risk_gate_result"))
        batch_op.drop_index(batch_op.f("ix_decision_events_strategy_type"))
        batch_op.drop_index(batch_op.f("ix_decision_events_source"))
        batch_op.drop_index(batch_op.f("ix_decision_events_decision_stage"))
        batch_op.drop_index(batch_op.f("ix_decision_events_symbol"))
        batch_op.drop_index(batch_op.f("ix_decision_events_cycle_id"))
    op.drop_table("decision_events")
