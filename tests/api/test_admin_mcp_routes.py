import pytest


@pytest.mark.asyncio
async def test_admin_mcp_reconnect_route_reconnects_runtime_client(client, monkeypatch):
    calls: list[bool] = []

    async def fake_ensure_connected(force_reconnect: bool = False) -> bool:
        calls.append(force_reconnect)
        monkeypatch.setattr("trading.mcp_client.mcp_client._post_client", object(), raising=False)
        monkeypatch.setattr("trading.mcp_client.mcp_client._session_id", "/messages/?session_id=test", raising=False)
        return True

    monkeypatch.setattr(
        "services.broker_runtime_service.BrokerRuntimeService.mcp_required",
        property(lambda self: True),
    )
    monkeypatch.setattr("trading.mcp_client.mcp_client.ensure_connected", fake_ensure_connected)
    monkeypatch.setattr("trading.mcp_client.mcp_client._post_client", None, raising=False)
    monkeypatch.setattr("trading.mcp_client.mcp_client._session_id", None, raising=False)

    response = await client.post("/api/v1/admin/mcp/reconnect")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["connected"] is True
    assert payload["mcp_connected"] is True
    assert calls == [True]


@pytest.mark.asyncio
async def test_system_status_marks_mcp_as_optional_for_kiwoom(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("api.routes.admin.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("api.routes.admin.settings.LLM_PROVIDER_TIER2", "CODEX")
    monkeypatch.setattr("api.routes.admin.settings.LLM_FALLBACK_PROVIDER_TIER1", "")
    monkeypatch.setattr("api.routes.admin.settings.LLM_FALLBACK_PROVIDER_TIER2", "")
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(
        "services.broker_runtime_service.BrokerRuntimeService.mcp_required",
        property(lambda self: False),
    )
    monkeypatch.setattr(
        "services.broker_runtime_service.BrokerRuntimeService.mcp_connected",
        property(lambda self: False),
    )
    monkeypatch.setattr("api.routes.admin.trading_scheduler._running", False)
    monkeypatch.setattr("agent.trading_agent.trading_agent._running", True, raising=False)

    response = await client.get("/api/v1/admin/system/status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["broker_provider"] == "KIWOOM"
    assert payload["mcp_required"] is False
    assert payload["mcp_connected"] is False
    assert payload["market_session"] in {"CLOSED", "NXT_PRE", "KRX_NXT", "KRX_CLOSE", "NXT_AFTER"}
    assert "market_session_label" in payload
    assert "next_market_session" in payload
    assert payload["broker_capabilities"]["supports_nxt_quotes"] is False
    assert payload["broker_capabilities"]["supported_order_sessions"] == ["REGULAR"]
    assert payload["operations"]["broker"]["status"] == "OK"
    assert payload["operations"]["broker"]["supported_sessions"] == ["REGULAR"]
    assert "정규장 주문만 지원" in payload["operations"]["broker"]["message"]
    assert payload["operations"]["ollama"]["status"] == "OK"
    assert payload["operations"]["ollama"]["label"] == "Ollama 미사용"


@pytest.mark.asyncio
async def test_system_status_includes_operations_summary(client, monkeypatch):
    class FakeError:
        summary = "❌ [005930] 주문 실패"
        error_message = "주문 한도 초과"
        symbol = "005930"
        created_at = None

    monkeypatch.setattr("api.routes.admin.settings.BROKER_PROVIDER", "KIS")
    monkeypatch.setattr("api.routes.admin.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_FALLBACK_PROVIDER", "")
    monkeypatch.setattr(
        "services.broker_runtime_service.BrokerRuntimeService.mcp_required",
        property(lambda self: True),
    )
    monkeypatch.setattr(
        "services.broker_runtime_service.BrokerRuntimeService.mcp_connected",
        property(lambda self: False),
    )
    async def fake_ollama_available(self):
        return False
    monkeypatch.setattr("api.routes.admin.OllamaProvider.is_available", fake_ollama_available)
    monkeypatch.setattr(
        "api.routes.admin.news_runtime_service.get_snapshot",
        lambda *, include_foreign: {
            "overall": {
                "last_status": "ERROR",
                "last_message": "DART 응답 실패",
                "last_run_at": "2026-04-06T10:00:00+09:00",
            },
            "sources": {
                "DART": {"status": "ERROR", "message": "DART 응답 실패"},
            },
        },
    )

    async def fake_latest_error(self, *, activity_type=None):
        assert activity_type == "ORDER"
        return FakeError()

    monkeypatch.setattr(
        "api.routes.admin.AgentActivityRepository.get_latest_error",
        fake_latest_error,
    )

    response = await client.get("/api/v1/admin/system/status")

    assert response.status_code == 200
    operations = response.json()["data"]["operations"]
    assert operations["broker"]["status"] == "ERROR"
    assert operations["news_polling"]["status"] == "ERROR"
    assert "DART" in operations["news_polling"]["message"]
    assert operations["ollama"]["status"] == "WARN"
    assert operations["orders"]["status"] == "WARN"
    assert operations["orders"]["message"] == "주문 한도 초과"
