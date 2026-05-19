from types import SimpleNamespace

from services.holdings_precheck_service import HoldingsPrecheckService
from strategy.holding_policy import _get_max_hold_days_for_trade


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

    decision = service.evaluate(
        holding=holding,
        trade_result=trade_result,
        current_price=95_000,
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
