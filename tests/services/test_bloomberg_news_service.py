import pytest

from tests.conftest import TestAsyncSessionLocal


BLOOMBERG_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://www.bloomberg.com/news/articles/2026-04-05/example-one</loc>
    <news:news>
      <news:publication>
        <news:name>Bloomberg</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>2026-04-05T15:44:38.882Z</news:publication_date>
      <news:title>Samsung and LG Rally as Chip Cycle Improves</news:title>
      <news:keywords>semiconductors, asia</news:keywords>
      <news:stock_tickers>NYSE:IBM, NASDAQ:NVDA</news:stock_tickers>
    </news:news>
  </url>
  <url>
    <loc>https://www.bloomberg.com/news/articles/2026-04-05/example-two</loc>
    <news:news>
      <news:publication>
        <news:name>Bloomberg</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>2026-04-05T14:10:00.000Z</news:publication_date>
      <news:title>Oil Holds Near Five-Week High on Supply Concerns</news:title>
      <news:keywords>oil, commodities</news:keywords>
      <news:stock_tickers></news:stock_tickers>
    </news:news>
  </url>
</urlset>
"""


@pytest.mark.asyncio
async def test_bloomberg_news_service_fetches_sitemap_items():
    import httpx

    from services.bloomberg_news_service import BloombergNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=BLOOMBERG_SITEMAP,
            headers={"Content-Type": "application/xml; charset=UTF-8"},
        )
    )

    service = BloombergNewsService(transport=transport)
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 2
    assert items[0]["source_code"] == "BLOOMBERG"
    assert items[0]["language"] == "en"
    assert items[0]["url"].startswith("https://www.bloomberg.com/news/articles/")
    assert items[0]["metadata"]["keywords"] == ["semiconductors", "asia"]
    assert items[0]["metadata"]["stock_tickers"] == ["NYSE:IBM", "NASDAQ:NVDA"]
    assert items[0]["external_id"] == "example-one"


@pytest.mark.asyncio
async def test_bloomberg_news_service_fetch_and_ingest_marks_foreign_items_pending_translation():
    import httpx

    from repositories.news_item_repository import NewsItemRepository
    from services.bloomberg_news_service import BloombergNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=BLOOMBERG_SITEMAP,
            headers={"Content-Type": "application/xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        service = BloombergNewsService(transport=transport)
        summary = await service.fetch_and_ingest(session, limit=5)
        await session.commit()
        items = await NewsItemRepository(session).get_recent(limit=5, source_code="BLOOMBERG")

    assert summary["received"] == 2
    assert summary["created"] == 2
    urls = {item.url for item in items}
    assert "https://www.bloomberg.com/news/articles/2026-04-05/example-one" in urls
    assert "https://www.bloomberg.com/news/articles/2026-04-05/example-two" in urls
    assert all('"translation_status": "PENDING"' in (item.metadata_json or "") for item in items)
