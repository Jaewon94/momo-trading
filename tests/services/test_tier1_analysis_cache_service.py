from analysis.chart_analyzer import ChartAnalysisResult
from services.tier1_analysis_cache_service import Tier1AnalysisCacheService


def test_tier1_analysis_cache_returns_copy_for_equivalent_key(monkeypatch) -> None:
    service = Tier1AnalysisCacheService()
    monkeypatch.setattr("services.tier1_analysis_cache_service.settings.TIER1_ANALYSIS_CACHE_ENABLED", True, raising=False)
    monkeypatch.setattr("services.tier1_analysis_cache_service.settings.TIER1_ANALYSIS_CACHE_TTL_SEC", 60, raising=False)

    key = service.build_key(
        symbol="A005930",
        strategy_type="stable_short",
        current_price=70_000,
        chart_result=ChartAnalysisResult(
            indicators={"rsi_14": 52.123},
            signal_summary={"direction": "BULLISH", "confidence": 0.7123, "net_score": 5},
        ),
        portfolio_snapshot={"holding_symbols": []},
        market_regime="SIDEWAYS",
        feedback_context="history",
    )

    service.put(key, {"recommendation": "HOLD", "confidence": 0.7, "key_factors": ["a"]})
    cached = service.get(key)
    assert cached == {"recommendation": "HOLD", "confidence": 0.7, "key_factors": ["a"]}

    cached["key_factors"].append("mutated")
    assert service.get(key) == {"recommendation": "HOLD", "confidence": 0.7, "key_factors": ["a"]}


def test_tier1_analysis_cache_key_changes_when_feedback_context_changes() -> None:
    service = Tier1AnalysisCacheService()
    kwargs = {
        "symbol": "005930",
        "strategy_type": "STABLE_SHORT",
        "current_price": 70_000,
        "chart_result": ChartAnalysisResult(signal_summary={"direction": "NEUTRAL", "confidence": 0.1}),
        "portfolio_snapshot": {"holding_symbols": []},
        "market_regime": "SIDEWAYS",
    }

    assert service.build_key(**kwargs, feedback_context="a") != service.build_key(**kwargs, feedback_context="b")
