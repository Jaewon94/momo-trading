import asyncio

import pytest

from agent.decision_maker import DecisionMaker
from core.events import EventType
from strategy.signal import TradeSignal
from trading.enums import Market, OrderSide, OrderType, SignalAction
from trading.models import OrderRequest, OrderResult, OrderStatusInfo


class FakeBrokerAdapter:
    def __init__(self, result: OrderResult) -> None:
        self.result = result
        self.requests: list[OrderRequest] = []
        self.order_status: OrderStatusInfo | None = None
        self.queried_order_ids: list[str] = []
        self.cache_invalidated = False

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return self.result

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        self.queried_order_ids.append(order_id)
        return self.order_status

    def invalidate_cache(self) -> None:
        self.cache_invalidated = True


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


@pytest.mark.asyncio
async def test_decision_maker_confirms_fill_via_broker_adapter(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-2", message="주문 접수")
    )
    adapter.order_status = OrderStatusInfo(
        order_id="ORD-2",
        symbol="005930",
        filled_qty=3,
        filled_price=70_500,
        remaining_qty=0,
        order_price=70_500,
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    recorded: dict = {}

    async def fake_sleep(_: float) -> None:
        return None

    async def fake_record_trade_result(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.decision_maker.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(decision_maker, "_record_trade_result", fake_record_trade_result)

    await decision_maker.confirm_and_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-2",
        quantity=3,
        expected_price=70_000,
        analysis_context={"stock_name": "삼성전자"},
        cycle_id="cycle-3",
    )

    assert adapter.queried_order_ids == ["ORD-2"]
    assert adapter.cache_invalidated is True
    assert recorded["filled_qty"] == 3
    assert recorded["filled_price"] == 70_500
    assert recorded["symbol"] == "005930"


@pytest.mark.asyncio
async def test_decision_maker_cancels_when_order_status_is_missing(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-3", message="주문 접수")
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    cancelled: list[tuple[str, str]] = []
    settled: list[tuple[str, bool]] = []

    async def fake_sleep(_: float) -> None:
        return None

    async def fake_cancel(order_id: str, symbol: str) -> None:
        cancelled.append((order_id, symbol))

    async def fake_on_settled(order_id: str, success: bool) -> None:
        settled.append((order_id, success))

    monkeypatch.setattr("agent.decision_maker.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(decision_maker, "_cancel_unfilled_order", fake_cancel)

    await decision_maker.confirm_and_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-3",
        quantity=1,
        expected_price=71_000,
        on_settled=fake_on_settled,
    )

    assert adapter.queried_order_ids == ["ORD-3"]
    assert cancelled == [("ORD-3", "005930")]
    assert settled == [("ORD-3", False)]
    assert adapter.cache_invalidated is False


@pytest.mark.asyncio
async def test_decision_maker_cancels_when_filled_quantity_is_zero(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-4", message="주문 접수")
    )
    adapter.order_status = OrderStatusInfo(
        order_id="ORD-4",
        symbol="005930",
        filled_qty=0,
        filled_price=0,
        remaining_qty=2,
        order_price=71_000,
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    cancelled: list[tuple[str, str]] = []
    settled: list[tuple[str, bool]] = []

    async def fake_sleep(_: float) -> None:
        return None

    async def fake_cancel(order_id: str, symbol: str) -> None:
        cancelled.append((order_id, symbol))

    async def fake_on_settled(order_id: str, success: bool) -> None:
        settled.append((order_id, success))

    monkeypatch.setattr("agent.decision_maker.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(decision_maker, "_cancel_unfilled_order", fake_cancel)

    await decision_maker.confirm_and_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-4",
        quantity=2,
        expected_price=71_000,
        on_settled=fake_on_settled,
    )

    assert adapter.queried_order_ids == ["ORD-4"]
    assert cancelled == [("ORD-4", "005930")]
    assert settled == [("ORD-4", False)]
    assert adapter.cache_invalidated is False
