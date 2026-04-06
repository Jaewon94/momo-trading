import pytest


@pytest.mark.asyncio
async def test_news_translation_service_skips_korean_items(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()

    called = {"count": 0}

    async def fake_translate_item(item):
        called["count"] += 1
        return item

    monkeypatch.setattr(service, "_translate_item", fake_translate_item)

    items = await service.translate_items([
        {"source_code": "YONHAP", "language": "ko", "title": "국내 뉴스", "summary": "요약"},
    ])

    assert called["count"] == 0
    assert items[0]["title"] == "국내 뉴스"


@pytest.mark.asyncio
async def test_news_translation_service_adds_korean_translation_metadata(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()

    async def fake_generate_manual(prompt, default_tier, manual_provider_override):
        assert manual_provider_override == "CODEX"
        assert default_tier.value == "TIER1"
        assert "Translate the following financial news into Korean" in prompt
        return (
            '{"translated_title":"삼성·LG 상승","translated_summary":"반도체 사이클 개선 기대","sentiment_label":"POSITIVE","sentiment_score":0.72}',
            "CODEX",
        )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_manual",
        fake_generate_manual,
    )

    items = await service.translate_items([
        {
            "source_code": "BLOOMBERG",
            "language": "en",
            "title": "Samsung and LG Rally as Chip Cycle Improves",
            "summary": "Semiconductor demand outlook improved.",
            "metadata": {"keywords": ["chips"]},
        },
    ])

    metadata = items[0]["metadata"]
    assert metadata["translated_title"] == "삼성·LG 상승"
    assert metadata["translated_summary"] == "반도체 사이클 개선 기대"
    assert metadata["translation_provider"] == "CODEX"
    assert items[0]["sentiment_label"] == "POSITIVE"
    assert items[0]["sentiment_score"] == pytest.approx(0.72)

