from datetime import datetime

import pytest

from tests.conftest import TestAsyncSessionLocal
from models.stock import Stock


@pytest.mark.asyncio
async def test_news_ingest_service_ingests_and_deduplicates_items():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        detailed = await service.ingest_items_detailed(session, [
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
        summary = detailed["summary"]
        source_summaries = detailed["source_summaries"]

    assert summary["received"] == 3
    assert summary["created"] == 2
    assert summary["duplicates"] == 1
    assert source_summaries["DART"] == {"received": 2, "created": 1, "duplicates": 1, "skipped": 0}
    assert source_summaries["REUTERS"] == {"received": 1, "created": 1, "duplicates": 0, "skipped": 0}
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
async def test_news_ingest_service_marks_foreign_translation_skipped_when_disabled(monkeypatch):
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    monkeypatch.setattr("services.news_ingest_service.settings.NEWS_TRANSLATE_FOREIGN_ENABLED", False)
    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        await service.ingest_items(session, [
            {
                "source_code": "CNBC",
                "language": "en",
                "title": "Chip stocks rise on demand recovery",
                "summary": "Demand improved.",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://example.com/cnbc/translation-disabled",
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=5, source_code="CNBC")

    item = next(
        candidate for candidate in candidates
        if candidate.url == "https://example.com/cnbc/translation-disabled"
    )
    assert '"translation_status": "SKIPPED"' in (item.metadata_json or "")
    assert "NEWS_TRANSLATE_FOREIGN_ENABLED disabled" in (item.metadata_json or "")


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


@pytest.mark.asyncio
async def test_news_ingest_service_attaches_symbols_from_translated_metadata():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="005930", name="삼성전자", market="KOSPI", is_active=True),
            Stock(symbol="066570", name="LG전자", market="KOSPI", is_active=True),
        ])
        await session.commit()

        summary = await service.ingest_items(session, [
            {
                "source_code": "INVESTING",
                "title": "Samsung and LG rally on AI demand optimism",
                "summary": "Foreign market commentary",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.investing.com/news/stock-market-news/example",
                "metadata": {
                    "translated_title": "AI 수요 기대에 삼성전자와 LG전자 강세",
                    "translated_summary": "외신에서 삼성전자와 LG전자 수혜를 언급",
                },
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=10, source_code="INVESTING")
        item = next(
            candidate for candidate in candidates
            if candidate.url == "https://www.investing.com/news/stock-market-news/example"
        )

    payload = service.serialize_item(item)

    assert summary["created"] == 1
    assert payload["symbols"] == ["005930", "066570"]
    assert payload["metadata"]["matched_stock_names"] == ["삼성전자", "LG전자"]
    assert payload["metadata"]["primary_symbol"] == "005930"


@pytest.mark.asyncio
async def test_news_ingest_service_enriches_sector_metadata_from_stock_category():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="815930", name="삼성전자", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="810660", name="SK하이닉스", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="852700", name="한미반도체", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="845420", name="NAVER", market="KOSPI", category="인터넷", is_active=True),
        ])
        await session.commit()

        await service.ingest_items(session, [
            {
                "source_code": "YONHAP",
                "title": "삼성전자와 SK하이닉스, AI 반도체 수요 기대",
                "summary": "반도체 업종 전반 투자 심리 개선",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.yna.co.kr/view/example-sector",
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=10, source_code="YONHAP")
        item = next(
            candidate for candidate in candidates
            if candidate.url == "https://www.yna.co.kr/view/example-sector"
        )

    payload = service.serialize_item(item)
    metadata = payload["metadata"]

    assert metadata["sector_label"] == "반도체"
    assert metadata["sector_relevance"] > 1.0
    assert {"815930", "810660", "852700"}.issubset(set(metadata["sector_symbols"]))
    assert "845420" not in metadata["sector_symbols"]


@pytest.mark.asyncio
async def test_news_ingest_service_infers_sector_symbols_from_category_keyword_without_direct_stock_match():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="905930", name="삼성전자", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="900660", name="SK하이닉스", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="942700", name="한미반도체", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="935420", name="NAVER", market="KOSPI", category="인터넷", is_active=True),
        ])
        await session.commit()

        await service.ingest_items(session, [
            {
                "source_code": "REUTERS",
                "title": "반도체 업종 전반 공급 차질 우려",
                "summary": "개별 종목 언급 없이 섹터 전반 리스크를 설명",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.reuters.com/world/example-sector-only",
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=10, source_code="REUTERS")
        item = next(
            candidate for candidate in candidates
            if candidate.url == "https://www.reuters.com/world/example-sector-only"
        )

    payload = service.serialize_item(item)
    metadata = payload["metadata"]

    assert {"905930", "900660", "942700"}.issubset(set(payload["symbols"]))
    assert "935420" not in payload["symbols"]
    assert metadata["matched_sector_labels"] == ["반도체"]
    assert metadata["sector_label"] == "반도체"
    assert {"905930", "900660", "942700"}.issubset(set(metadata["sector_symbols"]))
    assert "935420" not in metadata["sector_symbols"]


@pytest.mark.asyncio
async def test_news_ingest_service_builds_sector_weights_for_multi_sector_articles():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="715930", name="삼성전자", market="KOSPI", category="AI반도체", is_active=True),
            Stock(symbol="710660", name="SK하이닉스", market="KOSPI", category="AI반도체", is_active=True),
            Stock(symbol="735420", name="NAVER", market="KOSPI", category="플랫폼인터넷", is_active=True),
            Stock(symbol="703500", name="카카오", market="KOSPI", category="플랫폼인터넷", is_active=True),
        ])
        await session.commit()

        await service.ingest_items(session, [
            {
                "source_code": "BLOOMBERG",
                "title": "AI반도체와 플랫폼인터넷 업종 전반 밸류에이션 재평가",
                "summary": "개별 종목 언급 없이 두 업종 전반 기대가 커졌다.",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.bloomberg.com/news/articles/example-multi-sector",
            },
        ])
        await session.commit()
        candidates = await NewsItemRepository(session).get_recent(limit=10, source_code="BLOOMBERG")
        item = next(
            candidate for candidate in candidates
            if candidate.url == "https://www.bloomberg.com/news/articles/example-multi-sector"
        )

    payload = service.serialize_item(item)
    metadata = payload["metadata"]

    assert metadata["matched_sector_labels"] == ["AI반도체", "플랫폼인터넷"]
    assert {"715930", "710660", "735420", "703500"}.issubset(set(metadata["sector_symbols"]))
    assert metadata["sector_weights"]["715930"] == pytest.approx(1.08)
    assert metadata["sector_weights"]["735420"] == pytest.approx(1.04)
    assert metadata["theme_weights"]["AI반도체"] >= metadata["theme_weights"]["플랫폼인터넷"]
    assert metadata["market_reaction_weight"] > 1.0


