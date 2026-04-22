import pytest

from trading.adapters.kiwoom_adapter import KiwoomBrokerAdapter
from trading.enums import Market, OrderSide, OrderType
from trading.kiwoom_clients import KiwoomMarketDataClient, KiwoomOrderExecutor
from trading.kiwoom_rest_client import KiwoomRESTClient
from trading.models import MCPResponse, OrderRequest, OrderResult


class FakeAccountClient:
    async def get_balance(self):
        raise AssertionError("not used")

    async def get_holdings(self):
        return []

    async def get_pending_orders(self):
        return []


class FakeMarketDataClient:
    async def get_current_price(self, symbol: str, market: str = "KRX") -> MCPResponse:
        if market == "NASDAQ":
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")
        return MCPResponse(success=True, data={"current_price": 73_000, "change": 0, "change_rate": 0, "volume": 1})

    async def get_daily_price(
        self,
        symbol: str,
        period: str = "D",
        count: int = 30,
        market: str = "KRX",
    ) -> MCPResponse:
        if market == "NASDAQ":
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")
        return MCPResponse(success=True, data={"prices": []})

    async def get_minute_price(
        self,
        symbol: str,
        period: str = "5",
        market: str = "KRX",
    ) -> MCPResponse:
        if market == "NASDAQ":
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")
        return MCPResponse(success=True, data={"prices": []})

    async def get_volume_rank(self, market: str = "KRX") -> MCPResponse:
        if market == "NASDAQ":
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")
        return MCPResponse(success=True, data={"stocks": [{"symbol": "005930"}]})

    async def get_fluctuation_rank(self, sort: str, market: str = "KRX") -> MCPResponse:
        if market == "NASDAQ":
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")
        symbol = "035720" if sort == "top" else "000660"
        return MCPResponse(success=True, data={"stocks": [{"symbol": symbol}]})


class FakeOrderExecutor:
    def __init__(self) -> None:
        self.cancel_requests = []

    async def execute(self, request: OrderRequest) -> OrderResult:
        return OrderResult(success=True, order_id="K-1", message="ok")

    async def cancel(
        self,
        order_id: str,
        market: str = "KRX",
        symbol: str | None = None,
        quantity: int | None = None,
    ) -> OrderResult:
        self.cancel_requests.append((order_id, market, symbol, quantity))
        return OrderResult(success=True, order_id="CANCEL-1", message="cancelled")


def build_adapter() -> KiwoomBrokerAdapter:
    return KiwoomBrokerAdapter(
        account_client=FakeAccountClient(),
        market_data_client=FakeMarketDataClient(),
        order_executor=FakeOrderExecutor(),
    )


@pytest.mark.asyncio
async def test_kiwoom_adapter_rejects_overseas_quote_requests() -> None:
    adapter = build_adapter()

    with pytest.raises(RuntimeError, match="국내주식만 지원"):
        await adapter.get_current_price("AAPL", Market.NASDAQ)


@pytest.mark.asyncio
async def test_kiwoom_adapter_rejects_overseas_candle_requests() -> None:
    adapter = build_adapter()

    with pytest.raises(RuntimeError, match="국내주식만 지원"):
        await adapter.get_daily_candles("AAPL", market=Market.NASDAQ)

    with pytest.raises(RuntimeError, match="국내주식만 지원"):
        await adapter.get_intraday_candles("AAPL", market=Market.NASDAQ)


@pytest.mark.asyncio
async def test_kiwoom_adapter_delegates_rankings_for_domestic_market() -> None:
    adapter = build_adapter()

    assert await adapter.get_volume_rank() == [{"symbol": "005930"}]
    assert await adapter.get_fluctuation_rank("top") == [{"symbol": "035720"}]


@pytest.mark.asyncio
async def test_kiwoom_adapter_cancel_order_reports_missing_pending_order() -> None:
    adapter = build_adapter()

    result = await adapter.cancel_order("ORD-1")

    assert result.success is False
    assert "미체결 주문" in result.message


@pytest.mark.asyncio
async def test_kiwoom_market_data_client_rejects_overseas_market_without_network() -> None:
    client = KiwoomMarketDataClient(
        KiwoomRESTClient(
            app_key="real-key",
            secret_key="real-secret",
            paper_app_key="paper-key",
            paper_secret_key="paper-secret",
            account_type="VIRTUAL",
            token_cache_path=None,
        )
    )

    quote = await client.get_current_price("AAPL", market="NASDAQ")
    daily = await client.get_daily_price("AAPL", market="NASDAQ")
    minute = await client.get_minute_price("AAPL", market="NASDAQ")

    assert quote.success is False
    assert daily.success is False
    assert minute.success is False
    assert "국내주식만 지원" in quote.error


@pytest.mark.asyncio
async def test_kiwoom_order_executor_rejects_overseas_orders_without_network() -> None:
    executor = KiwoomOrderExecutor(
        KiwoomRESTClient(
            app_key="real-key",
            secret_key="real-secret",
            paper_app_key="paper-key",
            paper_secret_key="paper-secret",
            account_type="VIRTUAL",
            token_cache_path=None,
        )
    )
    request = OrderRequest(
        symbol="AAPL",
        market=Market.NASDAQ,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1,
        price=100,
    )

    result = await executor.execute(request)

    assert result.success is False
    assert "국내주식만 지원" in result.message
