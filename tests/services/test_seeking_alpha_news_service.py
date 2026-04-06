import pytest


SEEKING_ALPHA_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Seeking Alpha All News</title>
    <item>
      <title>Chipmakers gain as AI demand outlook firms</title>
      <link>https://seekingalpha.com/news/400001-chipmakers-gain</link>
      <description>Semiconductor shares advanced in premarket trade.</description>
      <pubDate>Sun, 05 Apr 2026 16:10:00 GMT</pubDate>
      <guid>sa-1</guid>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_seeking_alpha_news_service_fetches_rss_items():
    import httpx

    from services.seeking_alpha_news_service import SeekingAlphaNewsService

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "seekingalpha.com"
        assert request.url.path == "/market_currents.xml"
        return httpx.Response(
            200,
            text=SEEKING_ALPHA_RSS,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )

    service = SeekingAlphaNewsService(transport=httpx.MockTransport(handler))
    items = await service.fetch_recent_news(limit=5)

    assert len(items) == 1
    assert items[0]["source_code"] == "SEEKING_ALPHA"
    assert items[0]["language"] == "en"
    assert items[0]["external_id"] == "sa-1"
