import pytest


@pytest.mark.asyncio
async def test_admin_mcp_reconnect_route_reconnects_runtime_client(client, monkeypatch):
    calls: list[bool] = []

    async def fake_ensure_connected(force_reconnect: bool = False) -> bool:
        calls.append(force_reconnect)
        monkeypatch.setattr("api.routes.admin.mcp_client._post_client", object(), raising=False)
        monkeypatch.setattr("api.routes.admin.mcp_client._session_id", "/messages/?session_id=test", raising=False)
        return True

    monkeypatch.setattr("api.routes.admin.mcp_client.ensure_connected", fake_ensure_connected)
    monkeypatch.setattr("api.routes.admin.mcp_client._post_client", None, raising=False)
    monkeypatch.setattr("api.routes.admin.mcp_client._session_id", None, raising=False)

    response = await client.post("/api/v1/admin/mcp/reconnect")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["connected"] is True
    assert payload["mcp_connected"] is True
    assert calls == [True]


@pytest.mark.asyncio
async def test_system_status_marks_mcp_as_optional_for_kiwoom(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("api.routes.admin.mcp_client._post_client", None, raising=False)
    monkeypatch.setattr("api.routes.admin.mcp_client._session_id", None, raising=False)
    monkeypatch.setattr("api.routes.admin.trading_scheduler._running", False)
    monkeypatch.setattr("agent.trading_agent.trading_agent._running", True, raising=False)

    response = await client.get("/api/v1/admin/system/status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["broker_provider"] == "KIWOOM"
    assert payload["mcp_required"] is False
    assert payload["mcp_connected"] is False
