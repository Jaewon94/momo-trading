from datetime import datetime

import pytest

from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_news_ingest_service_ingests_and_deduplicates_items():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        summary = await service.ingest_items(session, [
            {
                "source_code": "DART",
                "title": "삼성전자 주요사항보고서 제출",
                "published_at": "2026-04-05T09:01:00+09:00",
                "symbols": ["A777777"],
                "url": "https://dart.fss.or.kr/example/1",
            },
            {
                "source_code": "DART",
                "title": "삼성전자 주요사항보고서 제출",
                "published_at": "2026-04-05T09:01:00+09:00",
                "symbols": ["777777"],
                "url": "https://dart.fss.or.kr/example/1",
            },
            {
                "source_code": "REUTERS",
                "title": "Chip demand lifts Samsung supplier outlook",
                "published_at": datetime.fromisoformat("2026-04-05T08:10:00+09:00"),
                "symbols": ["777777", "A777777"],
                "url": "https://www.reuters.com/example/2",
            },
        ])
        await session.commit()

        repo = NewsItemRepository(session)
        stored = await repo.get_recent(limit=10, symbol="777777")

    assert summary["received"] == 3
    assert summary["created"] == 2
    assert summary["duplicates"] == 1
    assert len(stored) == 2

    latest = stored[0]
    assert latest.source_code in {"DART", "REUTERS"}
    assert ",777777," in latest.symbols_csv

    dart_item = next(item for item in stored if item.source_code == "DART")
    assert dart_item.source_tier == "A"
    assert dart_item.region == "KR"
    assert dart_item.trust_score == pytest.approx(1.0)


def test_news_ingest_service_catalog_includes_domestic_and_global_sources():
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()
    catalog = service.get_source_catalog(include_foreign=True)

    codes = {item["code"] for item in catalog}
    assert "DART" in codes
    assert "KRX" in codes
    assert "REUTERS" in codes

    dart = next(item for item in catalog if item["code"] == "DART")
    assert dart["tier"] == "A"
    assert dart["official"] is True


@pytest.mark.asyncio
async def test_news_ingest_service_serialize_item_prefers_translated_display_fields():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        await service.ingest_items(session, [
            {
                "source_code": "BLOOMBERG",
                "title": "Samsung and LG Rally as Chip Cycle Improves",
                "summary": "Semiconductor demand outlook improved.",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.bloomberg.com/news/articles/example",
                "metadata": {
                    "translated_title": "반도체 사이클 개선에 삼성·LG 강세",
                    "translated_summary": "반도체 수요 기대가 개선됐다는 내용",
                    "translation_provider": "CODEX",
                },
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=10, source_code="BLOOMBERG")
        item = next(
            candidate for candidate in candidates
            if candidate.url == "https://www.bloomberg.com/news/articles/example"
        )

    payload = service.serialize_item(item)

    assert payload["display_title"] == "반도체 사이클 개선에 삼성·LG 강세"
    assert payload["display_summary"] == "반도체 수요 기대가 개선됐다는 내용"
    assert payload["original_title"] == "Samsung and LG Rally as Chip Cycle Improves"
    assert payload["original_summary"] == "Semiconductor demand outlook improved."
