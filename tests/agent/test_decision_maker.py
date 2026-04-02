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


def build_signal(
    *,
    action: SignalAction = SignalAction.BUY,
    quantity: int | None = 2,
    price: float | None = 71_000,
    metadata: dict | None = None,
) -> TradeSignal:
    return TradeSignal(
        symbol="005930",
        stock_id="005930",
        action=action,
        strength=0.9,
        suggested_price=price,
        suggested_quantity=quantity,
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_decision_maker_execute_routes_to_autonomous_mode(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    decision_maker = DecisionMaker(broker_adapter=adapter)
    observed: dict = {}

    async def fake_execute_autonomous(signal, cycle_id=None, analysis_context=None, on_settled=None):
        observed["symbol"] = signal.symbol
        observed["cycle_id"] = cycle_id
        observed["analysis_context"] = analysis_context
        observed["has_on_settled"] = on_settled is not None
        return {"mode": "AUTONOMOUS"}

    monkeypatch.setattr("agent.decision_maker.settings.AUTONOMY_MODE", "AUTONOMOUS")
    monkeypatch.setattr(decision_maker, "_execute_autonomous", fake_execute_autonomous)

    result = await decision_maker.execute(
        build_signal(),
        cycle_id="cycle-auto",
        analysis_context={"source": "test"},
        on_settled=lambda *_args: None,
    )

    assert result == {"mode": "AUTONOMOUS"}
    assert observed == {
        "symbol": "005930",
        "cycle_id": "cycle-auto",
        "analysis_context": {"source": "test"},
        "has_on_settled": True,
    }


@pytest.mark.asyncio
async def test_decision_maker_execute_routes_to_recommendation_in_semi_auto(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    decision_maker = DecisionMaker(broker_adapter=adapter)
    observed: dict = {}

    async def fake_create_recommendation(signal, analysis_id, cycle_id=None):
        observed["symbol"] = signal.symbol
        observed["analysis_id"] = analysis_id
        observed["cycle_id"] = cycle_id
        return {"mode": "SEMI_AUTO"}

    monkeypatch.setattr("agent.decision_maker.settings.AUTONOMY_MODE", "SEMI_AUTO")
    monkeypatch.setattr(decision_maker, "_create_recommendation", fake_create_recommendation)

    result = await decision_maker.execute(
        build_signal(),
        analysis_id="analysis-1",
        cycle_id="cycle-semi",
    )

    assert result == {"mode": "SEMI_AUTO"}
    assert observed == {
        "symbol": "005930",
        "analysis_id": "analysis-1",
        "cycle_id": "cycle-semi",
    }


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
async def test_decision_maker_rejects_non_positive_quantity_without_broker_call(monkeypatch) -> None:
    events = []
    logs = []
    adapter = FakeBrokerAdapter(
        OrderResult(
            success=True,
            order_id="ORD-ZERO",
            message="주문 접수",
        )
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)

    result = await decision_maker._execute_autonomous(
        build_signal(quantity=0),
        cycle_id="cycle-zero",
    )

    assert result["success"] is False
    assert result["message"] == "주문 수량이 유효하지 않습니다"
    assert result["order_id"] == ""
    assert adapter.requests == []
    assert events[0].data["success"] is False
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
async def test_decision_maker_treats_empty_order_id_as_non_submitted(monkeypatch) -> None:
    events = []
    logs = []
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="", message="주문 접수 응답")
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    pending_created = False
    confirm_called = False

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    async def fake_create_pending_record(**kwargs):
        nonlocal pending_created
        pending_created = True
        return 1

    async def fake_confirm_and_record(**kwargs):
        nonlocal confirm_called
        confirm_called = True

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)
    monkeypatch.setattr(decision_maker, "_create_pending_record", fake_create_pending_record)
    monkeypatch.setattr(decision_maker, "confirm_and_record", fake_confirm_and_record)

    result = await decision_maker._execute_autonomous(
        build_signal(),
        cycle_id="cycle-empty-order-id",
    )

    assert result["success"] is False
    assert result["order_id"] == ""
    assert result["message"] == "주문 접수 응답"
    assert pending_created is False
    assert confirm_called is False
    assert events[0].data["success"] is False
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
