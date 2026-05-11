from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from analysis.chart_analyzer import ChartAnalysisResult
from services.deterministic_tier1_fast_gate_service import DeterministicTier1FastGateService


def test_fast_gate_skips_late_day_overheated_non_holding(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
        True,
        raising=False,
    )
    service = DeterministicTier1FastGateService()
    daily_df = pd.DataFrame(
        [
            {"close": 1000, "volume": 1000},
            {"close": 1100, "volume": 1200},
            {"close": 1150, "volume": 1500},
            {"close": 1200, "volume": 1400},
            {"close": 1300, "volume": 1300},
            {"close": 1500, "volume": 1200},
        ]
    )
    chart = ChartAnalysisResult(
        signal_summary={"direction": "NEUTRAL", "confidence": 0.2},
        trend=SimpleNamespace(direction="BULLISH", score=35, intraday={"direction": "BULLISH"}),
    )

    decision = service.evaluate(
        symbol="006340",
        stock_info={"symbol": "006340", "change_rate": 28.2},
        current_price=15_865,
        daily_df=daily_df,
        minute_df=None,
        chart_result=chart,
        portfolio_snapshot={"holding_symbols": []},
        now=datetime(2026, 4, 30, 14, 46),
    )

    assert decision.should_skip_tier1 is True
    assert decision.action == "HOLD"
    assert decision.code == "FAST_GATE_HOLD"
    assert decision.detail["after_cutoff"] is True


def test_fast_gate_continues_held_symbol_even_when_late() -> None:
    service = DeterministicTier1FastGateService()
    chart = ChartAnalysisResult(
        signal_summary={"direction": "BEARISH", "confidence": 0.9},
        trend=SimpleNamespace(direction="BEARISH", score=-40, intraday={"direction": "BEARISH"}),
    )

    decision = service.evaluate(
        symbol="A005930",
        stock_info={"symbol": "005930", "change_rate": 29.0},
        current_price=70_000,
        daily_df=pd.DataFrame([{"close": 70_000, "volume": 1000}] * 6),
        minute_df=None,
        chart_result=chart,
        portfolio_snapshot={"holding_symbols": ["005930"]},
        now=datetime(2026, 4, 30, 14, 55),
    )

    assert decision.should_skip_tier1 is False
    assert decision.code == "HOLDING_OR_SELL"


def test_fast_gate_allows_bull_momentum_candidate_below_normal_score(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_BULL_MOMENTUM_ALLOW_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_MIN_CONTINUE_SCORE",
        55.0,
        raising=False,
    )
    service = DeterministicTier1FastGateService()
    chart = ChartAnalysisResult(
        indicators={"macd_histogram": -1.0, "rsi_14": 72.0},
        signal_summary={"direction": "NEUTRAL", "confidence": 0.3},
        trend=SimpleNamespace(direction="NEUTRAL", score=5, intraday={"direction": "BEARISH"}),
    )
    daily_df = pd.DataFrame(
        [
            {"close": 1000, "volume": 1000},
            {"close": 1010, "volume": 1200},
            {"close": 1020, "volume": 1300},
            {"close": 1030, "volume": 1400},
            {"close": 1040, "volume": 1500},
            {"close": 1120, "volume": 1600},
        ]
    )

    decision = service.evaluate(
        symbol="006340",
        stock_info={"symbol": "006340", "change_rate": 9.5},
        current_price=11_200,
        daily_df=daily_df,
        minute_df=None,
        chart_result=chart,
        portfolio_snapshot={"holding_symbols": []},
        market_regime="BULL",
        now=datetime(2026, 4, 30, 13, 10),
    )

    assert decision.should_skip_tier1 is False
    assert decision.code == "FAST_GATE_CONTINUE"
    assert decision.detail["score"] < decision.detail["threshold"]
    assert decision.detail["bull_momentum_allow"] is True


