import pytest
import asyncio


async def _passthrough_translate_items(items):
    return items


def _mock_empty_news_sources(monkeypatch, *service_names):
    """테스트가 다루지 않는 뉴스 소스를 빈 결과로 모킹해 실제 HTTP 호출을 차단한다."""
    for name in service_names:
        async def _fetch(*, limit, _name=name):
            return []
        monkeypatch.setattr(
            f"services.news_polling_service.{name}.fetch_recent_news",
            _fetch,
        )


@pytest.mark.asyncio
async def test_news_polling_service_publishes_events_for_created_items(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "test-key")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)

    published = []

    async def fake_fetch_recent_disclosures(*, days, page_count, corp_code=None):
        assert days == 1
        assert page_count == 25
        return [
            {
                "source_code": "DART",
                "title": "삼성전자 공시",
                "published_at": "2026-04-05T09:00:00+09:00",
                "symbols": ["005930"],
                "url": "https://dart.example/1",
                "external_id": "1",
            }
        ]

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return [
            {
                "source_code": "KRX",
                "title": "SK하이닉스 주요사항보고서",
                "published_at": "2026-04-05T09:05:00+09:00",
                "symbols": ["000660"],
                "url": "https://kind.krx.co.kr/example/2",
                "external_id": "2",
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        return {
            "summary": {"received": 2, "created": 2, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "DART",
                    "title": "삼성전자 공시",
                    "published_at": "2026-04-05T09:00:00+09:00",
                    "symbols": ["005930"],
                },
                {
                    "source_code": "KRX",
                    "title": "SK하이닉스 주요사항보고서",
                    "published_at": "2026-04-05T09:05:00+09:00",
                    "symbols": ["000660"],
                }
            ],
        }

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.open_dart_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=True)

    assert summary["created"] == 2
    assert summary["published_events"] == 2
    assert published[0].data["symbols"] == ["005930"]
    assert published[1].data["symbols"] == ["000660"]


@pytest.mark.asyncio
async def test_news_polling_service_skips_without_api_key(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)
    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["received"] == 0
    assert summary["created"] == 0
    assert summary["duplicates"] == 0
    assert summary["skipped"] == 0


