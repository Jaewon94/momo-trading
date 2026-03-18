import pytest

from agent.trading_agent import TradingAgent
from trading.enums import Market
from trading.models import Candle, CurrentPrice


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
