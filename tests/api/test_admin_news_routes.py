import pytest
import httpx


@pytest.mark.asyncio
async def test_admin_news_sources_route_returns_catalog(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.NEWS_INCLUDE_FOREIGN", True)

    response = await client.get("/api/v1/admin/news/sources")

    assert response.status_code == 200
    payload = response.json()["data"]
    codes = {item["code"] for item in payload["sources"]}
    assert "DART" in codes
    assert "KRX" in codes
    assert payload["llm"]["provider"]
    assert payload["include_foreign"] is True


@pytest.mark.asyncio
async def test_admin_news_sources_route_respects_foreign_toggle(client):
    await client.put("/api/v1/admin/settings", json={"NEWS_INCLUDE_FOREIGN": False})

    response = await client.get("/api/v1/admin/news/sources")

    assert response.status_code == 200
    payload = response.json()["data"]
    codes = {item["code"] for item in payload["sources"]}
    assert "DART" in codes
    assert "KRX" in codes
    assert "REUTERS" not in codes


@pytest.mark.asyncio
async def test_admin_news_fetch_dart_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(_db, *, days, page_count, corp_code=None):
        assert days == 2
        assert page_count == 25
        assert corp_code == "005930"
        return {"received": 3, "created": 2, "duplicates": 1, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.open_dart_disclosure_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/dart?days=2&page_count=25&corp_code=005930")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 2


@pytest.mark.asyncio
async def test_admin_news_fetch_krx_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(_db, *, page_count):
        assert page_count == 25
        return {"received": 2, "created": 1, "duplicates": 1, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.krx_kind_disclosure_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/krx?page_count=25")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 1


@pytest.mark.asyncio
async def test_admin_news_fetch_yonhap_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(_db, *, limit):
        assert limit == 25
        return {"received": 4, "created": 2, "duplicates": 2, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.yonhap_news_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/yonhap?limit=25")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 2


@pytest.mark.asyncio
async def test_admin_news_fetch_bloomberg_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(*, db, limit):
        assert limit == 15
        return {"received": 3, "created": 2, "duplicates": 1, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.bloomberg_news_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/bloomberg?limit=15")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 2


@pytest.mark.asyncio
async def test_admin_news_fetch_cnbc_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(*, db, limit):
        assert limit == 12
        return {"received": 4, "created": 3, "duplicates": 1, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.cnbc_news_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/cnbc?limit=12")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 3


@pytest.mark.asyncio
async def test_admin_news_fetch_nasdaq_route_returns_summary(client, monkeypatch):
    async def fake_fetch_and_ingest(*, db, limit):
        assert limit == 12
        return {"received": 4, "created": 2, "duplicates": 2, "skipped": 0}

    monkeypatch.setattr(
        "api.routes.admin.nasdaq_news_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/nasdaq?limit=12")

    assert response.status_code == 200
    assert response.json()["data"]["created"] == 2


@pytest.mark.asyncio
async def test_admin_news_fetch_nasdaq_route_returns_502_for_upstream_timeout(client, monkeypatch):
    async def fake_fetch_and_ingest(*, db, limit):
        assert limit == 8
        raise RuntimeError("Nasdaq 소스 응답 지연 또는 비정상 연결")

    monkeypatch.setattr(
        "api.routes.admin.nasdaq_news_service.fetch_and_ingest",
        fake_fetch_and_ingest,
    )

    response = await client.post("/api/v1/admin/news/fetch/nasdaq?limit=8")

    assert response.status_code == 502
    assert response.json()["message"] == "Nasdaq 소스 응답 지연 또는 비정상 연결"


@pytest.mark.asyncio
async def test_admin_news_ingest_and_items_routes(client):
    response = await client.post(
        "/api/v1/admin/news/ingest",
        json={
            "items": [
                {
                    "source_code": "DART",
                    "title": "SK하이닉스 시설투자 공시",
                    "published_at": "2026-04-05T09:11:00+09:00",
                    "symbols": ["A000660"],
                    "url": "https://dart.fss.or.kr/example/11",
                },
                {
                    "source_code": "DART",
                    "title": "SK하이닉스 시설투자 공시",
                    "published_at": "2026-04-05T09:11:00+09:00",
                    "symbols": ["000660"],
                    "url": "https://dart.fss.or.kr/example/11",
                },
            ]
        },
    )

    assert response.status_code == 200
    summary = response.json()["data"]
    assert summary["created"] == 1
    assert summary["duplicates"] == 1

    items_response = await client.get("/api/v1/admin/news/items?symbol=000660&limit=10")
    assert items_response.status_code == 200
    items = items_response.json()["data"]
    assert len(items) == 1
    assert items[0]["source_code"] == "DART"
    assert items[0]["symbols"] == ["000660"]


@pytest.mark.asyncio
async def test_admin_news_overview_route_returns_ingestion_and_performance_summary(client, monkeypatch):
    async def fake_build_summary(_db, *, days: int):
        assert days == 30
        return {
            "window": {"days": 30, "trade_count": 7},
            "overall": {"expectancy": 1250.0},
            "by_strategy": {},
            "by_horizon": {},
            "risk_controls": {
                "cost_gate_blocks": 2,
                "kill_switch_blocks": 1,
                "news_gate_blocks": 4,
                "news_rechecks": 6,
            },
            "news_context": {
                "trade_count": 5,
                "avg_negative_pressure": 0.31,
            },
        }

    monkeypatch.setattr(
        "api.routes.admin.performance_reporting_service.build_summary",
        fake_build_summary,
    )
    monkeypatch.setattr(
        "services.news_reporting_service.news_runtime_service.get_snapshot",
        lambda *, include_foreign: {
            "overall": {
                "last_status": "SUCCESS",
                "last_mode": "MANUAL",
                "last_message": "신규 공시 적재 완료",
                "last_run_at": "2026-04-05T09:12:00+09:00",
                "last_success_at": "2026-04-05T09:12:00+09:00",
            },
            "sources": {
                "DART": {
                    "status": "SUCCESS",
                    "message": "신규 공시 적재 완료",
                    "counts": {"received": 2, "created": 1, "duplicates": 1, "skipped": 0},
                }
            },
        },
    )

    await client.put(
        "/api/v1/admin/settings",
        json={
            "NEWS_LLM_ENABLED": True,
            "NEWS_LLM_PROVIDER": "OLLAMA",
            "NEWS_INCLUDE_FOREIGN": True,
            "NEWS_GATE_ENABLED": True,
            "NEWS_POLL_ENABLED": True,
            "NEWS_NEGATIVE_BLOCK_THRESHOLD": 0.65,
        },
    )

    ingest_response = await client.post(
        "/api/v1/admin/news/ingest",
        json={
            "items": [
                {
                    "source_code": "DART",
                    "title": "삼성전자 신규 투자 공시",
                    "published_at": "2026-04-06T09:11:00+09:00",
                    "symbols": ["005930"],
                    "url": "https://dart.fss.or.kr/example/overview-1",
                },
                {
                    "source_code": "REUTERS",
                    "title": "Memory prices outlook improves",
                    "published_at": "2026-04-05T22:30:00+09:00",
                    "symbols": ["005930"],
                    "url": "https://www.reuters.com/example/overview-2",
                },
            ]
        },
    )
    assert ingest_response.status_code == 200

    response = await client.get("/api/v1/admin/news/overview?recent_limit=5&performance_days=30")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["settings"]["llm_provider"] == "OLLAMA"
    assert payload["settings"]["gate_enabled"] is True
    assert payload["runtime"]["overall"]["last_status"] == "SUCCESS"
    assert payload["ingestion"]["recent_24h_count"] >= 1
    assert payload["ingestion"]["recent_7d_count"] >= 2
    assert payload["performance"]["news_gate_blocks"] == 4
    assert payload["performance"]["news_rechecks"] == 6
    assert payload["performance"]["avg_negative_pressure"] == 0.31
    assert len(payload["recent_items"]) >= 2
