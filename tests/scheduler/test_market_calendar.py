from datetime import datetime

from util.time_util import KST
from scheduler.market_calendar import market_calendar


def test_krx_close_is_regular_open_but_not_automated_trading_session():
    dt = datetime(2026, 4, 22, 15, 25, tzinfo=KST)

    assert market_calendar.get_market_session(dt) == "KRX_CLOSE"
    assert market_calendar.is_krx_trading_hours(dt) is True
    assert market_calendar.supports_automated_trading("KRX_CLOSE") is False
    assert market_calendar.is_automated_trading_session(dt) is False


def test_krx_nxt_is_automated_trading_session():
    dt = datetime(2026, 4, 22, 14, 30, tzinfo=KST)

    assert market_calendar.get_market_session(dt) == "KRX_NXT"
    assert market_calendar.is_automated_trading_session(dt) is True
