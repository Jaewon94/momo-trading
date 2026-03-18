import pytest

from agent.trading_agent import TradingAgent
from trading.enums import Market, OrderSide, OrderType
from trading.models import AccountBalance, Candle, CurrentPrice, HoldingInfo, OrderRequest, OrderResult


class FakeBrokerAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | int]] = []

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        self.calls.append(("quote", symbol, market.value))
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=71_500,
            change=500,
            change_rate=0.7,
            volume=123456,
            timestamp=__import__("datetime").datetime.now(),
        )

    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KRX,
    ) -> list[Candle]:
        self.calls.append(("daily", symbol, count))
        return [
            Candle(
                time_key="20260318",
                open=71000,
                high=72000,
                low=70500,
                close=71500,
                volume=120,
            )
        ]

    async def get_intraday_candles(
        self,
        symbol: str,
        interval: str = "5",
        market: Market = Market.KRX,
    ) -> list[Candle]:
        self.calls.append(("intraday", symbol, interval))
        return [
            Candle(
                time_key="0900",
                open=71000,
                high=71100,
                low=70900,
                close=71050,
                volume=10,
            )
        ]


@pytest.mark.asyncio
async def test_trading_agent_fetches_market_data_via_broker_adapter() -> None:
    adapter = FakeBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    price_resp, daily_resp, minute_resp = await agent._fetch_symbol_market_data("005930")

    assert price_resp.success is True
    assert price_resp.data["price"] == 71_500
    assert daily_resp.data["prices"][0]["date"] == "20260318"
    assert minute_resp.data["prices"][0]["time"] == "0900"
    assert adapter.calls == [
        ("quote", "005930", "KRX"),
        ("daily", "005930", 60),
        ("intraday", "005930", "5"),
    ]


class FakePortfolioBrokerAdapter:
    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=2_000_000,
            cash=1_200_000,
            stock_value=800_000,
            total_pnl=15_000,
            total_pnl_rate=0.75,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=4,
                avg_buy_price=70_000,
                current_price=71_500,
                pnl=6_000,
                pnl_rate=2.18,
            )
        ]

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return OrderResult(
            success=True,
            order_id="SELL-1",
            message="ok",
            filled_quantity=0,
            filled_price=0.0,
        )


@pytest.mark.asyncio
async def test_trading_agent_builds_portfolio_snapshot_from_broker_adapter(monkeypatch) -> None:
    adapter = FakePortfolioBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    async def fake_today_trade_count() -> int:
        return 2

    monkeypatch.setattr(agent, "_get_today_trade_count", fake_today_trade_count)

    snapshot = await agent._build_portfolio_snapshot()

    assert snapshot == {
        "cash": 1_200_000,
        "total_asset": 2_000_000,
        "holding_count": 1,
        "today_trade_count": 2,
        "holding_symbols": ["005930"],
    }
    assert agent._available_cash == 1_200_000


@pytest.mark.asyncio
async def test_trading_agent_executes_exit_order_via_broker_adapter(monkeypatch) -> None:
    adapter = FakePortfolioBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)
    recorded: dict = {}

    async def fake_confirm_and_record(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.decision_maker.confirm_and_record", fake_confirm_and_record)

    result = await agent._execute_exit_order(
        symbol="005930",
        expected_price=71_000,
        exit_reason="STOP_LOSS",
    )

    assert result is not None
    assert result.success is True
    assert adapter.requests[0].side == OrderSide.SELL
    assert adapter.requests[0].order_type == OrderType.MARKET
    assert adapter.requests[0].market == Market.KRX
    assert adapter.requests[0].quantity == 4
    assert recorded["order_id"] == "SELL-1"
    assert recorded["exit_reason"] == "STOP_LOSS"
