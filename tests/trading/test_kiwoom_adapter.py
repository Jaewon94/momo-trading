import pytest

from trading.adapters.kiwoom_adapter import KiwoomBrokerAdapter
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


class FakeAccountClient:
    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=2_000_000,
            cash=1_100_000,
            stock_value=900_000,
            total_pnl=33_000,
            total_pnl_rate=1.65,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=5,
                avg_buy_price=70_000,
                current_price=73_000,
                pnl=15_000,
                pnl_rate=4.28,
            )
        ]

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return [
            PendingOrderInfo(
                order_id="2002",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=5,
                filled_qty=0,
                remaining_qty=5,
                order_price=71_000,
                order_time="100000",
            )
        ]


class FakeMarketDataClient:
    async def get_current_price(self, symbol: str, market: str = "KRX") -> MCPResponse:
        return MCPResponse(
            success=True,
            data={
                "price": 73_000,
                "change": 1_000,
                "change_rate": 1.39,
                "volume": 654321,
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
                    {"date": "20260317", "open": 71000, "high": 72500, "low": 70800, "close": 72000, "volume": 200},
                    {"date": "20260318", "open": 72000, "high": 73500, "low": 71800, "close": 73000, "volume": 220},
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
                    {"time": "1000", "open": 72900, "high": 73000, "low": 72800, "close": 72950, "volume": 15},
                    {"time": "1005", "open": 72950, "high": 73100, "low": 72900, "close": 73050, "volume": 18},
                ]
            },
        )

    async def get_volume_rank(self, market: str = "KRX") -> MCPResponse:
        return MCPResponse(
            success=True,
            data={
                "stocks": [
                    {"symbol": "005930", "name": "삼성전자", "price": 73000, "change_rate": 1.39, "volume": 654321}
                ]
            },
        )

    async def get_fluctuation_rank(self, sort: str, market: str = "KRX") -> MCPResponse:
        symbol = "035720" if sort == "top" else "000660"
        change_rate = 5.12 if sort == "top" else -4.21
        return MCPResponse(
            success=True,
            data={
                "stocks": [
                    {"symbol": symbol, "name": "테스트", "price": 52000, "change_rate": change_rate, "volume": 123456}
                ]
            },
        )


