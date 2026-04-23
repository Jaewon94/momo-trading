async def test_admin_observability_overview_route_returns_payload(client, monkeypatch):
    expected = {
        "window": {"hours": 24, "resolution": "raw"},
        "latest_snapshot": {"host": "mac-local"},
        "resource_summary": {"snapshot_count": 12},
        "resource_series": [{"created_at": "2026-04-08T00:00:00+09:00", "memory_percent": 62.1}],
        "llm": {"total_calls": 3, "provider_breakdown": []},
        "jobs": {"news_poll": {"runs": 2}, "maintenance": {"runs": 1}},
        "storage": {"raw_retention_days": 30},
    }
    realtime_status = {
        "is_connected": True,
        "subscription_count": 41,
        "skipped_subscription_count": 3,
        "polling_fallback_symbols": ["000040", "000041", "000042"],
    }
    expected_realtime_status = {
        "connected": True,
        "subscription_count": 41,
        "skipped_subscription_count": 3,
        "polling_fallback_symbols": ["000040", "000041", "000042"],
    }

    async def fake_build_overview(db, *, hours, points):
        assert hours == 24
        assert points == 120
        return expected

    monkeypatch.setattr(
        "api.routes.admin.observability_reporting_service.build_overview",
        fake_build_overview,
        raising=False,
    )
    monkeypatch.setattr(
        "api.routes.admin.stream_manager",
        type("FakeStreamManager", (), realtime_status)(),
        raising=False,
    )

    response = await client.get("/api/v1/admin/observability/overview")

    assert response.status_code == 200
    assert response.json()["data"] == {**expected, "realtime": expected_realtime_status}


async def test_admin_observability_overview_route_accepts_custom_hours_and_points(client, monkeypatch):
    observed = {}

    async def fake_build_overview(db, *, hours, points):
        observed["hours"] = hours
        observed["points"] = points
        return {"window": {"hours": hours, "resolution": "hourly_rollup"}}

    monkeypatch.setattr(
        "api.routes.admin.observability_reporting_service.build_overview",
        fake_build_overview,
        raising=False,
    )

    response = await client.get("/api/v1/admin/observability/overview?hours=168&points=168")

    assert response.status_code == 200
    assert observed == {"hours": 168, "points": 168}
