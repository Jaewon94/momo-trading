from __future__ import annotations

from datetime import datetime, time

from core.config import settings
from scheduler.market_calendar import market_calendar
from util.time_util import now_kst


POST_LIQUIDATION_BUY_BLOCK_REASON = "POST_LIQUIDATION_BUY_BLOCK"


def is_post_liquidation_buy_blocked(now: datetime | None = None) -> bool:
    if not bool(getattr(settings, "POST_LIQUIDATION_BUY_BLOCK_ENABLED", True)):
        return False
    current = now or now_kst()
    if market_calendar.is_krx_holiday(current):
        return False
    if not market_calendar.is_krx_trading_day(current):
        return False
    liquidation_time = time(
        int(getattr(settings, "FORCE_LIQUIDATION_HOUR", 15) or 15),
        int(getattr(settings, "FORCE_LIQUIDATION_MINUTE", 10) or 10),
    )
    return current.time() >= liquidation_time
