import json
from datetime import datetime

import pytest
from sqlalchemy import select

from models.news_item import NewsItem
from models.stock import Stock
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_news_enrichment_backfill_applies_disclosure_risk_to_existing_item():
    from services.news_enrichment_backfill_service import news_enrichment_backfill_service

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="KRX",
            source_name="한국거래소 공시/시장공지",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="[유]DKME [정정]유상증자결정",
            url="https://kind.krx.co.kr/example/backfill-risk",
            published_at=datetime.fromisoformat("2026-04-23T09:00:00+09:00"),
            trust_score=1.0,
            dedupe_hash="backfill-risk",
        ))
        await session.commit()

        dry_run = await news_enrichment_backfill_service.process(session, limit=10, apply=False)
        stored = (
            await session.execute(select(NewsItem).where(NewsItem.dedupe_hash == "backfill-risk"))
        ).scalar_one()
        assert stored.sentiment_label is None

        result = await news_enrichment_backfill_service.process(session, limit=10, apply=True)
        item = (
            await session.execute(select(NewsItem).where(NewsItem.dedupe_hash == "backfill-risk"))
        ).scalar_one()

    assert dry_run["changed_count"] == 1
    assert result["changed_count"] == 1
    assert result["risk_classified"] == 1
    assert item.sentiment_label == "NEGATIVE"
    assert item.sentiment_score < 0.5
    assert "risk_classifier" in json.loads(item.metadata_json)


@pytest.mark.asyncio
async def test_news_enrichment_backfill_maps_existing_english_theme_when_stocks_exist():
    from services.news_enrichment_backfill_service import news_enrichment_backfill_service

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="005930", name="삼성전자", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="000660", name="SK하이닉스", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="035420", name="NAVER", market="KOSPI", category="인터넷", is_active=True),
            NewsItem(
                source_code="CNBC",
                source_name="CNBC Markets",
                source_tier="B",
                region="GLOBAL",
                official=False,
                language="en",
                title="AI chip export controls hit semiconductor supply chains",
                summary="Memory makers and advanced chip suppliers face pressure.",
                url="https://www.cnbc.com/example/backfill-topic",
                published_at=datetime.fromisoformat("2026-04-23T09:00:00+09:00"),
                trust_score=0.84,
                metadata_json='{"translation_status": "SKIPPED"}',
                dedupe_hash="backfill-topic",
            ),
        ])
        await session.commit()

        result = await news_enrichment_backfill_service.process(session, limit=10, apply=True)
        item = (
            await session.execute(select(NewsItem).where(NewsItem.dedupe_hash == "backfill-topic"))
        ).scalar_one()

    metadata = json.loads(item.metadata_json)
    assert result["changed_count"] == 1
    assert result["symbols_attached"] == 1
    assert result["topic_mapped"] == 1
    assert set(item.symbols_csv.strip(",").split(",")) == {"005930", "000660"}
    assert metadata["topic_mapper"]["matched_categories"] == ["반도체"]
    assert metadata["translation_status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_news_enrichment_backfill_keeps_explicit_sentiment():
    from services.news_enrichment_backfill_service import news_enrichment_backfill_service

    async with TestAsyncSessionLocal() as session:
        session.add(NewsItem(
            source_code="DART",
            source_name="금융감독원 전자공시",
            source_tier="A",
            region="KR",
            official=True,
            language="ko",
            title="거래정지 가능성 해소 공시",
            url="https://dart.fss.or.kr/example/explicit-sentiment",
            published_at=datetime.fromisoformat("2026-04-23T09:00:00+09:00"),
            sentiment_label="POSITIVE",
            sentiment_score=0.88,
            impact_score=0.3,
            trust_score=1.0,
            dedupe_hash="explicit-sentiment",
        ))
        await session.commit()

        result = await news_enrichment_backfill_service.process(session, limit=10, apply=True)
        item = (
            await session.execute(select(NewsItem).where(NewsItem.dedupe_hash == "explicit-sentiment"))
        ).scalar_one()

    assert result["risk_classified"] == 0
    assert item.sentiment_label == "POSITIVE"
    assert item.sentiment_score == pytest.approx(0.88)
