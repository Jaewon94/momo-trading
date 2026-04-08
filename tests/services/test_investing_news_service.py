import pytest

from tests.conftest import TestAsyncSessionLocal


INVESTING_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Investing.com Stock Market News</title>
    <item>
      <title>Chip stocks rise as AI spending stays strong</title>
      <link>https://www.investing.com/news/stock-market-news/chip-stocks-rise-400001</link>
      <description>Semiconductor shares advanced after upbeat capex commentary.</description>
      <pubDate>Sun, 05 Apr 2026 16:10:00 GMT</pubDate>
      <guid>investing-1</guid>
    </item>
    <item>
      <title>Wall Street drifts before inflation data</title>
      <link>https://www.investing.com/news/stock-market-news/wall-street-drifts-400002</link>
      <description>Investors turned cautious ahead of macro releases.</description>
      <pubDate>Sun, 05 Apr 2026 14:05:00 GMT</pubDate>
      <guid>investing-2</guid>
    </item>
  </channel>
</rss>
"""


INVESTING_RSS_NONSTANDARD_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Investing.com Stock Market News</title>
    <item>
      <title>Chip stocks steady after overnight gain</title>
      <link>https://www.investing.com/news/stock-market-news/chip-stocks-steady-400003</link>
      <description>Morning update.</description>
      <pubDate>2026-04-06 05:08:24</pubDate>
      <guid>investing-3</guid>
    </item>
  </channel>
</rss>
"""

INVESTING_RSS_MALFORMED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Investing.com Stock Market News</title>
    <item>
      <title>Chip stocks & AI names climb</title>
      <link>https://www.investing.com/news/stock-market-news/chip-stocks-400004</link>
      <description>Markets & sentiment improved.</description>
      <pubDate>Sun, 05 Apr 2026 16:10:00 GMT</pubDate>
      <guid>investing-4</guid>
    </item>
  </channel>
</rss>
<!-- trailing junk
"""


@pytest.mark.asyncio
async def test_investing_news_service_fetches_rss_items():
    import httpx

    from services.investing_news_service import InvestingNewsService

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.investing.com"
        assert request.url.path == "/rss/news_25.rss"
        return httpx.Response(
            200,
            text=INVESTING_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )

    service = InvestingNewsService(transport=httpx.MockTransport(handler))
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 2
    assert items[0]["source_code"] == "INVESTING"
    assert items[0]["language"] == "en"
    assert items[0]["external_id"] == "investing-1"


@pytest.mark.asyncio
async def test_investing_news_service_fetch_and_ingest_marks_items_pending_translation():
    import httpx

    from repositories.news_item_repository import NewsItemRepository
    from services.investing_news_service import InvestingNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=INVESTING_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        service = InvestingNewsService(transport=transport)
        summary = await service.fetch_and_ingest(session, limit=5)
        await session.commit()
        items = await NewsItemRepository(session).get_recent(limit=5, source_code="INVESTING")

    assert summary["received"] == 2
    assert summary["created"] == 2
    assert len(items) == 2
    assert '"translation_status": "PENDING"' in (items[0].metadata_json or "")


@pytest.mark.asyncio
async def test_investing_news_service_accepts_nonstandard_datetime_format():
    import httpx

    from services.investing_news_service import InvestingNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=INVESTING_RSS_NONSTANDARD_DATE,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    service = InvestingNewsService(transport=transport)
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 1
    assert items[0]["published_at"].startswith("2026-04-06T")


@pytest.mark.asyncio
async def test_investing_news_service_sanitizes_malformed_xml():
    import httpx

    from services.investing_news_service import InvestingNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=INVESTING_RSS_MALFORMED,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    service = InvestingNewsService(transport=transport)
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 1
    assert items[0]["title"] == "Chip stocks & AI names climb"
