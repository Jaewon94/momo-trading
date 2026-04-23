import pytest


@pytest.mark.asyncio
async def test_admin_performance_summary_route_returns_service_payload(client, monkeypatch):
    expected = {
        "window": {"days": 30, "trade_count": 12},
        "overall": {"expectancy": 1200.0},
        "by_strategy": {},
        "by_horizon": {},
        "risk_controls": {"cost_gate_blocks": 3, "kill_switch_blocks": 1},
    }

    async def fake_build_summary(_db, *, days: int):
        assert days == 30
        return expected

    monkeypatch.setattr(
        "api.routes.admin.performance_reporting_service.build_summary",
        fake_build_summary,
    )

    response = await client.get("/api/v1/admin/performance/summary?days=30")
    assert response.status_code == 200
    assert response.json()["data"] == expected


@pytest.mark.asyncio
async def test_admin_performance_periodic_route_validates_period(client):
    response = await client.get("/api/v1/admin/performance/periodic?period=daily")
    assert response.status_code == 400
    assert response.json()["detail"] == "period must be weekly or monthly"


@pytest.mark.asyncio
async def test_admin_performance_decision_benchmark_route_returns_service_payload(client, monkeypatch):
    expected = {
        "window": {"days": 14, "horizon": "close"},
        "sample_status": "READY",
        "overall": {"event_count": 12},
    }

    async def fake_build_report(_session_factory, *, days: int, horizon: str, min_sample_size: int):
        assert days == 14
        assert horizon == "close"
        assert min_sample_size == 5
        return expected

    monkeypatch.setattr(
        "api.routes.admin.decision_benchmark_service.build_report",
        fake_build_report,
    )

    response = await client.get(
        "/api/v1/admin/performance/decision-benchmark?days=14&horizon=close&min_sample_size=5"
    )
    assert response.status_code == 200
    assert response.json()["data"] == expected
