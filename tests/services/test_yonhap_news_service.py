import pytest

from models.stock import Stock
from tests.conftest import TestAsyncSessionLocal


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>연합뉴스TV 경제</title>
    <item>
      <title>삼성전자, AI 반도체 투자 확대</title>
      <link>https://www.yonhapnewstv.co.kr/news/AKR20260406000100001</link>
      <description>삼성전자와 SK하이닉스가 투자 확대에 나섰다.</description>
      <pubDate>Mon, 06 Apr 2026 09:00:00 +0900</pubDate>
    </item>
    <item>
      <title>거시 경제 브리핑</title>
      <link>https://www.yonhapnewstv.co.kr/news/AKR20260406000100002</link>
      <description>환율과 금리 동향을 정리했다.</description>
      <pubDate>Mon, 06 Apr 2026 08:30:00 +0900</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_yonhap_news_service_fetches_rss_and_maps_symbols():
    import httpx

    from services.yonhap_news_service import YonhapNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=RSS_XML,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            Stock(symbol="905930", name="삼성전자", market="KOSPI", is_active=True),
            Stock(symbol="900660", name="SK하이닉스", market="KOSPI", is_active=True),
        ])
        await session.commit()

        service = YonhapNewsService(transport=transport)
        items = await service.fetch_recent_news(session, limit=10)

    assert len(items) == 2
    assert items[0]["source_code"] == "YONHAP"
    assert set(items[0]["symbols"]) == {"905930", "900660"}
    assert items[0]["url"].startswith("https://www.yonhapnewstv.co.kr/news/")
    assert items[1]["symbols"] == []


@pytest.mark.asyncio
async def test_yonhap_news_service_fetch_and_ingest_returns_summary():
    import httpx

    from repositories.news_item_repository import NewsItemRepository
    from services.yonhap_news_service import YonhapNewsService

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            text=RSS_XML,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )
    )

    async with TestAsyncSessionLocal() as session:
        session.add(Stock(symbol="805930", name="삼성전자", market="KOSPI", is_active=True))
        await session.commit()

        service = YonhapNewsService(transport=transport)
        summary = await service.fetch_and_ingest(session, limit=10)
        await session.commit()

        items = await NewsItemRepository(session).get_recent(limit=10, source_code="YONHAP")

    assert summary["received"] == 2
    assert summary["created"] == 2
    urls = {item.url for item in items}
    assert "https://www.yonhapnewstv.co.kr/news/AKR20260406000100001" in urls
    assert "https://www.yonhapnewstv.co.kr/news/AKR20260406000100002" in urls


@pytest.mark.asyncio
async def test_yonhap_news_service_sends_browser_like_headers():
    import httpx

    from services.yonhap_news_service import YonhapNewsService

    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers["user-agent"] = request.headers.get("user-agent")
        captured_headers["accept"] = request.headers.get("accept")
        captured_headers["accept-language"] = request.headers.get("accept-language")
        captured_headers["referer"] = request.headers.get("referer")
        return httpx.Response(
            200,
            text=RSS_XML,
            headers={"Content-Type": "application/rss+xml; charset=UTF-8"},
        )

    async with TestAsyncSessionLocal() as session:
        service = YonhapNewsService(transport=httpx.MockTransport(handler))
        await service.fetch_recent_news(session, limit=1)

    assert "Mozilla/5.0" in str(captured_headers["user-agent"])
    assert "application/rss+xml" in str(captured_headers["accept"])
    assert "ko-KR" in str(captured_headers["accept-language"])
    assert captured_headers["referer"] == "https://www.yonhapnewstv.co.kr/"
