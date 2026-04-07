from datetime import datetime

import asyncio
import pytest

from core.config import settings
from realtime.monitor import RealtimeMonitor
from realtime.stream_manager import StreamManager
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


@pytest.mark.asyncio
async def test_realtime_monitor_start_skips_kis_websocket_in_kiwoom_mode(monkeypatch) -> None:
    monitor = RealtimeMonitor()
    observed: list[str] = []

    async def fail_stream_start() -> None:
        raise AssertionError("KIS websocket should not start in KIWOOM mode")

    async def fake_poll_loop() -> None:
        observed.append("poll_loop")

    async def fake_health_loop() -> None:
        observed.append("health_loop")

    monkeypatch.setattr(settings, "BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("realtime.monitor.stream_manager.start", fail_stream_start)
    monkeypatch.setattr(monitor, "_poll_loop", fake_poll_loop)
    monkeypatch.setattr(monitor, "_ws_health_loop", fake_health_loop)

    await monitor.start()
    await asyncio.sleep(0)
    await monitor.stop()

    assert monitor.is_running is False
    assert monitor.is_polling is False
    assert observed == ["poll_loop", "health_loop"]


@pytest.mark.asyncio
async def test_stream_manager_skips_kis_subscriptions_in_kiwoom_mode(monkeypatch) -> None:
    manager = StreamManager()

    async def fail_subscribe(_symbol: str, _market: str = "KRX") -> bool:
        raise AssertionError("KIS websocket subscription should not run in KIWOOM mode")

    monkeypatch.setattr(settings, "BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr(manager._stream_backend, "subscribe", fail_subscribe)

    await manager.update_subscriptions([("005930", "KRX")])

    assert manager.subscription_count == 0
