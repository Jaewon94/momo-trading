import pytest

from exceptions.common import ServiceException
from services.manual_trade_service import ManualTradeService
from trading.enums import Market, OrderSession, OrderSide, OrderType
from trading.models import BrokerCapabilities, HoldingInfo, OrderRequest, OrderResult, PendingOrderInfo


class FakeBrokerAdapter:
    def __init__(
        self,
        *,
        holdings=None,
        pending_orders=None,
        place_result=None,
        cancel_result=None,
    ) -> None:
        self._holdings = list(holdings or [])
        self._pending_orders = list(pending_orders or [])
        self.place_result = place_result or OrderResult(success=True, order_id="ORD-1", message="ok")
        self.cancel_result = cancel_result or OrderResult(success=True, order_id="CAN-1", message="cancelled")
        self.capabilities = BrokerCapabilities(supported_order_sessions=[OrderSession.REGULAR])
        self.placed_requests: list[OrderRequest] = []
        self.cancelled_order_ids: list[str] = []
        self.cache_invalidated = False

    async def get_holdings(self):
        return list(self._holdings)

    async def get_pending_orders(self):
        return list(self._pending_orders)

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.placed_requests.append(request)
        return self.place_result

    async def cancel_order(self, order_id: str, market=Market.KRX) -> OrderResult:
        self.cancelled_order_ids.append(order_id)
        return self.cancel_result

    def invalidate_cache(self) -> None:
        self.cache_invalidated = True


class FailingBrokerAdapter(FakeBrokerAdapter):
    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.placed_requests.append(request)
        raise RuntimeError("broker down")


