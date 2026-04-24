import asyncio
from types import SimpleNamespace

import pytest
from services.news_translation_service import NewsTranslationService


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

    async def fake_generate_news(prompt, tier, system_prompt="", **kwargs):
        assert tier.value == "TIER1"
        assert "Translate the following financial news into Korean" in prompt
        return (
            '{"translated_title":"삼성·LG 상승","translated_summary":"반도체 사이클 개선 기대","sentiment_label":"POSITIVE","sentiment_score":0.72}',
            "CODEX",
        )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fake_generate_news,
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


@pytest.mark.asyncio
async def test_news_translation_service_translate_item_skips_when_selection_disabled(monkeypatch):
    service = NewsTranslationService()

    async def fail_generate_news(*args, **kwargs):
        raise AssertionError("generate_news should not be called when news selection is disabled")

    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fail_generate_news,
    )

    item = {
        "source_code": "CNBC",
        "language": "en",
        "title": "Chip stocks rise on demand recovery",
        "summary": "Demand improved",
        "metadata": {"existing": "value"},
    }

    translated = await service.translate_item(
        item,
        news_selection=SimpleNamespace(
            enabled=False,
            provider="CODEX",
            provider_chain=(),
            provider_model_overrides=None,
        ),
    )

    assert translated == item


@pytest.mark.asyncio
async def test_news_translation_service_skips_foreign_items_when_translation_disabled(monkeypatch):
    service = NewsTranslationService()

    async def fail_generate_news(*args, **kwargs):
        raise AssertionError("generate_news should not be called when foreign translation is disabled")

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_TRANSLATE_FOREIGN_ENABLED", False)
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fail_generate_news,
    )

    item = {
        "source_code": "CNBC",
        "language": "en",
        "title": "Chip stocks rise on demand recovery",
        "summary": "Demand improved",
        "metadata": {"existing": "value"},
    }

    translated = await service.translate_items([item])

    assert translated == [item]


@pytest.mark.asyncio
async def test_news_translation_service_passes_resolved_selection_to_llm_factory(monkeypatch):
    service = NewsTranslationService()
    captured = {}

    async def fake_generate_news(prompt, tier, system_prompt="", *, news_selection=None, **kwargs):
        captured["news_selection"] = news_selection
        return (
            '{"translated_title":"현대차 상승","translated_summary":"현지 판매 호조 기대","sentiment_label":"POSITIVE","sentiment_score":0.61}',
            "CODEX",
        )

    selection = SimpleNamespace(
        enabled=True,
        provider="CODEX",
        provider_chain=(),
        provider_model_overrides=None,
    )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fake_generate_news,
    )

    translated = await service.translate_item(
        {
            "source_code": "INVESTING",
            "language": "en",
            "title": "Hyundai shares rise on stronger outlook",
            "summary": "Investors cheered the stronger guidance.",
        },
        news_selection=selection,
    )

    assert captured["news_selection"] is selection
    assert translated["metadata"]["translation_provider"] == "CODEX"


@pytest.mark.asyncio
async def test_news_translation_service_uses_news_specific_ollama_model(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()
    captured = {}

    async def fake_generate_news(prompt, tier, system_prompt="", **kwargs):
        captured["default_tier"] = tier.value
        return (
            '{"translated_title":"현대차 상승","translated_summary":"현지 판매 호조 기대","sentiment_label":"POSITIVE","sentiment_score":0.61}',
            "OLLAMA",
        )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_MODEL", "qwen2.5:14b")
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fake_generate_news,
    )

    items = await service.translate_items([
        {
            "source_code": "INVESTING",
            "language": "en",
            "title": "Hyundai shares rise on stronger outlook",
            "summary": "Investors cheered the stronger guidance.",
        },
    ])

    assert captured["default_tier"] == "TIER1"
    assert items[0]["metadata"]["translation_provider"] == "OLLAMA"


@pytest.mark.asyncio
async def test_news_translation_service_records_parse_failure_reason(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()

    async def fake_generate(*args, **kwargs):
        return ("not-json-response", "CODEX")

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fake_generate,
    )

    items = await service.translate_items([
        {
            "source_code": "INVESTING",
            "language": "en",
            "title": "Hyundai shares rise on stronger outlook",
            "summary": "Investors cheered the stronger guidance.",
        },
    ])

    assert items[0]["metadata"]["translation_status"] == "FAILED"
    assert items[0]["metadata"]["translation_error"] == "translation JSON parse failed"


@pytest.mark.asyncio
async def test_news_translation_service_parses_repaired_llm_json(monkeypatch):
    service = NewsTranslationService()

    async def fake_generate_news(*args, **kwargs):
        return (
            """
            ```json
            {
              "translated_title": "현대차 상승",
              "translated_summary": "현지 판매 호조 기대가 주가를 지지했다.",
              "sentiment_label": "POSITIVE",
              "sentiment_score": 0.61,
            }
            ```
            """,
            "OLLAMA",
        )

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr(
        "services.news_translation_service.llm_factory.generate_news",
        fake_generate_news,
    )

    items = await service.translate_items([
        {
            "source_code": "INVESTING",
            "language": "en",
            "title": "Hyundai shares rise on stronger outlook",
            "summary": "Investors cheered the stronger guidance.",
        },
    ])

    assert items[0]["metadata"]["translation_status"] == "SUCCESS"
    assert items[0]["metadata"]["translated_title"] == "현대차 상승"
    assert items[0]["sentiment_label"] == "POSITIVE"
    assert items[0]["sentiment_score"] == pytest.approx(0.61)


