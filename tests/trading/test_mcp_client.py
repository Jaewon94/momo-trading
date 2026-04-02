import pytest

from trading.mcp_client import MCPClient
from trading.models import MCPResponse


@pytest.mark.asyncio
async def test_ensure_connected_rebuilds_stale_transport_state(monkeypatch) -> None:
    client = MCPClient()
    client._post_client = object()
    client._sse_client = object()
    client._sse_task = object()
    client._session_id = None

    calls: list[str] = []

    async def fake_disconnect() -> None:
        calls.append("disconnect")
        client._post_client = None
        client._sse_client = None
        client._sse_task = None
        client._session_id = None

    async def fake_connect() -> None:
        calls.append("connect")
        client._post_client = object()
        client._session_id = "/messages/?session_id=test"

    monkeypatch.setattr(client, "disconnect", fake_disconnect)
    monkeypatch.setattr(client, "connect", fake_connect)

    connected = await client.ensure_connected(force_reconnect=True)

    assert connected is True
    assert client.is_connected is True
    assert calls == ["disconnect", "connect"]


@pytest.mark.asyncio
async def test_call_tool_reconnects_when_session_is_missing(monkeypatch) -> None:
    client = MCPClient()
    client._post_client = object()
    client._session_id = None

    reconnect_calls: list[bool] = []

    async def fake_ensure_connected(force_reconnect: bool = False) -> bool:
        reconnect_calls.append(force_reconnect)
        client._session_id = "/messages/?session_id=test"
        return True

    async def fake_call_tool_inner(tool_name: str, arguments: dict | None, _retry: int) -> MCPResponse:
        return MCPResponse(success=True, data={"tool_name": tool_name, "arguments": arguments or {}})

    monkeypatch.setattr(client, "ensure_connected", fake_ensure_connected)
    monkeypatch.setattr(client, "_call_tool_inner", fake_call_tool_inner)

    response = await client.call_tool("inquery-balance")

    assert response.success is True
    assert response.data == {"tool_name": "inquery-balance", "arguments": {}}
    assert reconnect_calls == [True]

