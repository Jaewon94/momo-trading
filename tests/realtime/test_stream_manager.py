import asyncio

import pytest

from core.config import settings
from realtime.stream_manager import StreamManager


class FakeRealtimeAdapter:
    def __init__(self) -> None:
        self.callback = None
        self.started = 0
        self.stopped = 0
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[tuple[str, str]] = []
        self.connected = True

    def set_on_price(self, callback) -> None:
        self.callback = callback

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def subscribe(self, symbol: str, market: str = "KRX") -> bool:
        self.subscribed.append((symbol, market))
        return True

    async def unsubscribe(self, symbol: str, market: str = "KRX") -> None:
        self.unsubscribed.append((symbol, market))

    async def listen(self) -> None:
        raise asyncio.CancelledError

    @property
    def subscription_count(self) -> int:
        return len(self.subscribed) - len(self.unsubscribed)

    @property
    def is_connected(self) -> bool:
        return self.connected


def test_stream_manager_set_on_price_delegates_to_adapter() -> None:
    adapter = FakeRealtimeAdapter()
    manager = StreamManager(realtime_adapter=adapter)
    callback = object()

    manager.set_on_price(callback)

    assert adapter.callback is callback


@pytest.mark.asyncio
async def test_stream_manager_updates_subscriptions_via_adapter_even_when_provider_is_kiwoom(
    monkeypatch,
) -> None:
    adapter = FakeRealtimeAdapter()
    manager = StreamManager(realtime_adapter=adapter)

    monkeypatch.setattr(settings, "BROKER_PROVIDER", "KIWOOM")

    await manager.update_subscriptions([("005930", "KRX")])

    assert adapter.subscribed == [("005930", "KRX")]
