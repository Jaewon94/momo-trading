from types import SimpleNamespace

import pytest

from core.order_submission import decide_order_submission
from strategy.policy.engine import TradingPolicyEngine
from strategy.policy.trace import trace_dict
from strategy.signal import TradeSignal
from trading.enums import SignalAction


def build_buy_signal() -> TradeSignal:
    return TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.8,
        confidence=0.8,
        suggested_price=100.0,
        suggested_quantity=10,
        target_price=100.3,
    )


def test_policy_engine_cost_gate_preserves_payload_and_trace(monkeypatch) -> None:
    monkeypatch.setattr("strategy.policy.engine.settings.COST_GATE_ENABLED", True)
    monkeypatch.setattr("strategy.policy.engine.settings.ESTIMATED_ENTRY_COST_BPS", 8)
    monkeypatch.setattr("strategy.policy.engine.settings.ESTIMATED_EXIT_COST_BPS", 8)
    monkeypatch.setattr("strategy.policy.engine.settings.ESTIMATED_SLIPPAGE_BPS_SHORT", 12)
    monkeypatch.setattr("strategy.policy.engine.settings.MIN_EDGE_TO_COST_RATIO_SHORT", 1.5)

    engine = TradingPolicyEngine()
    evaluation = engine.evaluate_cost_gate(
        signal=build_buy_signal(),
        current_price=100.0,
        horizon="SHORT",
    )

    assert evaluation.value["approved"] is False
    assert evaluation.value["horizon"] == "SHORT"
    assert evaluation.decision.owner == "cost_gate"
    assert evaluation.decision.reason_code == "LOW_EDGE_AFTER_COST"
    assert trace_dict(evaluation.decision)["blocked"] is True


def test_policy_engine_order_submission_uses_existing_decider(monkeypatch) -> None:
    monkeypatch.setattr("strategy.policy.engine.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("strategy.policy.engine.settings.ORDER_SUBMISSION_MODE", "SELL_ONLY")

    engine = TradingPolicyEngine(order_submission_decider=decide_order_submission)
    evaluation = engine.evaluate_order_submission("BUY")

    assert evaluation.value.allowed is False
    assert evaluation.value.mode == "SELL_ONLY"
    assert evaluation.decision.owner == "order_submission"
    assert evaluation.decision.reason_code == "SELL_ONLY"


def test_policy_engine_post_liquidation_buy_block_is_side_specific() -> None:
    engine = TradingPolicyEngine()

    buy_evaluation = engine.evaluate_post_liquidation_buy_block(
        side="BUY",
        is_blocked=lambda: True,
    )
    sell_evaluation = engine.evaluate_post_liquidation_buy_block(
        side="SELL",
        is_blocked=lambda: True,
    )

    assert buy_evaluation is not None
    assert buy_evaluation.decision.reason_code == "POST_LIQUIDATION_BUY_BLOCK"
    assert sell_evaluation is None


def test_policy_engine_exit_event_preserves_defer_trace() -> None:
    engine = TradingPolicyEngine()

    evaluation = engine.evaluate_exit_event(
        event_type="STOP_LOSS_HIT",
        blocked=True,
        exit_reason="MIN_HOLD_BLOCK",
        reason="MID 최소 보유 전 손절 보류",
    )

    trace = trace_dict(evaluation.decision)

    assert evaluation.stage == "HOLDING_EXIT"
    assert trace["blocked"] is False
    assert trace["decisions"][0]["action"] == "DEFER"
    assert trace["decisions"][0]["reason_code"] == "MIN_HOLD_BLOCK"


@pytest.mark.asyncio
async def test_policy_engine_news_gate_preserves_rollout_payload() -> None:
    class FakeRolloutService:
        async def resolve(self):
            return SimpleNamespace(
                evaluate_gate=False,
                reason="poll only",
                requested_mode="POLL_ONLY",
                effective_mode="POLL_ONLY",
                block_buy=False,
            )

    engine = TradingPolicyEngine(news_rollout_service=FakeRolloutService())
    evaluation = await engine.evaluate_news_gate(symbol="005930", horizon="MID")

    assert evaluation.value["approved"] is True
    assert evaluation.value["reason"] == "poll only"
    assert evaluation.value["news_gate_rollout"]["effective_mode"] == "POLL_ONLY"
    assert evaluation.decision.owner == "news_gate"