def test_fast_gate_allows_strong_bull_momentum_despite_soft_bearish_daily(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_BULL_MOMENTUM_MIN_SCORE",
        35.0,
        raising=False,
    )
    service = DeterministicTier1FastGateService()
    chart = ChartAnalysisResult(
        indicators={"macd_histogram": -0.5, "rsi_14": 61.0},
        signal_summary={"direction": "NEUTRAL", "confidence": 0.25},
        trend=SimpleNamespace(direction="BEARISH", score=-12, intraday={"direction": "NEUTRAL"}),
    )
    daily_df = pd.DataFrame([{"close": 1000 + i * 10, "volume": 1000 + i * 50} for i in range(6)])

    decision = service.evaluate(
        symbol="010170",
        stock_info={"symbol": "010170", "change_rate": 13.85},
        current_price=20_800,
        daily_df=daily_df,
        minute_df=None,
        chart_result=chart,
        portfolio_snapshot={"holding_symbols": []},
        market_regime="BULL",
        now=datetime(2026, 5, 7, 10, 45),
    )

    assert decision.should_skip_tier1 is False
    assert decision.detail["score"] == 42.0
    assert decision.detail["bull_momentum_allow"] is True


def test_fast_gate_uses_conservative_baseline_for_conservative_appetite(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.RISK_APPETITE",
        "CONSERVATIVE",
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_MIN_CONTINUE_SCORE",
        55.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT",
        27.0,
        raising=False,
    )

    profile = DeterministicTier1FastGateService._risk_profile()

    assert profile.risk_appetite == "CONSERVATIVE"
    assert profile.min_continue_score == 55.0
    assert profile.overheat_change_pct == 27.0
    assert profile.hard_late_overheat_change_pct == 20.0


def test_fast_gate_relaxes_effective_thresholds_for_moderate_and_aggressive(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_MIN_CONTINUE_SCORE",
        55.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT",
        27.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_BULL_MOMENTUM_MIN_CHANGE_PCT",
        7.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_BULL_MOMENTUM_MIN_SCORE",
        35.0,
        raising=False,
    )

    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.RISK_APPETITE",
        "MODERATE",
        raising=False,
    )
    moderate = DeterministicTier1FastGateService._risk_profile()

    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.RISK_APPETITE",
        "AGGRESSIVE",
        raising=False,
    )
    aggressive = DeterministicTier1FastGateService._risk_profile()

    assert moderate.min_continue_score == 48.0
    assert moderate.overheat_change_pct == 29.0
    assert moderate.bull_momentum_min_change_pct == 5.0
    assert moderate.bull_momentum_min_score == 30.0

    assert aggressive.min_continue_score == 42.0
    assert aggressive.overheat_change_pct == 31.0
    assert aggressive.bull_momentum_min_change_pct == 3.0
    assert aggressive.bull_momentum_min_score == 25.0


def test_fast_gate_moderate_continues_candidate_conservative_would_skip(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_MIN_CONTINUE_SCORE",
        55.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT",
        27.0,
        raising=False,
    )
    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.TIER1_FAST_GATE_BULL_MOMENTUM_ALLOW_ENABLED",
        False,
        raising=False,
    )
    service = DeterministicTier1FastGateService()
    chart = ChartAnalysisResult(
        indicators={"macd_histogram": -1.0, "rsi_14": 55.0},
        signal_summary={"direction": "NEUTRAL", "confidence": 0.3},
        trend=SimpleNamespace(direction="NEUTRAL", score=0, intraday={"direction": "NEUTRAL"}),
    )
    daily_df = pd.DataFrame([{"close": 1000 + i, "volume": 1000 + i * 100} for i in range(6)])

    kwargs = dict(
        symbol="005930",
        stock_info={"symbol": "005930", "change_rate": 2.0},
        current_price=70_000,
        daily_df=daily_df,
        minute_df=None,
        chart_result=chart,
        portfolio_snapshot={"holding_symbols": []},
        market_regime="SIDEWAYS",
        now=datetime(2026, 5, 7, 12, 0),
    )

    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.RISK_APPETITE",
        "CONSERVATIVE",
        raising=False,
    )
    conservative = service.evaluate(**kwargs)

    monkeypatch.setattr(
        "services.deterministic_tier1_fast_gate_service.settings.RISK_APPETITE",
        "MODERATE",
        raising=False,
    )
    moderate = service.evaluate(**kwargs)

    assert conservative.detail["score"] == 52.0
    assert conservative.detail["threshold"] == 55.0
    assert conservative.should_skip_tier1 is True

    assert moderate.detail["score"] == 52.0
    assert moderate.detail["threshold"] == 48.0
    assert moderate.should_skip_tier1 is False
