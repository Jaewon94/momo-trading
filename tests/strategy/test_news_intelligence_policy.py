from strategy.news_intelligence_policy import (
    after_hours_news_research_policy,
    news_event_policies,
    news_horizon_policy,
    news_severity_keywords,
)


def test_news_horizon_policy_tracks_scan_windows(monkeypatch) -> None:
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_NEWS_LOOKBACK_HOURS", 168)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_NEWS_LOOKBACK_HOURS", 720)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_NEWS_PROMPT_ITEMS", 3)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_NEWS_PROMPT_ITEMS", 5)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_NEWS_PROMPT_ITEMS", 8)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_SHORT_NEWS_PRESSURE_CANDIDATES", 8)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_MID_NEWS_PRESSURE_CANDIDATES", 20)
    monkeypatch.setattr("strategy.horizon_scan_policy.settings.HORIZON_LONG_NEWS_PRESSURE_CANDIDATES", 30)

    short_policy = news_horizon_policy("SHORT")
    mid_policy = news_horizon_policy("MID")
    long_policy = news_horizon_policy("LONG")

    assert short_policy.threshold_multiplier == 0.9
    assert short_policy.freshness_multiplier == 0.7
    assert short_policy.lookback_hours == 24
    assert short_policy.prompt_items == 3
    assert short_policy.pressure_candidates == 8
    assert mid_policy.threshold_multiplier == 1.0
    assert mid_policy.lookback_hours == 168
    assert mid_policy.prompt_items == 5
    assert mid_policy.pressure_candidates == 20
    assert long_policy.threshold_multiplier == 1.12
    assert long_policy.freshness_multiplier == 1.35
    assert long_policy.lookback_hours == 720
    assert long_policy.prompt_items == 8
    assert long_policy.pressure_candidates == 30


def test_news_policy_declares_material_event_taxonomy() -> None:
    categories = {policy.category: policy for policy in news_event_policies()}

    assert categories["guidance"].default_materiality > categories["market_noise"].default_materiality
    assert categories["regulatory"].default_materiality >= 0.9
    assert categories["market_noise"].treat_as_noise_when_unlinked is True
    assert "정정 공시" in {keyword for keyword, _weight in news_severity_keywords()}


def test_after_hours_research_policy_is_cost_gated_by_default() -> None:
    policy = after_hours_news_research_policy()

    assert policy.llm_default_enabled is False
    assert policy.max_llm_batches == 1
    assert policy.require_citations is True
    assert policy.require_no_trade_orders is True
    assert policy.require_shadow_metrics is True