@pytest.mark.asyncio
async def test_news_translation_service_captures_translation_failures(monkeypatch):
    service = NewsTranslationService()
    captured = {}

    async def fake_generate(*args, **kwargs):
        raise RuntimeError("llm timeout")

    async def fake_capture_exception(**kwargs):
        captured.update(kwargs)
        return {"fingerprint": "fp-1"}

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("services.news_translation_service.llm_factory.generate", fake_generate)
    monkeypatch.setattr("services.news_translation_service.error_capture_service.capture_exception", fake_capture_exception)

    items = await service.translate_items([
        {
            "source_code": "INVESTING",
            "language": "en",
            "title": "Hyundai shares rise on stronger outlook",
            "summary": "Investors cheered the stronger guidance.",
        },
    ])

    assert items[0]["metadata"]["translation_status"] == "FAILED"
    assert captured["component"] == "news_translation"
    assert captured["operation"] == "translate_item"
    assert captured["provider"] == "OLLAMA"
    assert captured["detail"]["source_code"] == "INVESTING"


@pytest.mark.asyncio
async def test_news_translation_service_clears_previous_error_on_success(monkeypatch):
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)

    async def fake_generate(prompt, tier, system_prompt="", **kwargs):
        return (
            '{"translated_title":"번역 제목","translated_summary":"번역 요약","sentiment_label":"NEUTRAL","sentiment_score":0.5}',
            "OLLAMA",
        )

    monkeypatch.setattr("services.news_translation_service.llm_factory.generate_news", fake_generate)

    service = NewsTranslationService()
    items = await service.translate_items([
        {
            "title": "Hello world",
            "summary": "summary",
            "language": "en",
            "metadata": {"translation_error": "ReadTimeout"},
        }
    ])

    assert items[0]["metadata"]["translation_status"] == "SUCCESS"
    assert "translation_error" not in items[0]["metadata"]


@pytest.mark.asyncio
async def test_news_translation_service_serializes_codex_translation_requests(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()
    started: list[str] = []
    release = asyncio.Event()

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CODEX")

    async def fake_translate_item(item, *, news_selection=None):
        assert news_selection is not None
        started.append(item["title"])
        await release.wait()
        copied = dict(item)
        copied["metadata"] = {"translated_title": f"{item['title']} 번역"}
        return copied

    monkeypatch.setattr(service, "_translate_item", fake_translate_item)

    task = asyncio.create_task(service.translate_items([
        {"language": "en", "title": "A", "summary": "1"},
        {"language": "en", "title": "B", "summary": "2"},
        {"language": "en", "title": "C", "summary": "3"},
    ]))

    await asyncio.sleep(0.05)
    assert started == ["A"]
    release.set()
    translated = await task

    assert [item["title"] for item in translated] == ["A", "B", "C"]
    assert translated[0]["metadata"]["translated_title"] == "A 번역"


@pytest.mark.asyncio
async def test_news_translation_service_limits_ollama_to_single_inflight_request(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()
    release = asyncio.Event()
    active = {"count": 0, "max": 0}

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "OLLAMA")

    async def fake_translate_item(item, *, news_selection=None):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await release.wait()
        active["count"] -= 1
        return item

    monkeypatch.setattr(service, "_translate_item", fake_translate_item)

    task = asyncio.create_task(service.translate_items([
        {"language": "en", "title": "A", "summary": "1"},
        {"language": "en", "title": "B", "summary": "2"},
    ]))

    await asyncio.sleep(0.05)
    assert active["max"] == 1

    release.set()
    translated = await task

    assert len(translated) == 2


@pytest.mark.asyncio
async def test_news_translation_service_uses_configured_concurrency_for_non_serialized_provider(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()
    release = asyncio.Event()
    active = {"count": 0, "max": 0}

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_TRANSLATION_CONCURRENCY", 2)

    async def fake_translate_item(item, *, news_selection=None):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await release.wait()
        active["count"] -= 1
        return item

    monkeypatch.setattr(service, "_translate_item", fake_translate_item)

    task = asyncio.create_task(service.translate_items([
        {"language": "en", "title": "A", "summary": "1"},
        {"language": "en", "title": "B", "summary": "2"},
        {"language": "en", "title": "C", "summary": "3"},
    ]))

    await asyncio.sleep(0.05)
    assert active["max"] == 2

    release.set()
    translated = await task

    assert len(translated) == 3


def test_news_translation_service_serializes_codex_and_ollama_translation() -> None:
    service = NewsTranslationService()

    assert service._translation_concurrency_limit("CODEX") == 1
    assert service._translation_concurrency_limit("OLLAMA") == 1


@pytest.mark.asyncio
async def test_news_translation_service_can_disable_claude_session_sharing(monkeypatch):
    from services.news_translation_service import NewsTranslationService

    service = NewsTranslationService()
    events = []

    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_ENABLED", True)
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_LLM_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("services.news_translation_service.settings.NEWS_CLAUDE_SHARE_SESSION", False)

    def fake_pause_session():
        events.append("pause")
        return "session-1"

    def fake_resume_session(session_id):
        events.append(f"resume:{session_id}")

    async def fake_translate_item(item, *, news_selection=None):
        return item

    monkeypatch.setattr("services.news_translation_service.llm_factory.pause_session", fake_pause_session)
    monkeypatch.setattr("services.news_translation_service.llm_factory.resume_session", fake_resume_session)
    monkeypatch.setattr(service, "_translate_item", fake_translate_item)

    translated = await service.translate_items([
        {"language": "en", "title": "A", "summary": "1"},
    ])

    assert len(translated) == 1
    assert events == ["pause", "resume:session-1"]
