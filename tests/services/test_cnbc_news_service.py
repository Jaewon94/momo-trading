import pytest

from tests.conftest import TestAsyncSessionLocal


CNBC_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CNBC Markets</title>
    <item>
      <title>Samsung suppliers rise as AI memory demand grows</title>
      <link>https://www.cnbc.com/2026/04/05/samsung-suppliers-rise.html</link>
      <description>Chip demand outlook is improving in Asia.</description>
      <pubDate>Sun, 05 Apr 2026 14:10:00 GMT</pubDate>
      <guid>cnbc-1</guid>
    </item>
    <item>
      <title>Oil retreats after sharp weekly gain</title>
      <link>https://www.cnbc.com/2026/04/05/oil-retreats.html</link>
      <description>Crude prices slipped after a strong weekly rally.</description>
      <pubDate>Sun, 05 Apr 2026 12:05:00 GMT</pubDate>
      <guid>cnbc-2</guid>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_cnbc_news_service_fetches_rss_items():
    import httpx

    from services.cnbc_news_service import CNBCNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=CNBC_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    service = CNBCNewsService(transport=transport)
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 2
    assert items[0]["source_code"] == "CNBC"
    assert items[0]["language"] == "en"
    assert items[0]["external_id"] == "cnbc-1"
    assert items[0]["url"].startswith("https://www.cnbc.com/")


@pytest.mark.asyncio
async def test_cnbc_news_service_fetch_and_ingest_marks_items_pending_translation():
    import httpx

    from repositories.news_item_repository import NewsItemRepository
    from services.cnbc_news_service import CNBCNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=CNBC_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        service = CNBCNewsService(transport=transport)
        summary = await service.fetch_and_ingest(session, limit=5)
        await session.commit()
        items = await NewsItemRepository(session).get_recent(limit=5, source_code="CNBC")

    assert summary["received"] == 2
    assert summary["created"] == 2
    matched = [item for item in items if item.url in {
        "https://www.cnbc.com/2026/04/05/samsung-suppliers-rise.html",
        "https://www.cnbc.com/2026/04/05/oil-retreats.html",
    }]
    assert len(matched) == 2
    assert all('"translation_status": "PENDING"' in (item.metadata_json or "") for item in matched)
