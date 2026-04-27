import pandas as pd
import pytest

from backtesting.engine import BacktestConfig, BacktestEngine
from strategy.signal import TradeSignal
from trading.enums import SignalAction


class OneBuySignalStrategy:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, analysis: dict) -> TradeSignal:
        self.calls += 1
        action = SignalAction.BUY if self.calls == 1 else SignalAction.HOLD
        return TradeSignal(
            symbol=analysis["symbol"],
            stock_id="",
            action=action,
            strength=1.0,
            confidence=1.0,
            strategy_type="TEST",
        )


def _ohlcv_frame(rows: int = 32) -> pd.DataFrame:
    data = []
    for index in range(rows):
        data.append({
            "date": f"2026-04-{index + 1:02d}",
            "open": 100.0 + index,
            "high": 120.0 + index,
            "low": 90.0 + index,
            "close": 110.0 + index,
            "volume": 1000 + index,
        })
    return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_backtest_default_executes_signal_on_next_open_not_same_close() -> None:
    engine = BacktestEngine(BacktestConfig(slippage_rate=0.0, commission_rate=0.0))
    engine.strategy = OneBuySignalStrategy()

    result = await engine.run("005930", _ohlcv_frame())

    trade = result["trades"][0]
    assert trade.entry_date == "2026-04-32"
    assert trade.entry_price == 131.0


@pytest.mark.asyncio
async def test_backtest_legacy_same_close_execution_is_explicit_opt_in() -> None:
    engine = BacktestEngine(BacktestConfig(
        execution_timing="LEGACY_SAME_CLOSE",
        slippage_rate=0.0,
        commission_rate=0.0,
    ))
    engine.strategy = OneBuySignalStrategy()

    result = await engine.run("005930", _ohlcv_frame())

    trade = result["trades"][0]
    assert trade.entry_date == "2026-04-31"
    assert trade.entry_price == 140.0
