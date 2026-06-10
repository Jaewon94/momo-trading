from datetime import datetime, timedelta
from types import SimpleNamespace

from strategy.position_exit_policy import (
    PARTIAL_STOP_LOSS_MARKER,
    min_hold_minutes_for_profit_exit,
    min_hold_minutes_for_review_exit,
    min_hold_minutes_for_soft_stop_exit,
    soft_loss_stop_min_hold_block_reason,
    staged_stop_loss_exit_decision,
    strategic_exit_min_hold_block_reason,
)
from strategy.trade_horizon import TradeHorizon


def test_default_min_hold_guards_match_horizon_contract() -> None:
    settings = SimpleNamespace()

    assert min_hold_minutes_for_profit_exit(settings, TradeHorizon.SHORT) == 15
    assert min_hold_minutes_for_review_exit(settings, TradeHorizon.SHORT) == 15
    assert min_hold_minutes_for_soft_stop_exit(settings, TradeHorizon.SHORT) == 5

    assert min_hold_minutes_for_profit_exit(settings, TradeHorizon.MID) == 1440
    assert min_hold_minutes_for_review_exit(settings, TradeHorizon.MID) == 1440
    assert min_hold_minutes_for_soft_stop_exit(settings, TradeHorizon.MID) == 1440

    assert min_hold_minutes_for_profit_exit(settings, TradeHorizon.LONG) == 2880
    assert min_hold_minutes_for_review_exit(settings, TradeHorizon.LONG) == 2880
    assert min_hold_minutes_for_soft_stop_exit(settings, TradeHorizon.LONG) == 2880


def test_mid_profit_exit_blocks_before_one_day_by_default() -> None:
    observed_at = datetime(2026, 6, 10, 10, 0)
    trade_result = SimpleNamespace(
        notes='{"trade_horizon":"MID"}',
        strategy_type="STABLE_SHORT",
        entry_at=observed_at - timedelta(hours=4),
    )

    reason = strategic_exit_min_hold_block_reason(
        trade_result,
        settings=SimpleNamespace(),
        exit_scope="profit",
        observed_at=observed_at,
    )

    assert reason is not None
    assert "MID 최소 보유 1440분" in reason


def test_long_soft_stop_blocks_before_two_days_but_allows_hard_stop() -> None:
    observed_at = datetime(2026, 6, 10, 10, 0)
    trade_result = SimpleNamespace(
        notes='{"trade_horizon":"LONG"}',
        strategy_type="STABLE_SHORT",
        entry_at=observed_at - timedelta(hours=30),
    )

    blocked = soft_loss_stop_min_hold_block_reason(
        trade_result,
        settings=SimpleNamespace(),
        pnl_rate=-4.5,
        default_stop_loss_pct=-10.0,
        observed_at=observed_at,
    )
    hard_stop = soft_loss_stop_min_hold_block_reason(
        trade_result,
        settings=SimpleNamespace(),
        pnl_rate=-10.2,
        default_stop_loss_pct=-10.0,
        observed_at=observed_at,
    )

    assert blocked is not None
    assert "LONG 최소 보유 2880분" in blocked
    assert hard_stop is None


def test_mid_default_stop_uses_partial_risk_reduction_before_deep_breach() -> None:
    trade_result = SimpleNamespace(notes='{"trade_horizon":"MID"}', strategy_type="STABLE_SHORT")

    decision = staged_stop_loss_exit_decision(
        settings=SimpleNamespace(),
        tr=trade_result,
        horizon=TradeHorizon.MID,
        pnl_rate=-7.4,
        holding_quantity=10,
        default_stop_loss_pct=-7.0,
    )

    assert decision.action == "partial"
    assert decision.quantity == 5
    assert "1차 손실축소" in decision.reason


def test_mid_partial_stop_marker_blocks_second_shallow_full_exit() -> None:
    trade_result = SimpleNamespace(
        notes=f'{{"trade_horizon":"MID"}} | {PARTIAL_STOP_LOSS_MARKER}',
        strategy_type="STABLE_SHORT",
    )

    decision = staged_stop_loss_exit_decision(
        settings=SimpleNamespace(),
        tr=trade_result,
        horizon=TradeHorizon.MID,
        pnl_rate=-7.4,
        holding_quantity=5,
        default_stop_loss_pct=-7.0,
    )

    assert decision.action == "hold"
    assert "1차 손실축소 완료" in decision.reason


def test_long_deep_stop_breach_still_allows_full_exit() -> None:
    trade_result = SimpleNamespace(notes='{"trade_horizon":"LONG"}', strategy_type="STABLE_SHORT")

    decision = staged_stop_loss_exit_decision(
        settings=SimpleNamespace(),
        tr=trade_result,
        horizon=TradeHorizon.LONG,
        pnl_rate=-14.2,
        holding_quantity=10,
        default_stop_loss_pct=-10.0,
    )

    assert decision.action == "full"
    assert "깊게 이탈" in decision.reason
