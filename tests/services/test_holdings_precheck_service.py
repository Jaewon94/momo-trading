from types import SimpleNamespace

from services.holdings_precheck_service import HoldingsPrecheckService


def test_holdings_precheck_service_skips_llm_for_clear_sell_reason() -> None:
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

    assert decision.should_skip_llm is True
    assert decision.action == "SELL"
    assert "손실 과대" in decision.reason


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