@pytest.mark.asyncio
async def test_news_ingest_service_classifies_disclosure_risk_on_ingest():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        await service.ingest_items(session, [
            {
                "source_code": "DART",
                "title": "신한제11호스팩 · 주권매매거래정지 (상장폐지 사유발생)",
                "published_at": "2026-04-05T09:01:00+09:00",
                "symbols": ["452980"],
                "url": "https://dart.fss.or.kr/example/trading-suspension",
                "metadata": {
                    "report_nm": "주권매매거래정지 (상장폐지 사유발생)",
                },
            },
        ])
        await session.commit()
        item = (
            await NewsItemRepository(session).get_recent(limit=1, source_code="DART")
        )[0]

    payload = service.serialize_item(item)

    assert item.sentiment_label == "NEGATIVE"
    assert item.sentiment_score <= 0.16
    assert item.impact_score >= 0.9
    assert "trading_suspension" in payload["metadata"]["risk_classifier"]["reason_codes"]
    assert "delisting_risk" in payload["metadata"]["risk_classifier"]["reason_codes"]


@pytest.mark.asyncio
async def test_news_ingest_service_maps_english_policy_theme_to_korean_sector_without_translation():
    from repositories.news_item_repository import NewsItemRepository
    from services.news_ingest_service import NewsIngestService

    service = NewsIngestService()

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="605930", name="삼성전자", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="600660", name="SK하이닉스", market="KOSPI", category="반도체", is_active=True),
            Stock(symbol="635420", name="NAVER", market="KOSPI", category="인터넷", is_active=True),
        ])
        await session.commit()

        await service.ingest_items(session, [
            {
                "source_code": "BLOOMBERG",
                "language": "en",
                "title": "AI chip export controls hit semiconductor supply chains",
                "summary": "New restrictions weigh on advanced chip suppliers.",
                "published_at": "2026-04-05T09:01:00+09:00",
                "url": "https://www.bloomberg.com/news/articles/example-ai-chip-export-controls",
            },
        ])
        await session.commit()
        item = (
            await NewsItemRepository(session).get_recent(limit=1, source_code="BLOOMBERG")
        )[0]

    payload = service.serialize_item(item)
    metadata = payload["metadata"]

    assert {"605930", "600660"}.issubset(set(payload["symbols"]))
    assert "635420" not in payload["symbols"]
    assert metadata["matched_sector_labels"] == ["반도체"]
    assert "english_theme_keywords" in metadata["topic_mapper"]["reason_codes"]
