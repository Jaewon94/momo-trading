import asyncio

import pytest

from core.config import settings
from realtime.stream_manager import StreamManager, SubscriptionPriority, SubscriptionRequest


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


@pytest.mark.asyncio
async def test_stream_manager_prioritizes_held_positions_over_new_candidates_when_limit_exceeded() -> None:
    adapter = FakeRealtimeAdapter()
    manager = StreamManager(realtime_adapter=adapter)

    candidates = [
        SubscriptionRequest(symbol=f"{idx:06d}", market="KRX", priority=SubscriptionPriority.NEW_CANDIDATE)
        for idx in range(1, 43)
    ]
    held = [
        SubscriptionRequest(symbol="900001", market="KRX", priority=SubscriptionPriority.HELD_POSITION),
        SubscriptionRequest(symbol="900002", market="KRX", priority=SubscriptionPriority.HELD_POSITION),
    ]

    await manager.update_subscriptions(candidates + held)

    subscribed_symbols = [symbol for symbol, _market in adapter.subscribed]

    assert len(subscribed_symbols) == manager.MAX_SUBSCRIPTIONS
    assert "900001" in subscribed_symbols
    assert "900002" in subscribed_symbols
    assert "000040" not in subscribed_symbols
    assert "000041" not in subscribed_symbols
    assert "000042" not in subscribed_symbols
    assert manager.polling_fallback_symbols == ["000040", "000041", "000042"]
    assert manager.skipped_subscription_count == 3


@pytest.mark.asyncio
async def test_stream_manager_direct_subscribe_evicts_lower_priority_candidate_for_held_position() -> None:
    adapter = FakeRealtimeAdapter()
    manager = StreamManager(realtime_adapter=adapter)

    await manager.update_subscriptions([
        SubscriptionRequest(symbol=f"{idx:06d}", market="KRX", priority=SubscriptionPriority.NEW_CANDIDATE)
        for idx in range(1, 42)
    ])

    await manager.subscribe_symbols([
        SubscriptionRequest(symbol="900001", market="KRX", priority=SubscriptionPriority.HELD_POSITION)
    ])

    subscribed_symbols = [symbol for symbol, _market in adapter.subscribed]
    unsubscribed_symbols = [symbol for symbol, _market in adapter.unsubscribed]

    assert "900001" in subscribed_symbols
    assert "000041" in unsubscribed_symbols
    assert manager.polling_fallback_symbols == ["000041"]
