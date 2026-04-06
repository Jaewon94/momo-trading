import pytest

from analysis.sentiment.news_analyzer import NewsAnalyzer


@pytest.mark.asyncio
async def test_news_analyzer_returns_neutral_when_disabled(monkeypatch):
    analyzer = NewsAnalyzer()
    monkeypatch.setattr("analysis.sentiment.news_analyzer.settings.NEWS_LLM_ENABLED", False)

    result = await analyzer.analyze_sentiment("삼성전자", ["headline"])

    assert result["sentiment"] == "NEUTRAL"
    assert "비활성화" in result["summary"]


@pytest.mark.asyncio
async def test_news_analyzer_uses_news_provider_override(monkeypatch):
    analyzer = NewsAnalyzer()
    monkeypatch.setattr("analysis.sentiment.news_analyzer.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("analysis.sentiment.news_analyzer.settings.NEWS_LLM_PROVIDER", "CODEX")

    observed = {}

    async def fake_generate_manual(prompt, default_tier, manual_provider_override):
        observed["default_tier"] = default_tier.value
        observed["provider"] = manual_provider_override
        return (
            '{"sentiment":"POSITIVE","score":0.8,"summary":"긍정 뉴스"}',
            "CODEX",
        )

    monkeypatch.setattr(
        "analysis.sentiment.news_analyzer.llm_factory.generate_manual",
        fake_generate_manual,
    )

    result = await analyzer.analyze_sentiment("삼성전자", ["좋은 실적 발표"])

    assert result["sentiment"] == "POSITIVE"
    assert observed["provider"] == "CODEX"
    assert observed["default_tier"] == "TIER1"
