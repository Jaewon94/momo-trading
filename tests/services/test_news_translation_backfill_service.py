import pytest

from repositories.news_item_repository import NewsItemRepository
from services.news_ingest_service import news_ingest_service
from services.news_translation_backfill_service import NewsTranslationBackfillService
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_news_translation_backfill_service_translates_pending_foreign_items(monkeypatch):
    async def fake_generate(prompt, tier, system_prompt="", *, provider_chain=None, provider_model_overrides=None, **kwargs):
        return (
            '{"translated_title":"반도체주 상승","translated_summary":"수요 개선 기대","sentiment_label":"POSITIVE","sentiment_score":0.67}',
            "OLLAMA",
        )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("services.news_translation_service.llm_factory.generate", fake_generate)
    monkeypatch.setattr("services.news_translation_backfill_service.NewsTranslationBackfillService.OFF_HOURS_BATCH_SIZE", 32)

    async with TestAsyncSessionLocal() as session:
        await news_ingest_service.ingest_items(session, [{
            "source_code": "CNBC",
            "language": "en",
            "title": "Chip stocks rise on demand recovery",
            "summary": "Demand improved",
            "published_at": "2026-04-08T09:00:00+09:00",
            "url": "https://example.com/cnbc/1",
        }])
        service = NewsTranslationBackfillService()
        summary = await service.process_pending(session, market_hours=False)
        await session.commit()
        items = await NewsItemRepository(session).get_recent(limit=5, source_code="CNBC")

    assert summary["translated"] >= 1
    assert summary["failed"] == 0
    matched = [item for item in items if item.url == "https://example.com/cnbc/1"]
    assert matched
    assert '"translation_status": "SUCCESS"' in (matched[0].metadata_json or "")
    assert '"translated_title": "반도체주 상승"' in (matched[0].metadata_json or "")


@pytest.mark.asyncio
async def test_news_translation_backfill_service_skips_when_llm_disabled(monkeypatch):
    monkeypatch.setattr("services.news_translation_backfill_service.settings.NEWS_LLM_ENABLED", False)

    async with TestAsyncSessionLocal() as session:
        service = NewsTranslationBackfillService()
        summary = await service.process_pending(session, market_hours=True)

    assert summary["status"] == "SKIPPED"
    assert summary["reason"] == "NEWS_LLM_ENABLED disabled"


@pytest.mark.asyncio
async def test_news_translation_backfill_service_skips_when_foreign_translation_disabled(monkeypatch):
    monkeypatch.setattr("services.news_translation_backfill_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_backfill_service.settings.NEWS_TRANSLATE_FOREIGN_ENABLED", False)

    async with TestAsyncSessionLocal() as session:
        service = NewsTranslationBackfillService()
        summary = await service.process_pending(session, market_hours=False)

    assert summary["status"] == "SKIPPED"
    assert summary["reason"] == "NEWS_TRANSLATE_FOREIGN_ENABLED disabled"