@pytest.mark.asyncio
async def test_news_polling_service_includes_yonhap_when_domestic_media_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_yonhap_news(_session, *, limit):
        assert limit == 25
        return [
            {
                "source_code": "YONHAP",
                "title": "삼성전자 AI 투자 확대",
                "published_at": "2026-04-05T09:10:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.yonhapnewstv.co.kr/news/1",
                "external_id": "AKR202604050001",
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "YONHAP"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "YONHAP",
                    "title": "삼성전자 AI 투자 확대",
                    "published_at": "2026-04-05T09:10:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.yonhap_news_service.fetch_recent_news",
        fake_fetch_recent_yonhap_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_includes_bloomberg_when_foreign_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    _mock_empty_news_sources(monkeypatch, "investing_news_service", "seeking_alpha_news_service")

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", True)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "BLOOMBERG",
                "title": "Samsung suppliers gain on memory optimism",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.bloomberg.com/news/articles/example",
                "external_id": "example",
                "language": "en",
                "metadata": {
                    "translated_title": "메모리 업황 기대에 삼성 관련주 강세",
                    "translated_summary": "블룸버그 기사 한글 요약",
                },
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "BLOOMBERG"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "BLOOMBERG",
                    "title": "Samsung suppliers gain on memory optimism",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    async def fake_fetch_recent_nasdaq_news(*, limit):
        assert limit == 25
        return []

    monkeypatch.setattr(
        "services.news_polling_service.nasdaq_news_service.fetch_recent_news",
        fake_fetch_recent_nasdaq_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        _passthrough_translate_items,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_includes_cnbc_when_foreign_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    _mock_empty_news_sources(monkeypatch, "investing_news_service", "seeking_alpha_news_service")

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "CNBC",
                "title": "Samsung suppliers rise as AI memory demand grows",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.cnbc.com/example",
                "external_id": "cnbc-1",
                "language": "en",
                "metadata": {
                    "translated_title": "AI 메모리 수요 확대로 삼성 공급망 강세",
                    "translated_summary": "CNBC 기사 한글 요약",
                },
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "CNBC"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "CNBC",
                    "title": "Samsung suppliers rise as AI memory demand grows",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    async def fake_fetch_recent_nasdaq_news(*, limit):
        assert limit == 25
        return []

    monkeypatch.setattr(
        "services.news_polling_service.nasdaq_news_service.fetch_recent_news",
        fake_fetch_recent_nasdaq_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        _passthrough_translate_items,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_includes_nasdaq_when_foreign_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    _mock_empty_news_sources(monkeypatch, "investing_news_service", "seeking_alpha_news_service")

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", True)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_nasdaq_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "NASDAQ",
                "title": "Chip stocks climb as AI demand keeps expanding",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.nasdaq.com/articles/example",
                "external_id": "nasdaq-1",
                "language": "en",
                "metadata": {
                    "translated_title": "AI 수요 확대로 반도체주 강세",
                    "translated_summary": "Nasdaq 기사 한글 요약",
                },
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "NASDAQ"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "NASDAQ",
                    "title": "Chip stocks climb as AI demand keeps expanding",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.nasdaq_news_service.fetch_recent_news",
        fake_fetch_recent_nasdaq_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        _passthrough_translate_items,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_captures_source_errors(monkeypatch):
    from services.news_polling_service import NewsPollingService, NewsSourcePollSpec

    captured = {}

    async def fake_capture_exception(**kwargs):
        captured.update(kwargs)
        return {"fingerprint": "fp-1"}

    async def failing_fetch():
        raise RuntimeError("feed timeout")

    monkeypatch.setattr(
        "services.news_polling_service.error_capture_service.capture_exception",
        fake_capture_exception,
    )

    service = NewsPollingService()
    result = await service._poll_single_source(
        NewsSourcePollSpec(
            source_code="BLOOMBERG",
            enabled=True,
            skip_message="",
            fetch=failing_fetch,
        ),
        semaphore=asyncio.Semaphore(1),
    )

    assert result.status == "ERROR"
    assert result.message == "feed timeout"
    assert captured["component"] == "news_polling"
    assert captured["operation"] == "poll_source:BLOOMBERG"
    assert captured["detail"]["source_code"] == "BLOOMBERG"
    assert isinstance(captured["exc"], RuntimeError)


@pytest.mark.asyncio
async def test_news_polling_service_includes_investing_when_foreign_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    _mock_empty_news_sources(monkeypatch, "nasdaq_news_service", "seeking_alpha_news_service")
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_investing_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "INVESTING",
                "title": "Chip stocks rise as AI spending stays strong",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.investing.com/news/stock-market-news/example",
                "external_id": "investing-1",
                "language": "en",
                "metadata": {
                    "translated_title": "AI 지출 강세에 반도체주 상승",
                    "translated_summary": "Investing.com 기사 한글 요약",
                },
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "INVESTING"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "INVESTING",
                    "title": "Chip stocks rise as AI spending stays strong",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        fake_fetch_recent_investing_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        _passthrough_translate_items,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_includes_seeking_alpha_when_foreign_enabled(monkeypatch):
    from services.news_polling_service import NewsPollingService
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_investing_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_seeking_alpha_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "SEEKING_ALPHA",
                "title": "Semiconductor winners extend rally",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://seekingalpha.com/news/example",
                "external_id": "sa-1",
                "language": "en",
            }
        ]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "SEEKING_ALPHA"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "SEEKING_ALPHA",
                    "title": "Semiconductor winners extend rally",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        fake_fetch_recent_investing_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.seeking_alpha_news_service.fetch_recent_news",
        fake_fetch_recent_seeking_alpha_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        _passthrough_translate_items,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_skips_nasdaq_when_source_disabled(monkeypatch):
    from services.news_polling_service import NewsPollingService

    _mock_empty_news_sources(monkeypatch, "investing_news_service", "seeking_alpha_news_service")
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False, raising=False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_ingest_items_detailed(_session, items):
        assert items == []
        return {
            "summary": {"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
            "created_items": [],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    service = NewsPollingService()
    await service.poll_sources(object(), market_hours=False)
    snapshot = news_runtime_service.get_snapshot(include_foreign=True)

    assert snapshot["sources"]["NASDAQ"]["status"] == "SKIPPED"
    assert snapshot["sources"]["NASDAQ"]["message"] == "NEWS_NASDAQ_ENABLED disabled"


@pytest.mark.asyncio
async def test_news_polling_service_translates_foreign_items_before_ingest(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return [
            {
                "source_code": "BLOOMBERG",
                "title": "Samsung suppliers gain on memory optimism",
                "published_at": "2026-04-05T09:20:00+09:00",
                "symbols": ["005930"],
                "url": "https://www.bloomberg.com/news/articles/example",
                "external_id": "example",
                "language": "en",
                "metadata": {
                    "publisher": "Bloomberg Markets",
                },
            }
        ]

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_investing_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_seeking_alpha_news(*, limit):
        assert limit == 25
        return []

    async def fake_translate_items(items):
        assert len(items) == 1
        copied = dict(items[0])
        copied["metadata"] = {
            **dict(items[0].get("metadata") or {}),
            "translated_title": "메모리 업황 기대에 삼성 공급망 강세",
            "translated_summary": "외신 기사 한글 요약",
            "translation_provider": "CODEX",
            "translation_status": "SUCCESS",
        }
        return [copied]

    async def fake_ingest_items_detailed(session, items):
        assert len(items) == 1
        assert items[0]["source_code"] == "BLOOMBERG"
        assert items[0]["metadata"]["translated_title"] == "메모리 업황 기대에 삼성 공급망 강세"
        assert items[0]["metadata"]["translation_status"] == "SUCCESS"
        return {
            "summary": {"received": 1, "created": 1, "duplicates": 0, "skipped": 0},
            "created_items": [
                {
                    "source_code": "BLOOMBERG",
                    "title": "Samsung suppliers gain on memory optimism",
                    "published_at": "2026-04-05T09:20:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    published = []

    async def fake_publish(event):
        published.append(event)

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        fake_fetch_recent_investing_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.seeking_alpha_news_service.fetch_recent_news",
        fake_fetch_recent_seeking_alpha_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_translation_service.translate_items",
        fake_translate_items,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    monkeypatch.setattr("services.news_polling_service.event_bus.publish", fake_publish)

    service = NewsPollingService()
    summary = await service.poll_sources(object(), market_hours=False)

    assert summary["created"] == 1
    assert summary["published_events"] == 1
    assert published[0].data["symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_news_polling_service_fetches_multiple_sources_in_parallel(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_FETCH_CONCURRENCY", 6)

    started: list[str] = []
    release = asyncio.Event()

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        started.append("KRX")
        await release.wait()
        return []

    async def fake_fetch_recent_yonhap_news(_session, *, limit):
        assert limit == 25
        started.append("YONHAP")
        await release.wait()
        return []

    def make_media_fetcher(source_code):
        async def _fetch(*, limit):
            assert limit == 25
            started.append(source_code)
            await release.wait()
            return []
        return _fetch

    async def fake_ingest_items_detailed(_session, items):
        assert items == []
        return {
            "summary": {"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
            "created_items": [],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.yonhap_news_service.fetch_recent_news",
        fake_fetch_recent_yonhap_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        make_media_fetcher("BLOOMBERG"),
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        make_media_fetcher("CNBC"),
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        make_media_fetcher("INVESTING"),
    )
    monkeypatch.setattr(
        "services.news_polling_service.seeking_alpha_news_service.fetch_recent_news",
        make_media_fetcher("SEEKING_ALPHA"),
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    service = NewsPollingService()
    poll_task = asyncio.create_task(service.poll_sources(object(), market_hours=False))

    async def wait_for_parallel_starts():
        while len(started) < 6:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_for_parallel_starts(), timeout=0.2)
    assert set(started) == {"KRX", "YONHAP", "BLOOMBERG", "CNBC", "INVESTING", "SEEKING_ALPHA"}

    release.set()
    summary = await poll_task

    assert summary["received"] == 0


@pytest.mark.asyncio
async def test_news_polling_service_respects_fetch_concurrency_limit(monkeypatch):
    from services.news_polling_service import NewsPollingService

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_FETCH_CONCURRENCY", 2)

    release = asyncio.Event()
    active = {"count": 0, "max": 0}

    async def track_fetch():
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await release.wait()
        active["count"] -= 1
        return []

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return await track_fetch()

    async def fake_fetch_recent_yonhap_news(_session, *, limit):
        assert limit == 25
        return await track_fetch()

    def make_media_fetcher():
        async def _fetch(*, limit):
            assert limit == 25
            return await track_fetch()
        return _fetch

    async def fake_ingest_items_detailed(_session, items):
        assert items == []
        return {
            "summary": {"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
            "created_items": [],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.yonhap_news_service.fetch_recent_news",
        fake_fetch_recent_yonhap_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        make_media_fetcher(),
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        make_media_fetcher(),
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        make_media_fetcher(),
    )
    monkeypatch.setattr(
        "services.news_polling_service.seeking_alpha_news_service.fetch_recent_news",
        make_media_fetcher(),
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    task = asyncio.create_task(NewsPollingService().poll_sources(object(), market_hours=False))
    await asyncio.sleep(0.05)
    assert active["max"] == 2

    release.set()
    summary = await task

    assert summary["received"] == 0


@pytest.mark.asyncio
async def test_news_polling_service_returns_observability_metric_payload_without_writing(monkeypatch):
    from services.news_polling_service import NewsPollingService
    import services.news_polling_service as news_polling_service_module

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_ingest_items_detailed(_session, items):
        assert items == []
        return {
            "summary": {"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
            "created_items": [],
        }

    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)
    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )
    summary = await NewsPollingService().poll_sources(object(), market_hours=False)

    assert summary["received"] == 0
    assert not hasattr(news_polling_service_module, "observability_service")
    assert summary["metric_payload"]["status"] == "SUCCESS"
    assert summary["metric_payload"]["item_count"] == 0
    assert summary["metric_payload"]["detail"]["mode"] == "AUTO_OFF_HOURS"


@pytest.mark.asyncio
async def test_news_polling_service_updates_runtime_counts_from_ingest(monkeypatch):
    from services.news_polling_service import NewsPollingService
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_yonhap_news(_session, *, limit):
        assert limit == 25
        return [
            {
                "source_code": "YONHAP",
                "title": "삼성전자 투자 확대",
                "published_at": "2026-04-08T10:00:00+09:00",
                "url": "https://example.com/news/1",
            },
            {
                "source_code": "YONHAP",
                "title": "삼성전자 투자 확대",
                "published_at": "2026-04-08T10:00:00+09:00",
                "url": "https://example.com/news/1",
            },
        ]

    async def fake_ingest_items_detailed(_session, items):
        assert len(items) == 2
        return {
            "summary": {"received": 2, "created": 1, "duplicates": 1, "skipped": 0},
            "source_summaries": {
                "YONHAP": {"received": 2, "created": 1, "duplicates": 1, "skipped": 0},
            },
            "created_items": [
                {
                    "source_code": "YONHAP",
                    "title": "삼성전자 투자 확대",
                    "published_at": "2026-04-08T10:00:00+09:00",
                    "symbols": ["005930"],
                }
            ],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.yonhap_news_service.fetch_recent_news",
        fake_fetch_recent_yonhap_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    summary = await NewsPollingService().poll_sources(object(), market_hours=False)
    snapshot = news_runtime_service.get_snapshot(include_foreign=False)

    assert summary["created"] == 1
    assert snapshot["sources"]["YONHAP"]["counts"] == {
        "received": 2,
        "created": 1,
        "duplicates": 1,
        "skipped": 0,
    }
    assert snapshot["sources"]["YONHAP"]["message"] == "신규 1건 적재 · 중복 1건 · 스킵 0건"


@pytest.mark.asyncio
async def test_news_polling_service_marks_overall_partial_error_when_some_sources_fail(monkeypatch):
    from services.news_polling_service import NewsPollingService
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", False)

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        raise RuntimeError("krx down")

    async def fake_fetch_recent_yonhap_news(_session, *, limit):
        assert limit == 25
        return [
            {
                "source_code": "YONHAP",
                "title": "삼성전자 투자 확대",
                "published_at": "2026-04-08T10:00:00+09:00",
                "url": "https://example.com/news/1",
            }
        ]

    async def fake_ingest_items_detailed(_session, items):
        assert len(items) == 1
        return {
            "summary": {"received": 1, "created": 0, "duplicates": 1, "skipped": 0},
            "source_summaries": {
                "YONHAP": {"received": 1, "created": 0, "duplicates": 1, "skipped": 0},
            },
            "created_items": [],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.yonhap_news_service.fetch_recent_news",
        fake_fetch_recent_yonhap_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    await NewsPollingService().poll_sources(object(), market_hours=False)
    snapshot = news_runtime_service.get_snapshot(include_foreign=False)

    assert snapshot["overall"]["last_status"] == "PARTIAL_ERROR"
    assert snapshot["overall"]["last_message"] == "일부 소스 실패 · 신규 0건 · 중복 1건 · 스킵 0건 · 오류 1건"
    assert snapshot["sources"]["KRX"]["status"] == "ERROR"
    assert snapshot["sources"]["YONHAP"]["message"] == "신규 없음 · 기존 기사 중복 1건"


@pytest.mark.asyncio
async def test_news_polling_service_skips_source_during_failure_cooldown(monkeypatch):
    from services.news_polling_service import NewsPollingService
    from services.news_runtime_service import news_runtime_service

    news_runtime_service.reset()
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("services.news_polling_service.settings.OPEN_DART_API_KEY", "")
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_DOMESTIC_MEDIA_ENABLED", False)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_INCLUDE_FOREIGN", True)
    monkeypatch.setattr("services.news_polling_service.settings.NEWS_NASDAQ_ENABLED", False)
    monkeypatch.setattr("services.news_runtime_service.settings.NEWS_SOURCE_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr("services.news_runtime_service.settings.NEWS_SOURCE_FAILURE_COOLDOWN_MIN", 30)

    news_runtime_service.record_source_result(
        "INVESTING",
        status="ERROR",
        mode="AUTO_EVENT",
        message="dns fail",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
        update_overall=False,
    )
    news_runtime_service.record_source_result(
        "INVESTING",
        status="ERROR",
        mode="AUTO_EVENT",
        message="dns fail",
        counts={"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
        update_overall=False,
    )

    called = {"investing": 0}

    async def fake_fetch_recent_krx_disclosures(*, page_count):
        assert page_count == 25
        return []

    async def fake_fetch_recent_bloomberg_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_cnbc_news(*, limit):
        assert limit == 25
        return []

    async def fake_fetch_recent_investing_news(*, limit):
        called["investing"] += 1
        return []

    async def fake_fetch_recent_seeking_alpha_news(*, limit):
        assert limit == 25
        return []

    async def fake_ingest_items_detailed(_session, items):
        assert items == []
        return {
            "summary": {"received": 0, "created": 0, "duplicates": 0, "skipped": 0},
            "source_summaries": {},
            "created_items": [],
        }

    monkeypatch.setattr(
        "services.news_polling_service.krx_kind_disclosure_service.fetch_recent_disclosures",
        fake_fetch_recent_krx_disclosures,
    )
    monkeypatch.setattr(
        "services.news_polling_service.bloomberg_news_service.fetch_recent_news",
        fake_fetch_recent_bloomberg_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.cnbc_news_service.fetch_recent_news",
        fake_fetch_recent_cnbc_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.investing_news_service.fetch_recent_news",
        fake_fetch_recent_investing_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.seeking_alpha_news_service.fetch_recent_news",
        fake_fetch_recent_seeking_alpha_news,
    )
    monkeypatch.setattr(
        "services.news_polling_service.news_ingest_service.ingest_items_detailed",
        fake_ingest_items_detailed,
    )

    await NewsPollingService().poll_sources(object(), market_hours=False)
    snapshot = news_runtime_service.get_snapshot(include_foreign=True)

    assert called["investing"] == 0
    assert snapshot["sources"]["INVESTING"]["status"] == "SKIPPED"
    assert "cooldown" in snapshot["sources"]["INVESTING"]["message"]
