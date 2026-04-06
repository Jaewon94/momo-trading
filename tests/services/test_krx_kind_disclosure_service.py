import httpx
import pytest

from services.krx_kind_disclosure_service import KrxKindDisclosureService


@pytest.mark.asyncio
async def test_krx_kind_disclosure_service_fetches_and_normalizes_rss_items():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/disclosure/rsstodaydistribute.do"
        assert request.url.params["method"] == "searchRssTodayDistribute"
        return httpx.Response(
            200,
            text="""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>오늘의공시</title>
    <item>
      <title><![CDATA[삼성전자(005930) [정정] 주요사항보고서]]></title>
      <link>https://kind.krx.co.kr/common/disclsviewer.do?acptno=20260406000123</link>
      <description><![CDATA[제출인: 삼성전자]]></description>
      <dc:date>2026-04-06T09:11:00+09:00</dc:date>
    </item>
  </channel>
</rss>""",
            headers={"Content-Type": "application/xml"},
        )

    service = KrxKindDisclosureService(transport=httpx.MockTransport(handler))

    items = await service.fetch_recent_disclosures(page_count=20)

    assert len(items) == 1
    assert items[0]["source_code"] == "KRX"
    assert items[0]["symbols"] == ["005930"]
    assert items[0]["title"].startswith("삼성전자")
    assert items[0]["external_id"] == "20260406000123"


@pytest.mark.asyncio
async def test_krx_kind_disclosure_service_falls_back_to_html_when_rss_invalid():
    responses = iter(
        [
            httpx.Response(200, text="<html>broken</html>", headers={"Content-Type": "text/html"}),
            httpx.Response(
                200,
                text="""
<section class="scrarea type-00">
  <table class="list type-00 mt10">
    <tbody>
      <tr class="first">
        <td class="first">09:21</td>
        <td><a href="/compnay/005930">삼성전자 (005930)</a></td>
        <td><a href="javascript:fnOpen('20260406000999')">주요사항보고서</a></td>
        <td>삼성전자</td>
        <td>-</td>
      </tr>
    </tbody>
  </table>
</section>
""",
                headers={"Content-Type": "text/html"},
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    service = KrxKindDisclosureService(transport=httpx.MockTransport(handler))

    items = await service.fetch_recent_disclosures(page_count=20)

    assert len(items) == 1
    assert items[0]["source_code"] == "KRX"
    assert items[0]["symbols"] == ["005930"]
    assert items[0]["external_id"] == "20260406000999"
    assert items[0]["title"] == "삼성전자 (005930) · 주요사항보고서"


@pytest.mark.asyncio
async def test_krx_kind_disclosure_service_returns_empty_list_when_no_data():
    responses = iter(
        [
            httpx.Response(
                200,
                text="""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>오늘의공시</title></channel></rss>""",
                headers={"Content-Type": "application/xml"},
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    service = KrxKindDisclosureService(transport=httpx.MockTransport(handler))

    items = await service.fetch_recent_disclosures(page_count=20)

    assert items == []
