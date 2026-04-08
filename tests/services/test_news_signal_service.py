from datetime import timedelta

import pytest

from models.news_item import NewsItem
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_news_signal_service_blocks_on_recent_high_trust_negative_news(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.55)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="DART",
            source_name="금융감독원 전자공시",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="삼성전자 실적 정정 공시",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.1,
            impact_score=1.0,
            trust_score=1.0,
            symbols_csv=",888888,",
            dedupe_hash="gate-neg-1",
        ))
        await session.commit()

        service = NewsSignalService()
        result = await service.evaluate_gate(session, symbol="888888")

    assert result["approved"] is False
    assert result["negative_pressure"] >= 0.55
    assert result["negative_count"] == 1


@pytest.mark.asyncio
async def test_news_signal_service_passes_when_negative_news_is_stale(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.55)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 4)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="REUTERS",
            source_name="Reuters",
            source_tier="B",
            region="GLOBAL",
            official=False,
            language="en",
            title="Old concern fades",
            published_at=now_kst() - timedelta(hours=40),
            sentiment_label="NEGATIVE",
            sentiment_score=0.2,
            impact_score=0.8,
            trust_score=0.8,
            symbols_csv=",999999,",
            dedupe_hash="gate-neg-2",
        ))
        await session.commit()

        service = NewsSignalService()
        result = await service.evaluate_gate(session, symbol="999999")

    assert result["approved"] is True
    assert result["negative_pressure"] < 0.55


@pytest.mark.asyncio
async def test_news_signal_service_is_more_sensitive_for_short_horizon(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.75)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="BLOOMBERG",
            source_name="Bloomberg",
            source_tier="B",
            region="GLOBAL",
            official=False,
            language="en",
            title="Samsung shares slip after demand warning",
            published_at=now_kst() - timedelta(hours=2),
            sentiment_label="NEGATIVE",
            sentiment_score=0.32,
            impact_score=0.75,
            trust_score=0.88,
            symbols_csv=",115930,",
            dedupe_hash="gate-horizon-1",
        ))
        await session.commit()

        service = NewsSignalService()
        short_result = await service.evaluate_gate(session, symbol="115930", horizon="SHORT")
        long_result = await service.evaluate_gate(session, symbol="115930", horizon="LONG")

    assert (short_result["negative_pressure"] / short_result["threshold"]) > (
        long_result["negative_pressure"] / long_result["threshold"]
    )
    assert short_result["threshold"] < long_result["threshold"]


@pytest.mark.asyncio
async def test_news_signal_service_boosts_high_severity_negative_keywords(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.6)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="DART",
            source_name="금융감독원 전자공시",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="삼성전자 회계 조사 관련 정정 공시",
            published_at=now_kst() - timedelta(minutes=30),
            sentiment_label="NEGATIVE",
            sentiment_score=0.41,
            impact_score=0.0,
            trust_score=1.0,
            symbols_csv=",225930,",
            dedupe_hash="gate-severity-1",
        ))
        await session.commit()

        service = NewsSignalService()
        result = await service.evaluate_gate(session, symbol="225930", horizon="MID")

    assert result["approved"] is False
    assert result["contributors"][0]["severity"] >= 1.0
    assert "회계 조사" in result["contributors"][0]["headline"]


@pytest.mark.asyncio
async def test_news_signal_service_surfaces_top_negative_contributors(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.95)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            NewsItem(
                source_code="BLOOMBERG",
                source_name="Bloomberg",
                source_tier="B",
                region="GLOBAL",
                official=False,
                language="en",
                title="Original English headline",
                published_at=now_kst() - timedelta(hours=1),
                sentiment_label="NEGATIVE",
                sentiment_score=0.2,
                impact_score=0.7,
                trust_score=0.88,
                symbols_csv=",335930,",
                metadata_json='{"translated_title":"한글 번역 제목"}',
                dedupe_hash="gate-contrib-1",
            ),
            NewsItem(
                source_code="YONHAP",
                source_name="연합뉴스",
                source_tier="B",
                region="KR",
                official=False,
                language="ko",
                title="삼성전자 공급 차질 우려",
                published_at=now_kst() - timedelta(hours=2),
                sentiment_label="NEGATIVE",
                sentiment_score=0.28,
                impact_score=0.65,
                trust_score=0.82,
                symbols_csv=",335930,",
                dedupe_hash="gate-contrib-2",
            ),
        ])
        await session.commit()

        service = NewsSignalService()
        result = await service.evaluate_gate(session, symbol="335930", horizon="MID")

    assert result["negative_count"] == 2
    assert len(result["contributors"]) == 2
    assert result["contributors"][0]["headline"] == "한글 번역 제목"
    assert result["contributors"][0]["pressure"] >= result["contributors"][1]["pressure"]
    assert result["source_count"] == 2


@pytest.mark.asyncio
async def test_news_signal_service_boosts_recent_off_hours_news(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.95)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)
    monkeypatch.setattr("services.news_signal_service.market_calendar.is_krx_trading_hours", lambda: False)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="DART",
            source_name="금융감독원 전자공시",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="삼성전자 실적 경고 정정 공시",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.35,
            impact_score=0.9,
            trust_score=1.0,
            symbols_csv=",445930,",
            dedupe_hash="gate-session-1",
        ))
        await session.commit()

        service = NewsSignalService()
        result = await service.evaluate_gate(session, symbol="445930", horizon="MID")

    assert result["contributors"][0]["session_multiplier"] > 1.0
    assert result["negative_pressure"] > result["negative_pressure_base"]


