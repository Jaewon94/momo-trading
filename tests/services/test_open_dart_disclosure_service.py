import httpx
import pytest

from services.open_dart_disclosure_service import OpenDartDisclosureService


@pytest.mark.asyncio
async def test_open_dart_disclosure_service_fetches_and_normalizes_items(monkeypatch):
    monkeypatch.setattr("services.open_dart_disclosure_service.settings.OPEN_DART_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/list.json"
        assert request.url.params["crtfc_key"] == "test-key"
        return httpx.Response(200, json={
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "corp_name": "삼성전자",
                    "corp_cls": "Y",
                    "stock_code": "005930",
                    "report_nm": "주요사항보고서(자기주식취득결정)",
                    "rcept_no": "20260405000123",
                    "rcept_dt": "20260405",
                    "rm": "유",
                }
            ],
        })

    service = OpenDartDisclosureService(transport=httpx.MockTransport(handler))

    items = await service.fetch_recent_disclosures(days=1, page_count=10)

    assert len(items) == 1
    assert items[0]["source_code"] == "DART"
    assert items[0]["symbols"] == ["005930"]
    assert items[0]["external_id"] == "20260405000123"
    assert "삼성전자" in items[0]["title"]
    assert items[0]["url"].endswith("20260405000123")


@pytest.mark.asyncio
async def test_open_dart_disclosure_service_fetch_and_ingest_returns_summary(monkeypatch):
    monkeypatch.setattr("services.open_dart_disclosure_service.settings.OPEN_DART_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "corp_name": "하이닉스",
                    "corp_cls": "Y",
                    "stock_code": "000660",
                    "report_nm": "투자판단 관련 주요경영사항",
                    "rcept_no": "20260405000456",
                    "rcept_dt": "20260405",
                    "rm": "유",
                }
            ],
        })

    captured = {}

    async def fake_ingest(session, items):
        captured["count"] = len(items)
        captured["item"] = items[0]
        return {"received": 1, "created": 1, "duplicates": 0, "skipped": 0}

    monkeypatch.setattr(
        "services.open_dart_disclosure_service.news_ingest_service.ingest_items",
        fake_ingest,
    )

    service = OpenDartDisclosureService(transport=httpx.MockTransport(handler))

    summary = await service.fetch_and_ingest(object(), days=1, page_count=20)

    assert summary["created"] == 1
    assert captured["count"] == 1
    assert captured["item"]["source_code"] == "DART"


@pytest.mark.asyncio
async def test_open_dart_disclosure_service_returns_empty_list_when_no_data(monkeypatch):
    monkeypatch.setattr("services.open_dart_disclosure_service.settings.OPEN_DART_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "013",
            "message": "조회된 데이타가 없습니다.",
            "list": [],
        })

    service = OpenDartDisclosureService(transport=httpx.MockTransport(handler))

    items = await service.fetch_recent_disclosures(days=1, page_count=10)

    assert items == []


@pytest.mark.asyncio
async def test_open_dart_disclosure_service_requires_api_key(monkeypatch):
    monkeypatch.setattr("services.open_dart_disclosure_service.settings.OPEN_DART_API_KEY", "")
    service = OpenDartDisclosureService()

    with pytest.raises(RuntimeError, match="OPEN_DART_API_KEY"):
        await service.fetch_recent_disclosures()
