from datetime import timedelta

import pytest

from models.news_item import NewsItem
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_news_context_service_builds_symbol_prompt_with_soft_negative_hint(monkeypatch):
    from services.news_context_service import NewsContextService

    monkeypatch.setattr("services.news_context_service.settings.NEWS_LOOKBACK_HOURS", 24)
    monkeypatch.setattr("services.news_context_service.settings.NEWS_MAX_ITEMS_PER_SYMBOL", 20)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="DART",
            source_name="금융감독원 전자공시",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="삼성전자 정정 공시",
            summary="단기 리스크 점검 필요",
            published_at=now_kst() - timedelta(hours=1),
            sentiment_label="NEGATIVE",
            sentiment_score=0.2,
            impact_score=0.9,
            trust_score=1.0,
            symbols_csv=",005930,",
            dedupe_hash="news-context-symbol-1",
        ))
        await session.commit()

        result = await NewsContextService().build_for_symbol(
            session,
            symbol="005930",
            name="삼성전자",
        )

    assert result["available"] is True
    assert result["negative_count"] == 1
    assert result["confidence_hint"] < 0
    assert "뉴스 역할: 차트/수급/리스크 판단을 보조" in result["prompt"]
    assert "뉴스만으로 BUY/SELL을 결정하지 마세요" in result["prompt"]
    assert result["items"][0]["match_type"] == "symbol"


@pytest.mark.asyncio
async def test_news_context_service_falls_back_to_domestic_name_match(monkeypatch):
    from services.news_context_service import NewsContextService

    monkeypatch.setattr("services.news_context_service.settings.NEWS_LOOKBACK_HOURS", 24)

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="KRX",
            source_name="한국거래소",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="[코]디케이티 신규시설투자등",
            summary="디케이티 생산능력 확대 공시",
            published_at=now_kst() - timedelta(hours=2),
            sentiment_label="POSITIVE",
            sentiment_score=0.75,
            impact_score=0.7,
            trust_score=0.95,
            symbols_csv="",
            dedupe_hash="news-context-name-1",
        ))
        await session.commit()

        result = await NewsContextService().build_for_symbol(
            session,
            symbol="290550",
            name="디케이티",
        )

    assert result["available"] is True
    assert result["match_source"] == "symbol_or_name"
    assert result["positive_count"] == 1
    assert result["confidence_hint"] == 0.03
    assert result["items"][0]["match_type"] == "name"


@pytest.mark.asyncio
async def test_news_context_service_returns_neutral_prompt_without_recent_news(monkeypatch):
    from services.news_context_service import NewsContextService

    monkeypatch.setattr("services.news_context_service.settings.NEWS_LOOKBACK_HOURS", 24)

    async with TestAsyncSessionLocal() as session:
        result = await NewsContextService().build_for_symbol(
            session,
            symbol="123456",
            name="없는종목",
        )

    assert result["available"] is False
    assert result["confidence_hint"] == 0.0
    assert "뉴스 판단: 중립" in result["prompt"]
