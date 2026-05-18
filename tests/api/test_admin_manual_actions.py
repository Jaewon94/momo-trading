import asyncio


async def _admin_confirmation_token(client, action: str, resource_id: str, quantity: str = "ALL") -> str:
    response = await client.post(
        "/api/v1/admin/actions/confirmations",
        json={"action": action, "resource_id": resource_id, "quantity": quantity},
    )
    assert response.status_code == 200
    return response.json()["data"]["confirmation_token"]


async def test_manual_report_generation_passes_manual_provider(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CODEX", raising=False)
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_MODEL", "gpt-5.4", raising=False)

    captured = {}

    async def fake_generate_daily_report(target_date=None, manual_provider_override=None, manual_model_override=None, force_regenerate=False):
        captured["target_date"] = target_date
        captured["manual_provider_override"] = manual_provider_override
        captured["manual_model_override"] = manual_model_override
        return None

    monkeypatch.setattr(
        "services.daily_report_service.daily_report_service.generate_daily_report",
        fake_generate_daily_report,
    )

    response = await client.post("/api/v1/admin/reports/generate")

    assert response.status_code == 200
    assert captured["manual_provider_override"] == "CODEX"
    assert captured["manual_model_override"] == "gpt-5.4"


async def test_manual_cycle_trigger_uses_default_cycle_routing(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CLAUDE_CODE", raising=False)
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_MODEL", "claude-sonnet-4-6", raising=False)

    captured = {}
    original_create_task = asyncio.create_task

    async def fake_run_cycle(*, manual_provider_override=None, manual_model_override=None):
        captured["manual_provider_override"] = manual_provider_override
        captured["manual_model_override"] = manual_model_override
        return {"ok": True}

    def fake_create_task(coro):
        return original_create_task(coro)

    monkeypatch.setattr(
        "agent.trading_agent.trading_agent.run_cycle",
        fake_run_cycle,
    )
    monkeypatch.setattr("api.routes.admin.asyncio.create_task", fake_create_task)

    token = await _admin_confirmation_token(client, "TRIGGER_AGENT_CYCLE", "TRADING_AGENT")
    response = await client.post(
        "/api/v1/admin/agent/trigger",
        json={"confirmation_token": token},
    )
    await asyncio.sleep(0)

    assert response.status_code == 200
    assert captured["manual_provider_override"] is None
    assert captured["manual_model_override"] is None


async def test_manual_cycle_trigger_requires_confirmation(client, monkeypatch):
    calls: list[str] = []

    async def fake_run_cycle(*, manual_provider_override=None, manual_model_override=None):
        calls.append("run")
        return {"ok": True}

    monkeypatch.setattr(
        "agent.trading_agent.trading_agent.run_cycle",
        fake_run_cycle,
    )

    response = await client.post("/api/v1/admin/agent/trigger")
    await asyncio.sleep(0)

    assert response.status_code == 428
    assert calls == []
