import asyncio
from types import SimpleNamespace

import pytest

from agent.decision_maker import DecisionMaker
from core.events import EventType
from strategy.signal import TradeSignal
from trading.enums import Market, OrderConfirmStatus, OrderSide, OrderType, SignalAction
from trading.models import OrderRequest, OrderResult, OrderStatusInfo, PendingOrderInfo


class FakeBrokerAdapter:
    def __init__(self, result: OrderResult) -> None:
        self.result = result
        self.requests: list[OrderRequest] = []
        self.pending_orders: list[PendingOrderInfo] = []
        self.order_status: OrderStatusInfo | None = None
        self.queried_order_ids: list[str] = []
        self.cache_invalidated = False
        self.cancelled_order_ids: list[str] = []

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return self.result

    async def get_order_status(self, order_id: str) -> OrderStatusInfo | None:
        self.queried_order_ids.append(order_id)
        return self.order_status

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return list(self.pending_orders)

    async def cancel_order(self, order_id: str, market=Market.KRX) -> OrderResult:
        self.cancelled_order_ids.append(order_id)
        return OrderResult(success=True, order_id=order_id, message="cancelled")

    def invalidate_cache(self) -> None:
        self.cache_invalidated = True


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return self

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        if self.added and getattr(self.added[-1], "id", None) is None:
            self.added[-1].id = "generated-id"


class FakeTradeResultRecord:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id")


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
async def test_decision_maker_skips_buy_when_pending_buy_exists(monkeypatch) -> None:
    events = []
    logs = []
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-PENDING-NEW", message="주문 접수")
    )
    adapter.pending_orders = [
        PendingOrderInfo(
            order_id="ORD-PENDING",
            symbol="005930",
            name="삼성전자",
            side="매수",
            order_qty=2,
            filled_qty=0,
            remaining_qty=2,
            order_price=71_000,
            order_time="100000",
        )
    ]
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)

    result = await decision_maker._execute_autonomous(
        build_signal(),
        cycle_id="cycle-pending-buy",
    )

    assert result["success"] is False
    assert result["order_id"] == ""
    assert "기존 미체결 매수 주문" in result["message"]
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


def test_decision_maker_build_order_request_falls_back_to_krx_for_invalid_market() -> None:
    request = DecisionMaker._build_order_request(
        build_signal(
            price=None,
            metadata={"market": "invalid-market"},
        )
    )

    assert request.market == Market.KRX
    assert request.order_type == OrderType.MARKET
    assert request.quantity == 2
    assert request.price is None


@pytest.mark.asyncio
async def test_decision_maker_marks_untradeable_symbol_on_rejected_order(monkeypatch) -> None:
    events = []
    logs = []
    blocked_symbols: list[str] = []
    adapter = FakeBrokerAdapter(
        OrderResult(success=False, message="매매불가 종목", order_id=None)
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.market_scanner.market_scanner.add_untradeable", blocked_symbols.append)

    result = await decision_maker._execute_autonomous(
        build_signal(),
        cycle_id="cycle-blocklist",
    )

    assert result["success"] is False
    assert blocked_symbols == ["005930"]
    assert events[0].data["message"] == "매매불가 종목"
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_decision_maker_creates_recommendation_in_semi_auto(monkeypatch) -> None:
    events = []
    logs = []
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-REC", message="ok"))
    )

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    async def fake_publish(event):
        events.append(event)

    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.decision_maker.settings.RECOMMENDATION_EXPIRE_MIN", 15)

    result = await decision_maker._create_recommendation(
        build_signal(),
        analysis_id="analysis-123",
        cycle_id="cycle-rec",
    )

    assert result["mode"] == "SEMI_AUTO"
    assert result["recommendation"]["analysis_id"] == "analysis-123"
    assert result["recommendation"]["suggested_quantity"] == 2
    assert events[0].type == EventType.RECOMMENDATION_CREATED
    assert events[0].data["symbol"] == "005930"
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_decision_maker_create_pending_record_returns_existing_id(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-P", message="ok"))
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return SimpleNamespace(id="pending-existing")

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)

    result = await decision_maker._create_pending_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-P",
        quantity=1,
        expected_price=70_000,
    )

    assert result == "pending-existing"