@pytest.mark.asyncio
async def test_news_signal_service_applies_related_symbol_relevance_from_metadata(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.95)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="BLOOMBERG",
            source_name="Bloomberg",
            source_tier="B",
            region="GLOBAL",
            official=False,
            language="en",
            title="Supply chain issue hits sector peers",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.24,
            impact_score=0.7,
            trust_score=0.88,
            symbols_csv=",555930,665930,",
            metadata_json='{"primary_symbol":"555930","related_symbol_weights":{"665930":0.55}}',
            dedupe_hash="gate-related-weight-1",
        ))
        await session.commit()

        service = NewsSignalService()
        primary = await service.evaluate_gate(session, symbol="555930", horizon="MID")
        related = await service.evaluate_gate(session, symbol="665930", horizon="MID")

    assert primary["contributors"][0]["symbol_relevance"] == 1.0
    assert related["contributors"][0]["symbol_relevance"] == 0.55
    assert related["negative_pressure"] < primary["negative_pressure"]


@pytest.mark.asyncio
async def test_news_signal_service_applies_sector_relevance_from_metadata(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.95)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="YONHAP",
            source_name="연합뉴스",
            source_tier="B",
            region="KR",
            official=False,
            language="ko",
            title="반도체 업종 전반 공급 차질 우려",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.22,
            impact_score=0.68,
            trust_score=0.82,
            symbols_csv=",775930,885930,",
            metadata_json='{"sector_symbols":["775930"],"sector_relevance":1.14}',
            dedupe_hash="gate-sector-weight-1",
        ))
        await session.commit()

        service = NewsSignalService()
        in_sector = await service.evaluate_gate(session, symbol="775930", horizon="MID")
        out_sector = await service.evaluate_gate(session, symbol="885930", horizon="MID")

    assert in_sector["contributors"][0]["sector_relevance"] == 1.14
    assert out_sector["contributors"][0]["sector_relevance"] == 1.0
    assert in_sector["negative_pressure"] > out_sector["negative_pressure"]


@pytest.mark.asyncio
async def test_news_signal_service_prefers_sector_weights_over_shared_sector_relevance(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 0.95)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="BLOOMBERG",
            source_name="Bloomberg",
            source_tier="B",
            region="GLOBAL",
            official=False,
            language="en",
            title="섹터 전반 리밸류에이션",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.24,
            impact_score=0.72,
            trust_score=0.88,
            symbols_csv=",715930,735420,",
            metadata_json='{"sector_symbols":["715930","735420"],"sector_relevance":1.06,"sector_weights":{"715930":1.08,"735420":1.04}}',
            dedupe_hash="gate-sector-weights-1",
        ))
        await session.commit()

        service = NewsSignalService()
        semiconductor = await service.evaluate_gate(session, symbol="715930", horizon="MID")
        internet = await service.evaluate_gate(session, symbol="735420", horizon="MID")

    assert semiconductor["contributors"][0]["sector_relevance"] == 1.08
    assert internet["contributors"][0]["sector_relevance"] == 1.04
    assert semiconductor["negative_pressure"] > internet["negative_pressure"]


@pytest.mark.asyncio
async def test_news_signal_service_applies_market_reaction_weight_from_metadata(monkeypatch):
    from services.news_signal_service import NewsSignalService

    monkeypatch.setattr("services.news_signal_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_NEGATIVE_BLOCK_THRESHOLD", 1.5)
    monkeypatch.setattr("services.news_signal_service.settings.NEWS_FRESHNESS_HALFLIFE_HOURS", 8)

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            NewsItem(
                source_code="BLOOMBERG",
                source_name="Bloomberg",
                source_tier="B",
                region="GLOBAL",
                official=False,
                language="en",
                title="AI chip outlook weakens",
                published_at=now_kst() - timedelta(hours=1),
                sentiment_label="NEGATIVE",
                sentiment_score=0.24,
                impact_score=0.72,
                trust_score=0.88,
                symbols_csv=",715930,",
                metadata_json='{"market_reaction_weight":1.12,"matched_sector_labels":["AI반도체"],"theme_weights":{"AI반도체":1.06},"sector_symbols":["715930"]}',
                dedupe_hash="gate-market-reaction-1",
            ),
            NewsItem(
                source_code="BLOOMBERG",
                source_name="Bloomberg",
                source_tier="B",
                region="GLOBAL",
                official=False,
                language="en",
                title="AI chip outlook weakens",
                published_at=now_kst() - timedelta(hours=1),
                sentiment_label="NEGATIVE",
                sentiment_score=0.24,
                impact_score=0.72,
                trust_score=0.88,
                symbols_csv=",725930,",
                metadata_json='{"matched_sector_labels":["AI반도체"],"theme_weights":{"AI반도체":1.0},"sector_symbols":["725930"]}',
                dedupe_hash="gate-market-reaction-2",
            ),
        ])
        await session.commit()

        service = NewsSignalService()
        boosted = await service.evaluate_gate(session, symbol="715930", horizon="MID")
        baseline = await service.evaluate_gate(session, symbol="725930", horizon="MID")

    assert boosted["contributors"][0]["market_reaction_weight"] == 1.12
    assert boosted["contributors"][0]["theme_relevance"] == 1.06
    assert boosted["negative_pressure"] > baseline["negative_pressure"]