class FakeOrderExecutor:
    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []
        self.cancel_requests: list[dict] = []

    async def execute(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return OrderResult(
            success=True,
            order_id="K-1",
            message="ok",
            filled_quantity=request.quantity,
            filled_price=request.price or 0,
        )

    async def cancel(
        self,
        order_id: str,
        market: str = "KRX",
        symbol: str | None = None,
        quantity: int | None = None,
    ) -> OrderResult:
        self.cancel_requests.append({
            "order_id": order_id,
            "market": market,
            "symbol": symbol,
            "quantity": quantity,
        })
        return OrderResult(success=True, order_id=order_id, message="cancelled")


def build_adapter() -> tuple[KiwoomBrokerAdapter, FakeOrderExecutor]:
    order_executor = FakeOrderExecutor()
    adapter = KiwoomBrokerAdapter(
        account_client=FakeAccountClient(),
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )
    return adapter, order_executor


class MutableAccountClient(FakeAccountClient):
    def __init__(
        self,
        *,
        holdings: list[HoldingInfo] | None = None,
        pending_orders: list[PendingOrderInfo] | None = None,
    ) -> None:
        self.holdings = holdings or []
        self.pending_orders = pending_orders or []

    async def get_holdings(self) -> list[HoldingInfo]:
        return self.holdings

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return self.pending_orders


@pytest.mark.asyncio
async def test_kiwoom_adapter_exposes_provider_and_capabilities() -> None:
    adapter, _ = build_adapter()

    assert adapter.provider == BrokerProvider.KIWOOM
    assert adapter.capabilities.supports_domestic_stocks is True
    assert adapter.capabilities.supports_overseas_stocks is False
    assert adapter.capabilities.supports_paper_trading is True
    assert adapter.capabilities.supports_realtime_quotes is False
    assert adapter.capabilities.supports_order_cancellation is True
    assert adapter.capabilities.supports_nxt_quotes is False
    assert adapter.capabilities.supports_after_hours_orders is False
    assert adapter.capabilities.supported_order_sessions == [OrderSession.REGULAR]


@pytest.mark.asyncio
async def test_kiwoom_adapter_cancels_order_with_pending_order_context() -> None:
    order_executor = FakeOrderExecutor()
    adapter = KiwoomBrokerAdapter(
        account_client=MutableAccountClient(
            pending_orders=[
                PendingOrderInfo(
                    order_id="0086997",
                    symbol="A092220",
                    name="KEC",
                    side="매수",
                    order_qty=7552,
                    filled_qty=0,
                    remaining_qty=7552,
                    order_price=1660,
                    order_time="102553",
                )
            ]
        ),
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )

    result = await adapter.cancel_order("0086997", market=Market.KRX)

    assert result.success is True
    assert order_executor.cancel_requests == [{
        "order_id": "0086997",
        "market": "KRX",
        "symbol": "092220",
        "quantity": 7552,
    }]


@pytest.mark.asyncio
async def test_kiwoom_adapter_returns_account_snapshot_models() -> None:
    adapter, _ = build_adapter()

    balance = await adapter.get_balance()
    holdings = await adapter.get_holdings()
    pending_orders = await adapter.get_pending_orders()

    assert balance.cash == 1_100_000
    assert holdings[0].symbol == "005930"
    assert pending_orders[0].remaining_qty == 5


@pytest.mark.asyncio
async def test_kiwoom_adapter_maps_quote_response_to_current_price() -> None:
    adapter, _ = build_adapter()

    quote = await adapter.get_current_price("005930", market=Market.KRX)

    assert isinstance(quote, CurrentPrice)
    assert quote.symbol == "005930"
    assert quote.market == Market.KRX
    assert quote.price == 73_000
    assert quote.volume == 654321


@pytest.mark.asyncio
async def test_kiwoom_adapter_delegates_order_execution() -> None:
    adapter, order_executor = build_adapter()
    request = OrderRequest(
        symbol="005930",
        market=Market.KRX,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=3,
        price=72_500,
    )

    result = await adapter.place_order(request)

    assert result.success is True
    assert result.order_id == "K-1"
    assert order_executor.requests == [request]


@pytest.mark.asyncio
async def test_kiwoom_adapter_rounds_krx_buy_limit_price_up_to_tick() -> None:
    adapter, order_executor = build_adapter()

    await adapter.place_order(
        OrderRequest(
            symbol="006340",
            market=Market.KRX,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=600,
            price=15_865,
        )
    )

    assert order_executor.requests[0].price == 15_870


@pytest.mark.asyncio
async def test_kiwoom_adapter_rounds_krx_sell_limit_price_down_to_tick() -> None:
    adapter, order_executor = build_adapter()

    await adapter.place_order(
        OrderRequest(
            symbol="006340",
            market=Market.KRX,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=600,
            price=15_865,
        )
    )

    assert order_executor.requests[0].price == 15_860


@pytest.mark.asyncio
async def test_kiwoom_adapter_infers_filled_buy_from_holdings_when_order_leaves_pending_book() -> None:
    account_client = MutableAccountClient(
        holdings=[],
        pending_orders=[],
    )
    order_executor = FakeOrderExecutor()
    adapter = KiwoomBrokerAdapter(
        account_client=account_client,
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )
    request = OrderRequest(
        symbol="005930",
        market=Market.KRX,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=3,
        price=72_500,
    )

    result = await adapter.place_order(request)
    account_client.holdings = [
        HoldingInfo(
            symbol="005930",
            name="삼성전자",
            quantity=3,
            avg_buy_price=72_400,
            current_price=72_400,
            pnl=0,
            pnl_rate=0,
        )
    ]

    status = await adapter.get_order_status(result.order_id or "")

    assert status is not None
    assert status.order_id == "K-1"
    assert status.symbol == "005930"
    assert status.filled_qty == 3
    assert status.remaining_qty == 0
    assert status.filled_price == 72_500


@pytest.mark.asyncio
async def test_kiwoom_adapter_uses_holding_avg_price_when_pending_fill_has_zero_order_price() -> None:
    account_client = MutableAccountClient(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=8,
                avg_buy_price=72_400,
                current_price=72_400,
                pnl=0,
                pnl_rate=0,
            )
        ],
        pending_orders=[
            PendingOrderInfo(
                order_id="K-1",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=3,
                filled_qty=3,
                remaining_qty=0,
                order_price=0,
                order_time="100000",
            )
        ],
    )
    order_executor = FakeOrderExecutor()
    adapter = KiwoomBrokerAdapter(
        account_client=account_client,
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )

    request = OrderRequest(
        symbol="005930",
        market=Market.KRX,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=3,
        price=None,
    )
    result = await adapter.place_order(request)

    status = await adapter.get_order_status(result.order_id or "")

    assert status is not None
    assert status.filled_qty == 3
    assert status.filled_price == 72_400
    assert status.order_price == 72_400


@pytest.mark.asyncio
async def test_kiwoom_adapter_does_not_use_holding_avg_price_for_pending_sell_fill() -> None:
    account_client = MutableAccountClient(
        holdings=[
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=2,
                avg_buy_price=70_000,
                current_price=73_000,
                pnl=6_000,
                pnl_rate=4.28,
            )
        ],
        pending_orders=[
            PendingOrderInfo(
                order_id="K-1",
                symbol="005930",
                name="삼성전자",
                side="매도",
                order_qty=3,
                filled_qty=3,
                remaining_qty=0,
                order_price=0,
                order_time="100000",
            )
        ],
    )
    order_executor = FakeOrderExecutor()
    adapter = KiwoomBrokerAdapter(
        account_client=account_client,
        market_data_client=FakeMarketDataClient(),
        order_executor=order_executor,
    )

    result = await adapter.place_order(OrderRequest(
        symbol="005930",
        market=Market.KRX,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=3,
        price=73_000,
    ))

    status = await adapter.get_order_status(result.order_id or "")

    assert status is not None
    assert status.filled_qty == 3
    assert status.filled_price == 0
    assert status.order_price == 0


@pytest.mark.asyncio
async def test_kiwoom_adapter_returns_normalized_candles() -> None:
    adapter, _ = build_adapter()

    daily = await adapter.get_daily_candles("005930", count=2, market=Market.KRX)
    intraday = await adapter.get_intraday_candles("005930", interval="5", market=Market.KRX)

    assert [c.close for c in daily] == [72000.0, 73000.0]
    assert intraday[0].time_key == "1000"


@pytest.mark.asyncio
async def test_kiwoom_adapter_delegates_market_rank_requests() -> None:
    adapter, _ = build_adapter()

    volume = await adapter.get_volume_rank()
    top = await adapter.get_fluctuation_rank("top")
    bottom = await adapter.get_fluctuation_rank("bottom")

    assert volume[0]["symbol"] == "005930"
    assert top[0]["symbol"] == "035720"
    assert bottom[0]["symbol"] == "000660"
