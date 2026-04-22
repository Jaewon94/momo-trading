import pytest

from tests.conftest import TestAsyncSessionLocal


NASDAQ_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Nasdaq Markets</title>
    <item>
      <title>Chip stocks climb as AI demand keeps expanding</title>
      <link>https://www.nasdaq.com/articles/chip-stocks-climb-ai-demand-expands</link>
      <description>Semiconductor names rallied after upbeat demand commentary.</description>
      <pubDate>Sun, 05 Apr 2026 15:20:00 GMT</pubDate>
      <guid>nasdaq-1</guid>
    </item>
    <item>
      <title>Dollar steadies before inflation data</title>
      <link>https://www.nasdaq.com/articles/dollar-steadies-before-inflation-data</link>
      <description>FX markets turned cautious ahead of key macro releases.</description>
      <pubDate>Sun, 05 Apr 2026 13:05:00 GMT</pubDate>
      <guid>nasdaq-2</guid>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_nasdaq_news_service_fetches_rss_items():
    import httpx

    from services.nasdaq_news_service import NasdaqNewsService

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.nasdaq.com"
        assert request.url.path == "/feed/rssoutbound"
        assert request.url.params["category"] == "Markets"
        assert "Mozilla/5.0" in request.headers["User-Agent"]
        assert request.headers["Referer"] == "https://www.nasdaq.com/nasdaq-RSS-Feeds"
        assert request.headers["Accept-Language"] == "en-US,en;q=0.9"
        return httpx.Response(
            200,
            text=NASDAQ_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )

    service = NasdaqNewsService(transport=httpx.MockTransport(handler))
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 2
    assert items[0]["source_code"] == "NASDAQ"
    assert items[0]["language"] == "en"
    assert items[0]["external_id"] == "nasdaq-1"


@pytest.mark.asyncio
async def test_nasdaq_news_service_fetch_and_ingest_marks_items_pending_translation():
    import httpx

    from repositories.news_item_repository import NewsItemRepository
    from services.nasdaq_news_service import NasdaqNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=NASDAQ_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        service = NasdaqNewsService(transport=transport)
        summary = await service.fetch_and_ingest(session, limit=5)
        await session.commit()
        items = await NewsItemRepository(session).get_recent(limit=5, source_code="NASDAQ")

    assert summary["received"] == 2
    assert summary["created"] == 2
    assert len(items) == 2
    assert '"translation_status": "PENDING"' in (items[0].metadata_json or "")


@pytest.mark.asyncio
async def test_nasdaq_news_service_retries_transient_transport_errors():
    import httpx

    from services.nasdaq_news_service import NasdaqNewsService

    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.RemoteProtocolError("stream reset")
        return httpx.Response(
            200,
            text=NASDAQ_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )

    service = NasdaqNewsService(
        transport=httpx.MockTransport(handler),
        retry_backoff_sec=0,
    )
    items = await service.fetch_recent_news(limit=5)

    assert calls == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_nasdaq_news_service_wraps_timeout_as_runtime_error():
    import httpx

    from services.nasdaq_news_service import NasdaqNewsService

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    service = NasdaqNewsService(
        transport=httpx.MockTransport(handler),
        retry_backoff_sec=0,
    )

    with pytest.raises(RuntimeError, match="Nasdaq 소스 응답 지연 또는 비정상 연결: Markets"):
        await service.fetch_recent_news(limit=5)