@pytest.mark.asyncio
async def test_decision_maker_create_pending_record_creates_trade_result(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-P2", message="ok"))
    )
    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return None

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.TradeResult", FakeTradeResultRecord)

    result = await decision_maker._create_pending_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-P2",
        quantity=3,
        expected_price=70_100,
        analysis_context={"stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"},
    )

    assert result == "generated-id"
    assert len(session.added) == 1
    added = session.added[0]
    assert added.stock_name == "삼성전자"
    assert added.quantity == 3
    assert added.status == OrderConfirmStatus.PENDING_CONFIRM.value
    assert "PENDING_CONFIRM" in added.notes


@pytest.mark.asyncio
async def test_decision_maker_cancel_unfilled_order_invokes_executor(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-CANCEL", message="ok"))
    decision_maker = DecisionMaker(broker_adapter=adapter)

    await decision_maker._cancel_unfilled_order("ORD-CANCEL", "005930")

    assert adapter.cancelled_order_ids == ["ORD-CANCEL"]


@pytest.mark.asyncio
async def test_decision_maker_mark_pending_failed_updates_status(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-F", message="ok"))
    )
    session = FakeSession()
    record = FakeTradeResultRecord(
        id="pending-failed",
        stock_symbol="005930",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
        notes=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def filter_by_one(self, **kwargs):
            return record

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)

    await decision_maker._mark_pending_failed("pending-failed", "db timeout while confirming")

    assert record.status == OrderConfirmStatus.CONFIRM_FAILED.value
    assert "db timeout while confirming" in record.notes


@pytest.mark.asyncio
async def test_decision_maker_record_trade_result_creates_buy_entry(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-BUY", message="ok"))
    )
    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return None

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.TradeResult", FakeTradeResultRecord)
    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)

    await decision_maker._record_trade_result(
        symbol="005930",
        side="BUY",
        order_id="ORD-BUY",
        filled_qty=2,
        filled_price=70_500,
        analysis_context={
            "stock_name": "삼성전자",
            "strategy_type": "STABLE_SHORT",
            "entry_pattern": "상승 추세 지속",
            "chart_signal_direction": "BULLISH",
            "chart_signal_confidence": 0.74,
            "trade_horizon": "MID",
            "estimated_edge_bps": 182.4,
            "estimated_cost_bps": 61,
            "edge_to_cost_ratio": 2.99,
            "cost_gate_ratio": 1.3,
            "news_negative_pressure": 0.22,
            "news_negative_count": 2,
            "news_source_count": 2,
            "news_threshold": 0.75,
            "news_top_contributors": [{"headline": "한글 번역 제목", "pressure": 0.11}],
        },
        cycle_id="cycle-buy",
    )

    assert len(session.added) == 1
    added = session.added[0]
    assert added.order_id == "ORD-BUY"
    assert added.side == "BUY"
    assert added.entry_price == 70_500
    assert added.quantity == 2
    assert added.entry_pattern == "상승 추세 지속"
    assert "news_top_contributors" in (added.notes or "")
    assert "edge_to_cost_ratio" in (added.notes or "")


def test_decision_maker_build_trade_notes_includes_news_metrics():
    notes = DecisionMaker._build_trade_notes({
        "trade_horizon": "MID",
        "estimated_edge_bps": 120.5,
        "estimated_cost_bps": 44.1,
        "edge_to_cost_ratio": 2.73,
        "cost_gate_ratio": 1.3,
        "news_negative_pressure": 0.35,
        "news_negative_count": 2,
        "news_source_count": 3,
        "news_threshold": 0.75,
        "news_top_contributors": [{"headline": "공급 차질 우려", "pressure": 0.12}],
        "chart_signal_direction": "BULLISH",
        "chart_signal_confidence": 0.81,
        "entry_pattern": "상승 추세 지속",
    })

    assert "news_negative_pressure" in notes
    assert "news_negative_count" in notes
    assert "edge_to_cost_ratio" in notes
    assert "news_top_contributors" in notes
    assert "chart_signal_direction" in notes
    assert "entry_pattern" in notes


@pytest.mark.asyncio
async def test_decision_maker_record_trade_result_closes_open_buys_on_sell(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-SELL", message="ok"))
    )

    open_buy_1 = FakeTradeResultRecord(
        id="buy-1",
        entry_price=70_000,
        quantity=2,
        entry_at=None,
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
    )
    open_buy_2 = FakeTradeResultRecord(
        id="buy-2",
        entry_price=71_000,
        quantity=1,
        entry_at=None,
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return None

        async def get_all_open_buys(self, _symbol: str):
            return [open_buy_1, open_buy_2]

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)

    await decision_maker._record_trade_result(
        symbol="005930",
        side="SELL",
        order_id="ORD-SELL",
        filled_qty=3,
        filled_price=73_000,
        exit_reason="SIGNAL",
        cycle_id="cycle-sell",
    )

    assert open_buy_1.exit_price == 73_000
    assert open_buy_1.pnl == 6_000
    assert open_buy_1.is_win is True
    assert open_buy_2.exit_price == 73_000
    assert open_buy_2.pnl == 2_000
    assert open_buy_2.exit_reason == "SIGNAL"


