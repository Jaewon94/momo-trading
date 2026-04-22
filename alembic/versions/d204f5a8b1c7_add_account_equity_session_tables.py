"""add_account_equity_session_tables

Revision ID: d204f5a8b1c7
Revises: c6a9b7d12e30
Create Date: 2026-04-09 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d204f5a8b1c7"
down_revision: Union[str, Sequence[str], None] = "c6a9b7d12e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_day_baselines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("baseline_at", sa.DateTime(), nullable=False),
        sa.Column("baseline_total_asset", sa.Float(), nullable=False),
        sa.Column("baseline_cash", sa.Float(), nullable=False),
        sa.Column("baseline_stock_value", sa.Float(), nullable=False),
        sa.Column("baseline_total_unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("baseline_holding_count", sa.Integer(), nullable=False),
        sa.Column("baseline_pending_order_count", sa.Integer(), nullable=False),
        sa.Column("baseline_source", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trading_date"),
    )
    with op.batch_alter_table("account_day_baselines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_account_day_baselines_trading_date"), ["trading_date"], unique=True)

    op.create_table(
        "account_equity_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("session_phase", sa.String(length=30), nullable=False),
        sa.Column("total_asset", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("stock_value", sa.Float(), nullable=False),
        sa.Column("total_unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("total_unrealized_pnl_rate", sa.Float(), nullable=False),
        sa.Column("holding_count", sa.Integer(), nullable=False),
        sa.Column("pending_order_count", sa.Integer(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("account_equity_snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_account_equity_snapshots_trading_date"), ["trading_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_account_equity_snapshots_captured_at"), ["captured_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_account_equity_snapshots_session_phase"), ["session_phase"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("account_equity_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_account_equity_snapshots_session_phase"))
        batch_op.drop_index(batch_op.f("ix_account_equity_snapshots_captured_at"))
        batch_op.drop_index(batch_op.f("ix_account_equity_snapshots_trading_date"))
    op.drop_table("account_equity_snapshots")

    with op.batch_alter_table("account_day_baselines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_account_day_baselines_trading_date"))
    op.drop_table("account_day_baselines")
