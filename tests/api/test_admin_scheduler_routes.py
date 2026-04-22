import pytest


@pytest.mark.asyncio
async def test_admin_scheduler_start_route_starts_runtime_scheduler(client, monkeypatch):
    calls: list[str] = []

    async def fake_start() -> None:
        calls.append("start")

    monkeypatch.setattr("api.routes.admin.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr("api.routes.admin.trading_scheduler.start", fake_start)
    monkeypatch.setattr("api.routes.admin.trading_scheduler._running", False)

    response = await client.post("/api/v1/admin/scheduler/start")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["enabled"] is True
    assert calls == ["start"]


@pytest.mark.asyncio
async def test_admin_scheduler_stop_route_stops_runtime_scheduler(client, monkeypatch):
    calls: list[str] = []

    async def fake_stop() -> None:
        calls.append("stop")

    monkeypatch.setattr("api.routes.admin.settings.SCHEDULER_ENABLED", True)
    monkeypatch.setattr("api.routes.admin.trading_scheduler.stop", fake_stop)
    monkeypatch.setattr("api.routes.admin.trading_scheduler._running", True)

    response = await client.post("/api/v1/admin/scheduler/stop")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["enabled"] is False
    assert calls == ["stop"]
