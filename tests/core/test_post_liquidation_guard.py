from datetime import datetime

from core.post_liquidation_guard import is_post_liquidation_buy_blocked


def test_post_liquidation_guard_blocks_after_force_liquidation_time(monkeypatch) -> None:
    monkeypatch.setattr("core.post_liquidation_guard.settings.POST_LIQUIDATION_BUY_BLOCK_ENABLED", True)
    monkeypatch.setattr("core.post_liquidation_guard.settings.FORCE_LIQUIDATION_HOUR", 15)
    monkeypatch.setattr("core.post_liquidation_guard.settings.FORCE_LIQUIDATION_MINUTE", 10)
    monkeypatch.setattr("core.post_liquidation_guard.market_calendar.is_krx_holiday", lambda _dt: False)
    monkeypatch.setattr("core.post_liquidation_guard.market_calendar.is_krx_trading_day", lambda _dt: True)

    assert is_post_liquidation_buy_blocked(datetime(2026, 4, 23, 15, 10)) is True
    assert is_post_liquidation_buy_blocked(datetime(2026, 4, 23, 15, 9)) is False


def test_post_liquidation_guard_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setattr("core.post_liquidation_guard.settings.POST_LIQUIDATION_BUY_BLOCK_ENABLED", False)
    monkeypatch.setattr("core.post_liquidation_guard.market_calendar.is_krx_holiday", lambda _dt: False)
    monkeypatch.setattr("core.post_liquidation_guard.market_calendar.is_krx_trading_day", lambda _dt: True)

    assert is_post_liquidation_buy_blocked(datetime(2026, 4, 23, 15, 30)) is False
