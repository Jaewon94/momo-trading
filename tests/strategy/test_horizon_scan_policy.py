from strategy.horizon_scan_policy import (
    horizon_scan_profile,
    normalize_scan_horizon,
    normalize_weekday,
)
from strategy.trade_horizon import TradeHorizon


def test_normalize_scan_horizon_defaults_to_short() -> None:
    assert normalize_scan_horizon(None) == TradeHorizon.SHORT
    assert normalize_scan_horizon("bad") == TradeHorizon.SHORT
    assert normalize_scan_horizon("mid") == TradeHorizon.MID


def test_horizon_scan_profile_defaults_by_horizon(monkeypatch) -> None:
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_MAX_CANDIDATES", 30)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_MAX_CANDIDATES", 60)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_MAX_CANDIDATES", 100)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_SELECTED_MAX", 10)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_SELECTED_MAX", 12)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_SELECTED_MAX", 12)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_NEWS_LOOKBACK_HOURS", 168)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_NEWS_LOOKBACK_HOURS", 720)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_DAILY_CANDLE_COUNT", 60)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_DAILY_CANDLE_COUNT", 120)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_DAILY_CANDLE_COUNT", 240)

    short_profile = horizon_scan_profile("SHORT")
    mid_profile = horizon_scan_profile("MID")
    long_profile = horizon_scan_profile("LONG")

    assert short_profile.max_candidates == 30
    assert short_profile.max_selected == 10
    assert short_profile.news_lookback_hours == 24
    assert short_profile.daily_candle_count == 60
    assert mid_profile.max_candidates == 60
    assert mid_profile.max_selected == 12
    assert mid_profile.news_lookback_hours == 168
    assert mid_profile.daily_candle_count == 120
    assert long_profile.max_candidates == 100
    assert long_profile.max_selected == 12
    assert long_profile.news_lookback_hours == 720
    assert long_profile.daily_candle_count == 240


def test_normalize_weekday_rejects_weekends() -> None:
    assert normalize_weekday("fri") == "fri"
    assert normalize_weekday("sun") == "wed"
    assert normalize_weekday(None, default="mon") == "mon"
