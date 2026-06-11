import json
from types import SimpleNamespace

from services.holdings_precheck_service import HoldingsPrecheckService
from strategy.holding_policy import (
    _get_max_hold_days_for_trade,
    apply_hold_extension_decision,
    plan_hold_extension,
)


def test_holdings_precheck_service_keeps_llm_for_loss_sell_reason() -> None:
    service = HoldingsPrecheckService()
    holding = SimpleNamespace(symbol="005930", avg_buy_price=100_000)
    trade_result = SimpleNamespace(
        strategy_type="STABLE_SHORT",
        ai_confidence=0.7,
        ai_target_price=0,
        entry_at=None,
        created_at=None,
    )
    settings = SimpleNamespace(MAX_HOLD_DAYS_STABLE=5, MAX_HOLD_DAYS_AGGRESSIVE=3)

    # horizon notes가 없는 STABLE_SHORT는 MID로 추론되어 -7% 임계값이 적용된다.
    decision = service.evaluate(
        holding=holding,
        trade_result=trade_result,
        current_price=92_000,
        settings=settings,
    )

    assert decision.should_skip_llm is False
    assert decision.action == "SELL"
    assert "손실 과대" in decision.reason


def test_holdings_precheck_service_skips_llm_for_missing_trade_result() -> None:
    service = HoldingsPrecheckService()
    holding = SimpleNamespace(symbol="005930", avg_buy_price=100_000)
    settings = SimpleNamespace(MAX_HOLD_DAYS_STABLE=5, MAX_HOLD_DAYS_AGGRESSIVE=3)

    decision = service.evaluate(
        holding=holding,
        trade_result=None,
        current_price=95_000,
        settings=settings,
    )

    assert decision.should_skip_llm is True
    assert decision.action == "SELL"
    assert "TradeResult 없음" in decision.reason


def test_holdings_precheck_service_keeps_llm_for_non_clear_hold_reason() -> None:
    service = HoldingsPrecheckService()
    holding = SimpleNamespace(symbol="005930", avg_buy_price=100_000)
    trade_result = SimpleNamespace(
        strategy_type="STABLE_SHORT",
        ai_confidence=0.7,
        ai_target_price=120_000,
        entry_at=None,
        created_at=None,
    )
    settings = SimpleNamespace(MAX_HOLD_DAYS_STABLE=5, MAX_HOLD_DAYS_AGGRESSIVE=3)

    decision = service.evaluate(
        holding=holding,
        trade_result=trade_result,
        current_price=101_000,
        settings=settings,
    )

    assert decision.should_skip_llm is False
    assert decision.action == "HOLD"


def test_holdings_precheck_service_skips_llm_for_clear_hold_when_enabled() -> None:
    service = HoldingsPrecheckService()
    holding = SimpleNamespace(symbol="005930", avg_buy_price=100_000)
    trade_result = SimpleNamespace(
        strategy_type="STABLE_SHORT",
        ai_confidence=0.72,
        ai_target_price=110_000,
        entry_at=None,
        created_at=None,
    )
    settings = SimpleNamespace(
        MAX_HOLD_DAYS_STABLE=5,
        MAX_HOLD_DAYS_AGGRESSIVE=3,
        HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED=True,
    )

    decision = service.evaluate(
        holding=holding,
        trade_result=trade_result,
        current_price=102_000,
        settings=settings,
    )

    assert decision.should_skip_llm is True
    assert decision.action == "HOLD"
    assert "명확한 HOLD" in decision.reason


def test_holdings_precheck_service_keeps_llm_for_hold_near_target() -> None:
    service = HoldingsPrecheckService()
    holding = SimpleNamespace(symbol="005930", avg_buy_price=100_000)
    trade_result = SimpleNamespace(
        strategy_type="STABLE_SHORT",
        ai_confidence=0.72,
        ai_target_price=102_500,
        entry_at=None,
        created_at=None,
    )
    settings = SimpleNamespace(
        MAX_HOLD_DAYS_STABLE=5,
        MAX_HOLD_DAYS_AGGRESSIVE=3,
        HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED=True,
    )

    decision = service.evaluate(
        holding=holding,
        trade_result=trade_result,
        current_price=102_000,
        settings=settings,
    )

    assert decision.should_skip_llm is False
    assert decision.action == "HOLD"


