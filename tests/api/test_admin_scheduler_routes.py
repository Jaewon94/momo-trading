import pytest


async def _admin_confirmation_token(client, action: str, resource_id: str, quantity: str = "ALL") -> str:
    response = await client.post(
        "/api/v1/admin/actions/confirmations",
        json={"action": action, "resource_id": resource_id, "quantity": quantity},
    )
    assert response.status_code == 200
    return response.json()["data"]["confirmation_token"]


@pytest.mark.asyncio
async def test_admin_scheduler_start_route_starts_runtime_scheduler(client, monkeypatch):
    calls: list[str] = []

    async def fake_start() -> None:
        calls.append("start")

    monkeypatch.setattr("api.routes.admin.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr("api.routes.admin.trading_scheduler.start", fake_start)
    monkeypatch.setattr("api.routes.admin.trading_scheduler._running", False)

    token = await _admin_confirmation_token(client, "START_SCHEDULER", "SCHEDULER")
    response = await client.post(
        "/api/v1/admin/scheduler/start",
        json={"confirmation_token": token},
    )

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

    token = await _admin_confirmation_token(client, "STOP_SCHEDULER", "SCHEDULER")
    response = await client.post(
        "/api/v1/admin/scheduler/stop",
        json={"confirmation_token": token},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["enabled"] is False
    assert calls == ["stop"]


@pytest.mark.asyncio
async def test_admin_scheduler_start_requires_confirmation(client, monkeypatch):
    calls: list[str] = []

    async def fake_start() -> None:
        calls.append("start")

    monkeypatch.setattr("api.routes.admin.trading_scheduler.start", fake_start)

    response = await client.post("/api/v1/admin/scheduler/start")

    assert response.status_code == 428
    assert calls == []
