import pytest

from core.events import EventType
from realtime.event_detector import EventDetector


@pytest.mark.asyncio
async def test_event_detector_publishes_price_update_but_not_order_trigger_during_close_auction(monkeypatch):
    detector = EventDetector()
    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda: False)
    monkeypatch.setattr("realtime.event_detector.event_bus.publish", fake_publish)

    detector.set_thresholds("005930", stop_loss=70_000, take_profit=75_000)

    await detector.on_price_update({
        "symbol": "005930",
        "price": 69_500,
        "volume": 100,
        "change_rate": -4.0,
    })

    assert [event.type for event in published] == [EventType.PRICE_UPDATE]
    assert published[0].data["order_allowed"] is False


@pytest.mark.asyncio
async def test_event_detector_publishes_stop_loss_during_automated_trading_session(monkeypatch):
    detector = EventDetector()
    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda: True)
    monkeypatch.setattr("realtime.event_detector.event_bus.publish", fake_publish)

    detector.set_thresholds("005930", stop_loss=70_000)

    await detector.on_price_update({
        "symbol": "005930",
        "price": 69_500,
        "volume": 100,
        "change_rate": -1.0,
    })

    assert [event.type for event in published] == [
        EventType.PRICE_UPDATE,
        EventType.STOP_LOSS_HIT,
    ]
