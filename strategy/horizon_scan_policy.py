"""Horizon-specific scanner/news policy helpers."""
from __future__ import annotations

from dataclasses import dataclass

from core.config import settings
from strategy.trade_horizon import TradeHorizon


_VALID_HORIZONS = {TradeHorizon.SHORT, TradeHorizon.MID, TradeHorizon.LONG}
_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri"}


@dataclass(frozen=True)
class HorizonScanProfile:
    horizon: str
    label: str
    max_candidates: int
    max_selected: int
    news_pressure_candidates: int
    news_lookback_hours: int
    news_prompt_items: int
    daily_candle_count: int
    preferred_change_min_pct: float | None
    preferred_change_max_pct: float | None
    prompt_focus: str


def normalize_scan_horizon(value: str | None) -> str:
    key = str(value or "").upper().strip()
    return key if key in _VALID_HORIZONS else TradeHorizon.SHORT


def normalize_weekday(value: str | None, *, default: str = "wed") -> str:
    key = str(value or "").lower().strip()
    return key if key in _VALID_DAYS else default


def horizon_scan_profile(value: str | None) -> HorizonScanProfile:
    horizon = normalize_scan_horizon(value)
    if horizon == TradeHorizon.LONG:
        return HorizonScanProfile(
            horizon=TradeHorizon.LONG,
            label="LONG weekly",
            max_candidates=_positive_int("HORIZON_LONG_MAX_CANDIDATES", 100),
            max_selected=_bounded_int("HORIZON_LONG_SELECTED_MAX", 6, minimum=1, maximum=15),
            news_pressure_candidates=_bounded_int("HORIZON_LONG_NEWS_PRESSURE_CANDIDATES", 30, minimum=0, maximum=100),
            news_lookback_hours=_bounded_int("HORIZON_LONG_NEWS_LOOKBACK_HOURS", 720, minimum=1, maximum=2160),
            news_prompt_items=_bounded_int("HORIZON_LONG_NEWS_PROMPT_ITEMS", 8, minimum=1, maximum=12),
            daily_candle_count=_bounded_int("HORIZON_LONG_DAILY_CANDLE_COUNT", 240, minimum=60, maximum=400),
            preferred_change_min_pct=_float_setting("HORIZON_LONG_PREFERRED_CHANGE_MIN_PCT", -10.0),
            preferred_change_max_pct=_float_setting("HORIZON_LONG_PREFERRED_CHANGE_MAX_PCT", 12.0),
            prompt_focus=(
                "장기 후보: 단기 급등 추격보다 120~240일 추세, 과도하지 않은 가격 위치, "
                "공식 뉴스/공시와 사업 모멘텀을 우선합니다."
            ),
        )
    if horizon == TradeHorizon.MID:
        return HorizonScanProfile(
            horizon=TradeHorizon.MID,
            label="MID daily",
            max_candidates=_positive_int("HORIZON_MID_MAX_CANDIDATES", 60),
            max_selected=_bounded_int("HORIZON_MID_SELECTED_MAX", 8, minimum=1, maximum=15),
            news_pressure_candidates=_bounded_int("HORIZON_MID_NEWS_PRESSURE_CANDIDATES", 20, minimum=0, maximum=100),
            news_lookback_hours=_bounded_int("HORIZON_MID_NEWS_LOOKBACK_HOURS", 168, minimum=1, maximum=2160),
            news_prompt_items=_bounded_int("HORIZON_MID_NEWS_PROMPT_ITEMS", 5, minimum=1, maximum=12),
            daily_candle_count=_bounded_int("HORIZON_MID_DAILY_CANDLE_COUNT", 120, minimum=60, maximum=400),
            preferred_change_min_pct=_float_setting("HORIZON_MID_PREFERRED_CHANGE_MIN_PCT", -4.0),
            preferred_change_max_pct=_float_setting("HORIZON_MID_PREFERRED_CHANGE_MAX_PCT", 14.0),
            prompt_focus=(
                "중기 후보: 20~120일 추세, 눌림 후 회복, 거래량 유지, "
                "7~30일 뉴스/공시 맥락을 함께 봅니다."
            ),
        )
    return HorizonScanProfile(
        horizon=TradeHorizon.SHORT,
        label="SHORT frequent",
        max_candidates=_positive_int("HORIZON_SHORT_MAX_CANDIDATES", int(getattr(settings, "SCANNER_MAX_CANDIDATES", 30) or 30)),
        max_selected=_bounded_int("HORIZON_SHORT_SELECTED_MAX", 8, minimum=1, maximum=15),
        news_pressure_candidates=_bounded_int("HORIZON_SHORT_NEWS_PRESSURE_CANDIDATES", 8, minimum=0, maximum=100),
        news_lookback_hours=_bounded_int("HORIZON_SHORT_NEWS_LOOKBACK_HOURS", int(getattr(settings, "NEWS_LOOKBACK_HOURS", 24) or 24), minimum=1, maximum=2160),
        news_prompt_items=_bounded_int("HORIZON_SHORT_NEWS_PROMPT_ITEMS", 3, minimum=1, maximum=12),
        daily_candle_count=_bounded_int("HORIZON_SHORT_DAILY_CANDLE_COUNT", 60, minimum=20, maximum=400),
        preferred_change_min_pct=None,
        preferred_change_max_pct=_float_setting("HORIZON_SHORT_PREFERRED_CHANGE_MAX_PCT", 18.0),
        prompt_focus=(
            "단기 후보: 현재 장세, 거래량, 급등락, 유동성, 최근 24시간 뉴스 리스크를 빠르게 봅니다."
        ),
    )


def _positive_int(setting_name: str, default: int) -> int:
    return _bounded_int(setting_name, default, minimum=1, maximum=300)


def _bounded_int(setting_name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(getattr(settings, setting_name, default) or default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _float_setting(setting_name: str, default: float) -> float:
    try:
        return float(getattr(settings, setting_name, default))
    except (TypeError, ValueError):
        return float(default)
