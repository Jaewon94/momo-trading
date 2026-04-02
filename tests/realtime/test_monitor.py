from datetime import datetime

import pytest

from realtime.monitor import RealtimeMonitor
from trading.enums import Market
from trading.models import CurrentPrice, HoldingInfo


class FakeBrokerAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Market]] = []

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        self.calls.append((symbol, market))
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=71_500,
            change=500,
            change_rate=0.7,
            volume=123_456,
            timestamp=datetime.now(),
        )


@pytest.mark.asyncio
async def test_realtime_monitor_polls_prices_via_broker_adapter(monkeypatch) -> None:
    monitor = RealtimeMonitor()
    adapter = FakeBrokerAdapter()
    emitted: list[dict] = []

    async def fake_get_holdings() -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=3,
                avg_buy_price=70_000,
                current_price=71_500,
                pnl=4_500,
                pnl_rate=2.14,
            )
        ]

    async def fake_on_price_update(data: dict) -> None:
        emitted.append(data)

    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("realtime.monitor.get_broker_adapter", lambda: adapter)
    monkeypatch.setattr("realtime.monitor.event_detector.on_price_update", fake_on_price_update)

    await monitor._poll_holdings_prices()

    assert adapter.calls == [("005930", Market.KRX)]
    assert emitted == [{
        "symbol": "005930",
        "price": 71_500.0,
        "volume": 123_456,
        "change_rate": 0.7,
        "source": "polling_fallback",
    }]
