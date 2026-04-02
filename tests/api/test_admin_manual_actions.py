import asyncio


async def test_manual_report_generation_passes_manual_provider(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CODEX", raising=False)

    captured = {}

    async def fake_generate_daily_report(target_date=None, manual_provider_override=None):
        captured["target_date"] = target_date
        captured["manual_provider_override"] = manual_provider_override
        return None

    monkeypatch.setattr(
        "services.daily_report_service.daily_report_service.generate_daily_report",
        fake_generate_daily_report,
    )

    response = await client.post("/api/v1/admin/reports/generate")

    assert response.status_code == 200
    assert captured["manual_provider_override"] == "CODEX"


async def test_manual_cycle_trigger_captures_manual_provider(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CLAUDE_CODE", raising=False)

    captured = {}
    original_create_task = asyncio.create_task

    async def fake_run_cycle(*, manual_provider_override=None):
        captured["manual_provider_override"] = manual_provider_override
        return {"ok": True}

    def fake_create_task(coro):
        return original_create_task(coro)

    monkeypatch.setattr(
        "agent.trading_agent.trading_agent.run_cycle",
        fake_run_cycle,
    )
    monkeypatch.setattr("api.routes.admin.asyncio.create_task", fake_create_task)

    response = await client.post("/api/v1/admin/agent/trigger")
    await asyncio.sleep(0)

    assert response.status_code == 200
    assert captured["manual_provider_override"] == "CLAUDE_CODE"
