import asyncio

import pytest

from agent.decision_maker import DecisionMaker
from core.events import EventType
from strategy.signal import TradeSignal
from trading.enums import Market, OrderSide, OrderType, SignalAction
from trading.models import OrderRequest, OrderResult


class FakeBrokerAdapter:
    def __init__(self, result: OrderResult) -> None:
        self.result = result
        self.requests: list[OrderRequest] = []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return self.result


@pytest.mark.asyncio
async def test_decision_maker_uses_broker_adapter_for_autonomous_order(monkeypatch) -> None:
    events = []
    logs = []
    adapter = FakeBrokerAdapter(
        OrderResult(
            success=True,
            order_id="ORD-1",
            message="주문 접수",
            filled_quantity=2,
            filled_price=71_000,
        )
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    async def fake_confirm_and_record(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)
    monkeypatch.setattr(decision_maker, "confirm_and_record", fake_confirm_and_record)

    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.9,
        suggested_price=71_000,
        suggested_quantity=2,
        metadata={"market": "KOSDAQ"},
    )

    result = await decision_maker._execute_autonomous(signal, cycle_id="cycle-1")
    await asyncio.sleep(0)

    assert result["success"] is True
    assert result["order_id"] == "ORD-1"
    assert adapter.requests[0].market == Market.KOSDAQ
    assert adapter.requests[0].side == OrderSide.BUY
    assert adapter.requests[0].order_type == OrderType.LIMIT
    assert events[0].type == EventType.ORDER_EXECUTED
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_decision_maker_reports_failed_autonomous_order(monkeypatch) -> None:
    events = []
    logs = []
    adapter = FakeBrokerAdapter(
        OrderResult(success=False, message="주문 실패", order_id=None)
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)

    signal = TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=SignalAction.BUY,
        strength=0.9,
        suggested_price=71_000,
        suggested_quantity=2,
    )

    result = await decision_maker._execute_autonomous(signal, cycle_id="cycle-2")

    assert result["success"] is False
    assert "주문 실패" in result["message"]
    assert events[0].type == EventType.ORDER_EXECUTED
    assert len(logs) == 2
