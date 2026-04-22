import pytest
from pydantic import ValidationError

from trading.enums import BrokerProvider, Market, OrderSession, OrderSide, OrderType
from trading.models import (
    AccountBalance,
    CurrentPrice,
    HoldingInfo,
    MCPResponse,
    OrderRequest,
    OrderResult,
    PendingOrderInfo,
)
from trading.adapters.kis_adapter import KisBrokerAdapter


class FakeAccountClient:
    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=1_000_000,
            cash=700_000,
            stock_value=300_000,
            total_pnl=12_500,
            total_pnl_rate=1.25,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=3,
                avg_buy_price=70_000,
                current_price=71_000,
                pnl=3_000,
                pnl_rate=1.43,
            )
        ]

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return [
            PendingOrderInfo(
                order_id="1001",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=3,
                filled_qty=1,
                remaining_qty=2,
                order_price=70_500,
                order_time="091500",
            )
        ]


class FakeMarketDataClient:
    async def get_current_price(self, symbol: str, market: str = "KRX") -> MCPResponse:
        return MCPResponse(
            success=True,
            data={
                "price": 71_000,
                "current_price": 71_000,
                "change": 500,
                "change_rate": 0.71,
                "volume": 123456,
            },
        )

    async def get_daily_price(
        self,
        symbol: str,
        period: str = "D",
        count: int = 30,
        market: str = "KRX",
    ) -> MCPResponse:
        return MCPResponse(
            success=True,
            data={
                "prices": [
                    {"date": "20260317", "open": 70000, "high": 71500, "low": 69800, "close": 71000, "volume": 100},
                    {"date": "20260318", "open": 71000, "high": 72000, "low": 70500, "close": 71500, "volume": 120},
                ]
            },
        )

    async def get_minute_price(
        self,
        symbol: str,
        period: str = "5",
        market: str = "KRX",
    ) -> MCPResponse:
        return MCPResponse(
            success=True,
            data={
                "prices": [
                    {"time": "0900", "open": 71000, "high": 71100, "low": 70900, "close": 71050, "volume": 10},
                    {"time": "0905", "open": 71050, "high": 71200, "low": 71000, "close": 71150, "volume": 12},
                ]
            },
        )


class FakeOrderExecutor:
    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []
        self.cancel_requests: list[tuple[str, str]] = []

    async def execute(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return OrderResult(
            success=True,
            order_id="A-1",
            message="ok",
            filled_quantity=request.quantity,
            filled_price=request.price or 0,
        )

    async def cancel(self, order_id: str, market: str = "KRX") -> OrderResult:
        self.cancel_requests.append((order_id, market))
        return OrderResult(success=True, order_id=order_id, message="cancelled")


def build_adapter() -> tuple[KisBrokerAdapter, FakeOrderExecutor]:
    order_executor = FakeOrderExecutor()
    adapter = KisBrokerAdapter(
        account_client=FakeAccountClient(),
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )
    return adapter, order_executor


def test_limit_order_requires_price() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="005930",
            market=Market.KOSPI,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
        )


def test_market_order_allows_empty_price() -> None:
    order = OrderRequest(
        symbol="005930",
        market=Market.KOSPI,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
    )
    assert order.price is None


def test_order_request_defaults_to_regular_session() -> None:
    order = OrderRequest(
        symbol="005930",
        market=Market.KOSPI,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=71_000,
    )

    assert order.order_session == OrderSession.REGULAR


@pytest.mark.asyncio
async def test_kis_adapter_exposes_provider_and_capabilities() -> None:
    adapter, _ = build_adapter()

    assert adapter.provider == BrokerProvider.KIS
    assert adapter.capabilities.supports_domestic_stocks is True
    assert adapter.capabilities.supports_overseas_stocks is True
    assert adapter.capabilities.supports_paper_trading is True
    assert adapter.capabilities.supports_realtime_quotes is True
    assert adapter.capabilities.supports_nxt_quotes is True
    assert adapter.capabilities.supports_after_hours_orders is False
    assert adapter.capabilities.supported_order_sessions == [OrderSession.REGULAR]


@pytest.mark.asyncio
async def test_kis_adapter_returns_account_snapshot_models() -> None:
    adapter, _ = build_adapter()

    balance = await adapter.get_balance()
    holdings = await adapter.get_holdings()
    pending_orders = await adapter.get_pending_orders()

    assert balance.cash == 700_000
    assert holdings[0].symbol == "005930"
    assert pending_orders[0].remaining_qty == 2


@pytest.mark.asyncio
async def test_kis_adapter_maps_quote_response_to_current_price() -> None:
    adapter, _ = build_adapter()

    quote = await adapter.get_current_price("005930", market=Market.KOSPI)

    assert isinstance(quote, CurrentPrice)
    assert quote.symbol == "005930"
    assert quote.market == Market.KOSPI
    assert quote.price == 71_000
    assert quote.volume == 123456


@pytest.mark.asyncio
async def test_kis_adapter_delegates_order_execution() -> None:
    adapter, order_executor = build_adapter()
    request = OrderRequest(
        symbol="005930",
        market=Market.KOSPI,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=2,
        price=71_000,
    )

    result = await adapter.place_order(request)

    assert result.success is True
    assert result.order_id == "A-1"
    assert order_executor.requests == [request]


@pytest.mark.asyncio
async def test_kis_adapter_returns_normalized_candles() -> None:
    adapter, _ = build_adapter()

    daily = await adapter.get_daily_candles("005930", count=2, market=Market.KOSPI)
    intraday = await adapter.get_intraday_candles("005930", interval="5", market=Market.KOSPI)

    assert [c.close for c in daily] == [71000.0, 71500.0]
    assert intraday[0].time_key == "0900"