@pytest.mark.asyncio
async def test_decision_maker_record_trade_result_partially_closes_open_buy_lots(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-SELL-PART", message="ok"))
    )
    session = FakeSession()
    closed_at = __import__("datetime").datetime(2026, 4, 6, 12, 10, 0)

    open_buy_1 = FakeTradeResultRecord(
        id="buy-1",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=100.0,
        quantity=5,
        entry_at=__import__("datetime").datetime(2026, 4, 6, 9, 0, 0),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        status="CONFIRMED",
        notes=None,
    )
    open_buy_2 = FakeTradeResultRecord(
        id="buy-2",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=110.0,
        quantity=3,
        entry_at=__import__("datetime").datetime(2026, 4, 6, 9, 5, 0),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        status="CONFIRMED",
        notes=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return None

        async def get_all_open_buys(self, _symbol: str):
            return [open_buy_1, open_buy_2]

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.now_kst", lambda: closed_at)

    await decision_maker._record_trade_result(
        symbol="005930",
        side="SELL",
        order_id="ORD-SELL-PART",
        filled_qty=6,
        filled_price=120.0,
        exit_reason="SIGNAL",
        cycle_id="cycle-sell-partial",
    )

    assert open_buy_1.exit_price == 120.0
    assert open_buy_1.exit_at == closed_at
    assert open_buy_1.pnl == 100.0
    assert open_buy_2.quantity == 2
    assert open_buy_2.exit_at is None
    assert len(session.added) == 1
    partial_close = session.added[0]
    assert partial_close.quantity == 1
    assert partial_close.entry_price == 110.0
    assert partial_close.exit_price == 120.0
    assert partial_close.exit_at == closed_at
    assert partial_close.pnl == 10.0
    assert partial_close.return_pct == pytest.approx(9.09, abs=0.01)


@pytest.mark.asyncio
async def test_decision_maker_confirm_pending_record_marks_partial_exit(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-PSELL", message="ok"))
    )
    session = FakeSession()
    closed_at = __import__("datetime").datetime(2026, 4, 6, 12, 20, 0)
    pending_sell = FakeTradeResultRecord(
        id="pending-sell",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="SELL",
        strategy_type="SWING",
        quantity=8,
        entry_price=0.0,
        exit_price=119.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
        notes="PENDING_CONFIRM: 체결 확인 대기 중",
    )
    open_buy_1 = FakeTradeResultRecord(
        id="buy-1",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=100.0,
        quantity=5,
        entry_at=__import__("datetime").datetime(2026, 4, 6, 9, 0, 0),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        status="CONFIRMED",
        notes=None,
    )
    open_buy_2 = FakeTradeResultRecord(
        id="buy-2",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=110.0,
        quantity=3,
        entry_at=__import__("datetime").datetime(2026, 4, 6, 9, 5, 0),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        status="CONFIRMED",
        notes=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def filter_by_one(self, id):
            assert id == "pending-sell"
            return pending_sell

        async def get_all_open_buys(self, symbol):
            assert symbol == "005930"
            return [open_buy_1, open_buy_2]

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.now_kst", lambda: closed_at)

    await decision_maker._confirm_pending_record(
        pending_record_id="pending-sell",
        symbol="005930",
        side="SELL",
        filled_qty=6,
        filled_price=120.0,
        exit_reason="SIGNAL",
    )

    assert pending_sell.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_sell.quantity == 6
    assert pending_sell.exit_at == closed_at
    assert "PARTIAL_EXIT" in (pending_sell.notes or "")
    assert "remaining_open_quantity" in (pending_sell.notes or "")
    assert open_buy_1.exit_at == closed_at
    assert open_buy_2.quantity == 2
    assert open_buy_2.exit_at is None
    assert len(session.added) == 1


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
async def test_decision_maker_updates_pending_record_when_id_is_provided(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-PENDING", message="주문 접수")
    )
    adapter.order_status = OrderStatusInfo(
        order_id="ORD-PENDING",
        symbol="005930",
        filled_qty=1,
        filled_price=70_100,
        remaining_qty=0,
        order_price=70_100,
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    confirmed: dict = {}
    settled: list[tuple[str, bool]] = []

    async def fake_sleep(_: float) -> None:
        return None

    async def fake_confirm_pending_record(**kwargs) -> None:
        confirmed.update(kwargs)

    async def fake_on_settled(order_id: str, success: bool) -> None:
        settled.append((order_id, success))

    monkeypatch.setattr("agent.decision_maker.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(decision_maker, "_confirm_pending_record", fake_confirm_pending_record)

    await decision_maker.confirm_and_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-PENDING",
        quantity=1,
        expected_price=70_000,
        pending_record_id="pending-1",
        on_settled=fake_on_settled,
    )

    assert confirmed["pending_record_id"] == "pending-1"
    assert confirmed["filled_qty"] == 1
    assert confirmed["filled_price"] == 70_100
    assert adapter.cache_invalidated is True
    assert settled == [("ORD-PENDING", True)]


@pytest.mark.asyncio
async def test_decision_maker_marks_pending_failed_when_confirm_record_raises(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(
        OrderResult(success=True, order_id="ORD-ERR", message="주문 접수")
    )
    adapter.order_status = OrderStatusInfo(
        order_id="ORD-ERR",
        symbol="005930",
        filled_qty=2,
        filled_price=70_500,
        remaining_qty=0,
        order_price=70_500,
    )
    decision_maker = DecisionMaker(broker_adapter=adapter)
    failed_marks: list[tuple[str | None, str]] = []
    settled: list[tuple[str, bool]] = []

    async def fake_sleep(_: float) -> None:
        return None

    async def fake_confirm_pending_record(**kwargs) -> None:
        raise RuntimeError("db write failed")

    async def fake_mark_pending_failed(pending_record_id: str | None, reason: str) -> None:
        failed_marks.append((pending_record_id, reason))

    async def fake_on_settled(order_id: str, success: bool) -> None:
        settled.append((order_id, success))

    monkeypatch.setattr("agent.decision_maker.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(decision_maker, "_confirm_pending_record", fake_confirm_pending_record)
    monkeypatch.setattr(decision_maker, "_mark_pending_failed", fake_mark_pending_failed)

    await decision_maker.confirm_and_record(
        symbol="005930",
        side="BUY",
        order_id="ORD-ERR",
        quantity=2,
        expected_price=70_000,
        pending_record_id="pending-err",
        on_settled=fake_on_settled,
    )

    assert failed_marks == [("pending-err", "db write failed")]
    assert settled == [("ORD-ERR", False)]
    assert adapter.cache_invalidated is False


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


@pytest.mark.asyncio
async def test_decision_maker_cancel_unfilled_order_returns_early_without_order_id(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    cancel_called = False

    async def fake_cancel(_order_id: str):
        nonlocal cancel_called
        cancel_called = True
        return SimpleNamespace(success=True, message="ok")

    monkeypatch.setattr("trading.order_executor.order_executor.cancel", fake_cancel)

    await decision_maker._cancel_unfilled_order("", "005930")

    assert cancel_called is False


@pytest.mark.asyncio
async def test_decision_maker_cancel_unfilled_order_swallows_failed_cancel(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_cancel(order_id: str, market=Market.KRX):
        adapter.cancelled_order_ids.append(order_id)
        return SimpleNamespace(success=False, message="already closed")

    monkeypatch.setattr(adapter, "cancel_order", fake_cancel)

    await decision_maker._cancel_unfilled_order("ORD-CLOSED", "005930")

    assert adapter.cancelled_order_ids == ["ORD-CLOSED"]


@pytest.mark.asyncio
async def test_decision_maker_cancel_unfilled_order_swallows_cancel_exception(monkeypatch) -> None:
    adapter = FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    decision_maker = DecisionMaker(broker_adapter=adapter)

    async def fake_cancel(order_id: str, market=Market.KRX):
        adapter.cancelled_order_ids.append(order_id)
        raise RuntimeError("cancel transport error")

    monkeypatch.setattr(adapter, "cancel_order", fake_cancel)

    await decision_maker._cancel_unfilled_order("ORD-ERR", "005930")

    assert adapter.cancelled_order_ids == ["ORD-ERR"]


@pytest.mark.asyncio
async def test_decision_maker_confirm_pending_record_creates_new_record_when_missing(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    recorded: dict = {}

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def filter_by_one(self, **kwargs):
            return None

    async def fake_record_trade_result(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr(decision_maker, "_record_trade_result", fake_record_trade_result)

    await decision_maker._confirm_pending_record(
        pending_record_id="missing-pending",
        symbol="005930",
        side="BUY",
        filled_qty=2,
        filled_price=70_500,
        analysis_context={"stock_name": "삼성전자"},
        cycle_id="cycle-missing",
    )

    assert recorded["symbol"] == "005930"
    assert recorded["side"] == "BUY"
    assert recorded["order_id"] == ""
    assert recorded["filled_qty"] == 2
    assert recorded["analysis_context"] == {"stock_name": "삼성전자"}
    assert recorded["cycle_id"] == "cycle-missing"


@pytest.mark.asyncio
async def test_decision_maker_confirm_pending_record_updates_sell_and_closes_open_buys(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    pending = FakeTradeResultRecord(
        id="pending-sell",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
        quantity=0,
        exit_price=0.0,
        exit_at=None,
        exit_reason="",
        notes="PENDING_CONFIRM",
    )
    open_buy = FakeTradeResultRecord(
        id="buy-open",
        entry_price=70_000,
        quantity=2,
        entry_at=SimpleNamespace(__rsub__=lambda self, other: __import__("datetime").timedelta(days=3)),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def filter_by_one(self, **kwargs):
            return pending

        async def get_all_open_buys(self, _symbol: str):
            return [open_buy]

    async def fake_log(*args, **kwargs) -> None:
        return None

    now = __import__("datetime").datetime(2026, 4, 2, 15, 20)
    open_buy.entry_at = now - __import__("datetime").timedelta(days=3)

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.decision_maker.now_kst", lambda: now)

    await decision_maker._confirm_pending_record(
        pending_record_id="pending-sell",
        symbol="005930",
        side="SELL",
        filled_qty=2,
        filled_price=73_000,
        exit_reason="FORCE_LIQUIDATION",
    )

    assert pending.status == OrderConfirmStatus.CONFIRMED.value
    assert pending.exit_price == 73_000
    assert pending.exit_reason == "FORCE_LIQUIDATION"
    assert pending.notes is None
    assert open_buy.exit_price == 73_000
    assert open_buy.pnl == 6_000
    assert open_buy.return_pct == round((73_000 - 70_000) / 70_000 * 100, 2)
    assert open_buy.hold_days == 3
    assert open_buy.exit_reason == "FORCE_LIQUIDATION"


@pytest.mark.asyncio
async def test_decision_maker_mark_pending_failed_returns_early_without_id(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    repo_created = False

    class FakeRepo:
        def __init__(self, _session) -> None:
            nonlocal repo_created
            repo_created = True

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)

    await decision_maker._mark_pending_failed(None, "ignored")

    assert repo_created is False


@pytest.mark.asyncio
async def test_decision_maker_mark_pending_failed_swallows_repo_errors(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def filter_by_one(self, **kwargs):
            raise RuntimeError("db lookup failed")

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", FakeSession)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)

    await decision_maker._mark_pending_failed("pending-err", "db lookup failed")


@pytest.mark.asyncio
async def test_decision_maker_record_trade_result_skips_duplicate_order_id(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return SimpleNamespace(id="existing-order")

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)

    await decision_maker._record_trade_result(
        symbol="005930",
        side="BUY",
        order_id="ORD-DUP",
        filled_qty=1,
        filled_price=71_000,
    )

    assert session.added == []


@pytest.mark.asyncio
async def test_decision_maker_record_trade_result_creates_sell_only_entry_without_open_buys(monkeypatch) -> None:
    decision_maker = DecisionMaker(
        broker_adapter=FakeBrokerAdapter(OrderResult(success=True, order_id="ORD-X", message="ok"))
    )
    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_order_id(self, _order_id: str):
            return None

        async def get_all_open_buys(self, _symbol: str):
            return []

    monkeypatch.setattr("agent.decision_maker.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("agent.decision_maker.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("agent.decision_maker.TradeResult", FakeTradeResultRecord)

    await decision_maker._record_trade_result(
        symbol="005930",
        side="SELL",
        order_id="ORD-ONLY-SELL",
        filled_qty=2,
        filled_price=72_500,
        analysis_context={"stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        exit_reason="SIGNAL",
    )

    assert len(session.added) == 1
    added = session.added[0]
    assert added.side == "SELL"
    assert added.entry_price == 0.0
    assert added.exit_price == 72_500
    assert added.exit_reason == "SIGNAL"