def test_holding_policy_uses_trade_horizon_for_max_hold_days() -> None:
    settings = SimpleNamespace(
        MAX_HOLD_DAYS_SHORT=5,
        MAX_HOLD_DAYS_MID=15,
        MAX_HOLD_DAYS_LONG=30,
        MAX_HOLD_DAYS_STABLE=15,
        MAX_HOLD_DAYS_AGGRESSIVE=10,
    )

    long_trade = SimpleNamespace(
        strategy_type="AGGRESSIVE_SHORT",
        notes='{"trade_horizon":"LONG"}',
    )
    missing_horizon = SimpleNamespace(
        strategy_type="AGGRESSIVE_SHORT",
        notes="",
    )

    assert _get_max_hold_days_for_trade(long_trade, settings) == 30
    assert _get_max_hold_days_for_trade(missing_horizon, settings) == 10


def test_hold_extension_promotes_mid_to_long_and_preserves_note_marker() -> None:
    settings = SimpleNamespace(
        MAX_HOLD_DAYS_SHORT=5,
        MAX_HOLD_DAYS_MID=15,
        MAX_HOLD_DAYS_LONG=30,
        MAX_HOLD_EXTENSION_DAYS=15,
        MAX_HOLD_TOTAL_DAYS=60,
        MAX_HOLD_DAYS_STABLE=15,
        MAX_HOLD_DAYS_AGGRESSIVE=10,
    )
    trade_result = SimpleNamespace(
        strategy_type="STABLE_SHORT",
        notes='{"trade_horizon":"MID","active_trailing_stop_pct":4.5} | PARTIAL_TAKE_PROFIT_DONE',
    )

    update = apply_hold_extension_decision(
        trade_result,
        decision={"reason": "추세와 목표가 여유 유지", "confidence": 0.81},
        hold_days=15,
        config=settings,
        source="LLM",
    )

    assert update is not None
    assert update.current_horizon == "MID"
    assert update.next_horizon == "LONG"
    assert update.extension_until_days == 30
    assert "PARTIAL_TAKE_PROFIT_DONE" in update.updated_notes

    payload, end_index = json.JSONDecoder().raw_decode(update.updated_notes)
    assert update.updated_notes[end_index:].strip() == "| PARTIAL_TAKE_PROFIT_DONE"
    assert payload["trade_horizon"] == "LONG"
    assert payload["active_trailing_stop_pct"] == 4.5
    assert payload["hold_extension_count"] == 1

    trade_result.notes = update.updated_notes
    assert _get_max_hold_days_for_trade(trade_result, settings) == 30


def test_hold_extension_extends_long_in_review_windows_until_total_cap() -> None:
    settings = SimpleNamespace(
        MAX_HOLD_DAYS_SHORT=5,
        MAX_HOLD_DAYS_MID=15,
        MAX_HOLD_DAYS_LONG=30,
        MAX_HOLD_EXTENSION_DAYS=15,
        MAX_HOLD_TOTAL_DAYS=60,
        MAX_HOLD_DAYS_STABLE=15,
        MAX_HOLD_DAYS_AGGRESSIVE=10,
    )
    trade_result = SimpleNamespace(strategy_type="STABLE_SHORT", notes='{"trade_horizon":"LONG"}')

    first = apply_hold_extension_decision(
        trade_result,
        decision={"reason": "장기 추세 유지", "confidence": 0.77},
        hold_days=30,
        config=settings,
    )
    assert first is not None
    assert first.extension_until_days == 45
    trade_result.notes = first.updated_notes
    assert _get_max_hold_days_for_trade(trade_result, settings) == 45

    second = apply_hold_extension_decision(
        trade_result,
        decision={"reason": "목표가 여유 유지", "confidence": 0.74},
        hold_days=45,
        config=settings,
    )
    assert second is not None
    assert second.extension_until_days == 60
    trade_result.notes = second.updated_notes

    cap_plan = plan_hold_extension(trade_result, settings, hold_days=60)
    assert cap_plan.should_record is True
    assert cap_plan.can_extend is False
    assert "총 보유 상한 60일" in cap_plan.reason