@pytest.mark.asyncio
async def test_manual_trade_service_places_market_sell_and_confirms(monkeypatch):
    adapter = FakeBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="A005930",
                name="삼성전자",
                quantity=7,
                avg_buy_price=70000,
                current_price=72000,
                pnl=14000,
                pnl_rate=2.0,
            ),
        ],
        place_result=OrderResult(success=True, order_id="SELL-1", message="접수"),
    )
    confirmed = {}
    logs = []
    service = ManualTradeService(broker_adapter=adapter)

    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    async def fake_confirm_and_record(**kwargs):
        confirmed.update(kwargs)

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    monkeypatch.setattr("services.manual_trade_service.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("services.manual_trade_service.activity_logger.log", fake_log)

    result = await service.sell_position("005930")

    assert result["symbol"] == "005930"
    assert result["order_id"] == "SELL-1"
    assert adapter.placed_requests[0].side == OrderSide.SELL
    assert adapter.placed_requests[0].order_type == OrderType.MARKET
    assert adapter.placed_requests[0].quantity == 7
    assert confirmed["symbol"] == "005930"
    assert confirmed["side"] == "SELL"
    assert confirmed["order_id"] == "SELL-1"
    assert logs


@pytest.mark.asyncio
async def test_manual_trade_service_cancels_pending_buy(monkeypatch):
    adapter = FakeBrokerAdapter(
        pending_orders=[
            PendingOrderInfo(
                order_id="BUY-1",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=7,
                filled_qty=0,
                remaining_qty=7,
                order_price=71000,
                order_time="091500",
            ),
        ],
    )
    service = ManualTradeService(broker_adapter=adapter)
    logs = []
    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    async def fake_log(*args, **kwargs):
        logs.append((args, kwargs))

    monkeypatch.setattr("services.manual_trade_service.activity_logger.log", fake_log)

    result = await service.cancel_pending_buy("BUY-1")

    assert result["order_id"] == "BUY-1"
    assert adapter.cancelled_order_ids == ["BUY-1"]
    assert adapter.cache_invalidated is True
    assert logs


@pytest.mark.asyncio
async def test_manual_trade_service_cancels_pending_sell_then_places_market_sell(monkeypatch):
    adapter = FakeBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70000,
                current_price=72000,
                pnl=10000,
                pnl_rate=1.5,
            ),
        ],
        pending_orders=[
            PendingOrderInfo(
                order_id="SELL-OLD-1",
                symbol="005930",
                name="삼성전자",
                side="매도",
                order_qty=5,
                filled_qty=0,
                remaining_qty=5,
                order_price=72500,
                order_time="101200",
            ),
        ],
        place_result=OrderResult(success=True, order_id="SELL-NEW-1", message="접수"),
    )
    confirmed = {}
    service = ManualTradeService(broker_adapter=adapter)
    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    async def fake_confirm_and_record(**kwargs):
        confirmed.update(kwargs)

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("services.manual_trade_service.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("services.manual_trade_service.activity_logger.log", fake_log)

    result = await service.replace_pending_sell_with_market_order("SELL-OLD-1")

    assert result["cancelled_order_id"] == "SELL-OLD-1"
    assert result["new_order_id"] == "SELL-NEW-1"
    assert adapter.cancelled_order_ids == ["SELL-OLD-1"]
    assert adapter.placed_requests[0].side == OrderSide.SELL
    assert adapter.placed_requests[0].quantity == 5
    assert confirmed["order_id"] == "SELL-NEW-1"


@pytest.mark.asyncio
async def test_manual_trade_service_rejects_immediate_sell_when_pending_sell_exists(monkeypatch):
    adapter = FakeBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70000,
                current_price=72000,
                pnl=10000,
                pnl_rate=1.5,
            ),
        ],
        pending_orders=[
            PendingOrderInfo(
                order_id="SELL-OLD-1",
                symbol="005930",
                name="삼성전자",
                side="매도",
                order_qty=5,
                filled_qty=0,
                remaining_qty=5,
                order_price=72500,
                order_time="101200",
            ),
        ],
    )
    service = ManualTradeService(broker_adapter=adapter)
    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    with pytest.raises(ServiceException) as exc_info:
        await service.sell_position("005930")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_manual_trade_service_rejects_immediate_sell_outside_regular_session(monkeypatch):
    adapter = FakeBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70000,
                current_price=72000,
                pnl=10000,
                pnl_rate=1.5,
            ),
        ],
    )
    service = ManualTradeService(broker_adapter=adapter)
    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": False, "label": "장외"},
    )

    with pytest.raises(ServiceException) as exc_info:
        await service.sell_position("005930")

    assert exc_info.value.status_code == 400
    assert "현재 세션(장외)" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_manual_trade_service_rejects_immediate_sell_when_broker_capability_excludes_regular(monkeypatch):
    adapter = FakeBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70000,
                current_price=72000,
                pnl=10000,
                pnl_rate=1.5,
            ),
        ],
    )
    adapter.capabilities = BrokerCapabilities(supported_order_sessions=[OrderSession.AFTER_HOURS_SINGLE])
    service = ManualTradeService(broker_adapter=adapter)
    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    with pytest.raises(ServiceException) as exc_info:
        await service.sell_position("005930")

    assert exc_info.value.status_code == 400
    assert "정규장 즉시 매도" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_manual_trade_service_captures_unexpected_broker_error(monkeypatch):
    adapter = FailingBrokerAdapter(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70000,
                current_price=72000,
                pnl=10000,
                pnl_rate=1.5,
            ),
        ],
    )
    service = ManualTradeService(broker_adapter=adapter)
    captured = {}

    monkeypatch.setattr("services.manual_trade_service.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(
        "services.manual_trade_service.market_calendar.get_market_session_info",
        lambda: {"is_regular_open": True, "label": "정규장"},
    )

    async def fake_capture_exception(**kwargs):
        captured.update(kwargs)
        return {"fingerprint": "fp-1"}

    monkeypatch.setattr("services.manual_trade_service.error_capture_service.capture_exception", fake_capture_exception)

    with pytest.raises(RuntimeError, match="broker down"):
        await service.sell_position("005930")

    assert captured["component"] == "manual_trade"
    assert captured["operation"] == "sell_position"
    assert captured["symbol"] == "005930"
