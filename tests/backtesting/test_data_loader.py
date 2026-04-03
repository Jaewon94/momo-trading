from datetime import date

import pandas as pd
import pytest

from backtesting.data_loader import BacktestDataLoader
from trading.enums import Market
from trading.models import Candle


class FakeBrokerAdapter:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles
        self.calls: list[tuple[str, int, Market]] = []

    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KRX,
    ) -> list[Candle]:
        self.calls.append((symbol, count, market))
        return self._candles


@pytest.mark.asyncio
async def test_backtest_data_loader_uses_broker_adapter_candles(monkeypatch) -> None:
    adapter = FakeBrokerAdapter([
        Candle(time_key="20260401", open=1000, high=1100, low=980, close=1080, volume=1000),
        Candle(time_key="20260402", open=1080, high=1120, low=1050, close=1110, volume=1200),
    ])
    monkeypatch.setattr("backtesting.data_loader.get_broker_adapter", lambda: adapter)

    df = await BacktestDataLoader.load_from_broker(
        symbol="005930",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 3),
    )

    assert adapter.calls == [("005930", 2, Market.KRX)]
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert isinstance(df.loc[0, "date"], pd.Timestamp)
    assert df.loc[1, "close"] == 1110


@pytest.mark.asyncio
async def test_backtest_data_loader_returns_empty_frame_when_broker_raises(monkeypatch) -> None:
    class FailingBrokerAdapter:
        async def get_daily_candles(self, symbol: str, count: int = 30, market: Market = Market.KRX):
            raise RuntimeError("broker down")

    monkeypatch.setattr("backtesting.data_loader.get_broker_adapter", lambda: FailingBrokerAdapter())

    df = await BacktestDataLoader.load_from_broker(
        symbol="005930",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 3),
    )

    assert df.empty is True
