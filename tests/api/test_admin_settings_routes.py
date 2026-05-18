async def _admin_confirmation_token(client, action: str, resource_id: str, quantity: str = "ALL") -> str:
    response = await client.post(
        "/api/v1/admin/actions/confirmations",
        json={"action": action, "resource_id": resource_id, "quantity": quantity},
    )
    assert response.status_code == 200
    return response.json()["data"]["confirmation_token"]


async def test_admin_settings_exposes_manual_llm_provider(client):
    response = await client.get("/api/v1/admin/settings")

    assert response.status_code == 200
    payload = response.json()
    assert "MANUAL_LLM_PROVIDER" in payload["data"]
    assert "MANUAL_LLM_MODEL" in payload["data"]
    assert "LLM_PROVIDER_TIER1" in payload["data"]
    assert "LLM_PROVIDER_TIER2" in payload["data"]
    assert "LLM_FALLBACK_PROVIDER_TIER1" in payload["data"]
    assert "LLM_FALLBACK_PROVIDER_TIER2" in payload["data"]
    assert "LLM_FALLBACK_MODEL_TIER1" in payload["data"]
    assert "LLM_FALLBACK_MODEL_TIER2" in payload["data"]
    assert "CLAUDE_CODE_MODEL" in payload["data"]
    assert "CLAUDE_CODE_MODEL_TIER1" in payload["data"]
    assert "CLAUDE_CODE_MODEL_TIER2" in payload["data"]
    assert "CLAUDE_CODE_EFFORT_TIER1" in payload["data"]
    assert "CLAUDE_CODE_EFFORT_TIER2" in payload["data"]
    assert "CLAUDE_CODE_BARE_TIER1" in payload["data"]
    assert "CLAUDE_CODE_BARE_TIER2" in payload["data"]
    assert "CODEX_MODEL" in payload["data"]
    assert "CODEX_MODEL_TIER1" in payload["data"]
    assert "CODEX_MODEL_TIER2" in payload["data"]
    assert "CODEX_REASONING_EFFORT_TIER1" in payload["data"]
    assert "CODEX_REASONING_EFFORT_TIER2" in payload["data"]
    assert "CODEX_TIMEOUT_SEC_TIER1" in payload["data"]
    assert "CODEX_TIMEOUT_SEC_TIER2" in payload["data"]
    assert "LLM_EXECUTION_MODE_TIER1" in payload["data"]
    assert "LLM_EXECUTION_MODE_TIER2" in payload["data"]
    assert "LLM_TIER1_CONCURRENCY" in payload["data"]
    assert "LLM_TIER2_CONCURRENCY" in payload["data"]
    assert "NEWS_LLM_ENABLED" in payload["data"]
    assert "MANUAL_LLM_EXECUTION_MODE" in payload["data"]
    assert "NEWS_LLM_PROVIDER" in payload["data"]
    assert "NEWS_LLM_EXECUTION_MODE" in payload["data"]
    assert "MANUAL_LLM_FALLBACK_PROVIDER" in payload["data"]
    assert "MANUAL_LLM_FALLBACK_MODEL" in payload["data"]
    assert "NEWS_LLM_MODEL" in payload["data"]
    assert "NEWS_LLM_FALLBACK_PROVIDER" in payload["data"]
    assert "NEWS_LLM_FALLBACK_MODEL" in payload["data"]
    assert "NEWS_DOMESTIC_MEDIA_ENABLED" in payload["data"]
    assert "NEWS_INCLUDE_FOREIGN" in payload["data"]
    assert "NEWS_TRANSLATE_FOREIGN_ENABLED" in payload["data"]
    assert "NEWS_NASDAQ_ENABLED" in payload["data"]
    assert "NEWS_GATE_ROLLOUT_MODE" in payload["data"]
    assert "NEWS_GATE_ENABLED" in payload["data"]
    assert "NEWS_LOOKBACK_HOURS" in payload["data"]
    assert "NEWS_NEGATIVE_BLOCK_THRESHOLD" in payload["data"]
    assert "NEWS_POLL_ENABLED" in payload["data"]
    assert "NEWS_POLL_INTERVAL_MIN_TRADING" in payload["data"]
    assert "NEWS_FETCH_CONCURRENCY" in payload["data"]
    assert "NEWS_TRANSLATION_CONCURRENCY" in payload["data"]
    assert "NEWS_CLAUDE_SHARE_SESSION" in payload["data"]
    assert "NEWS_SHADOW_ENABLED" in payload["data"]
    assert "NEWS_ROLLOUT_MIN_SAMPLE_SIZE" in payload["data"]
    assert "NEWS_ROLLOUT_MIN_PROFIT_FACTOR" in payload["data"]
    assert "NEWS_ROLLOUT_MIN_EXPECTANCY" in payload["data"]
    assert "NEWS_ROLLOUT_MAX_DRAWDOWN_KRW" in payload["data"]
    assert "OLLAMA_BASE_URL" in payload["data"]
    assert "OLLAMA_MODEL" in payload["data"]
    assert "OLLAMA_MODEL_TIER1" in payload["data"]
    assert "OLLAMA_MODEL_TIER2" in payload["data"]
    assert "strategy_insights" in payload["data"]
    assert "ORDER_SUBMISSION_MODE" in payload["data"]
    assert "ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE" in payload["data"]


async def test_admin_system_status_exposes_effective_order_submission_mode(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("api.routes.admin.settings.ORDER_SUBMISSION_MODE", "SELL_ONLY", raising=False)

    response = await client.get("/api/v1/admin/system/status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["effective_order_submission_mode"] == "SELL_ONLY"
    assert payload["runtime_override_active"] is True


async def test_admin_settings_updates_manual_llm_provider(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "MANUAL_LLM_PROVIDER": "CODEX",
            "MANUAL_LLM_MODEL": "gpt-5.4",
            "MANUAL_LLM_FALLBACK_PROVIDER": "CLAUDE_CODE",
            "MANUAL_LLM_FALLBACK_MODEL": "claude-sonnet-4-6",
        },
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "CODEX"
    assert settings_response.json()["data"]["MANUAL_LLM_MODEL"] == "gpt-5.4"
    assert settings_response.json()["data"]["MANUAL_LLM_FALLBACK_PROVIDER"] == "CLAUDE_CODE"
    assert settings_response.json()["data"]["MANUAL_LLM_FALLBACK_MODEL"] == "claude-sonnet-4-6"


async def test_admin_settings_updates_news_llm_provider(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "NEWS_LLM_PROVIDER": "OLLAMA",
            "NEWS_LLM_MODEL": "qwen2.5:14b",
            "NEWS_LLM_FALLBACK_PROVIDER": "CODEX",
            "NEWS_LLM_FALLBACK_MODEL": "gpt-5.4",
            "NEWS_LLM_ENABLED": False,
            "NEWS_DOMESTIC_MEDIA_ENABLED": True,
            "NEWS_INCLUDE_FOREIGN": False,
            "NEWS_TRANSLATE_FOREIGN_ENABLED": False,
            "NEWS_NASDAQ_ENABLED": False,
            "NEWS_GATE_ROLLOUT_MODE": "SHADOW_ONLY",
            "NEWS_GATE_ENABLED": False,
            "NEWS_POLL_ENABLED": False,
            "NEWS_POLL_INTERVAL_MIN_TRADING": 7,
            "NEWS_FETCH_CONCURRENCY": 5,
            "NEWS_TRANSLATION_CONCURRENCY": 2,
            "NEWS_CLAUDE_SHARE_SESSION": False,
            "NEWS_SHADOW_ENABLED": False,
            "NEWS_ROLLOUT_MIN_SAMPLE_SIZE": 18,
            "NEWS_ROLLOUT_MIN_PROFIT_FACTOR": 1.25,
            "NEWS_ROLLOUT_MIN_EXPECTANCY": 320.0,
            "NEWS_ROLLOUT_MAX_DRAWDOWN_KRW": 750000,
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "OLLAMA_MODEL_TIER1": "qwen2.5:7b",
        },
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_LLM_PROVIDER"] == "OLLAMA"
    assert settings_response.json()["data"]["NEWS_LLM_MODEL"] == "qwen2.5:14b"
    assert settings_response.json()["data"]["NEWS_LLM_FALLBACK_PROVIDER"] == "CODEX"
    assert settings_response.json()["data"]["NEWS_LLM_FALLBACK_MODEL"] == "gpt-5.4"
    assert settings_response.json()["data"]["NEWS_LLM_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_DOMESTIC_MEDIA_ENABLED"] is True
    assert settings_response.json()["data"]["NEWS_INCLUDE_FOREIGN"] is False
    assert settings_response.json()["data"]["NEWS_TRANSLATE_FOREIGN_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_NASDAQ_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_GATE_ROLLOUT_MODE"] == "SHADOW_ONLY"
    assert settings_response.json()["data"]["NEWS_GATE_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_POLL_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_POLL_INTERVAL_MIN_TRADING"] == 7
    assert settings_response.json()["data"]["NEWS_FETCH_CONCURRENCY"] == 5
    assert settings_response.json()["data"]["NEWS_TRANSLATION_CONCURRENCY"] == 2
    assert settings_response.json()["data"]["NEWS_CLAUDE_SHARE_SESSION"] is False
    assert settings_response.json()["data"]["NEWS_SHADOW_ENABLED"] is False
    assert settings_response.json()["data"]["NEWS_ROLLOUT_MIN_SAMPLE_SIZE"] == 18
    assert settings_response.json()["data"]["NEWS_ROLLOUT_MIN_PROFIT_FACTOR"] == 1.25
    assert settings_response.json()["data"]["NEWS_ROLLOUT_MIN_EXPECTANCY"] == 320.0
    assert settings_response.json()["data"]["NEWS_ROLLOUT_MAX_DRAWDOWN_KRW"] == 750000.0
    assert settings_response.json()["data"]["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
    assert settings_response.json()["data"]["OLLAMA_MODEL_TIER1"] == "qwen2.5:7b"


async def test_admin_settings_updates_tier_provider_and_fallback(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "LLM_PROVIDER_TIER1": "CLAUDE_CODE",
            "LLM_FALLBACK_PROVIDER_TIER1": "",
            "LLM_PROVIDER_TIER2": "CODEX",
            "LLM_FALLBACK_PROVIDER_TIER2": "CLAUDE_CODE",
        },
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    payload = settings_response.json()["data"]
    assert payload["LLM_PROVIDER_TIER1"] == "CLAUDE_CODE"
    assert payload["LLM_FALLBACK_PROVIDER_TIER1"] == ""
    assert payload["LLM_PROVIDER_TIER2"] == "CODEX"
    assert payload["LLM_FALLBACK_PROVIDER_TIER2"] == "CLAUDE_CODE"


async def test_admin_settings_updates_provider_models_and_default_mode(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "CLAUDE_CODE_MODEL_TIER1": "DEFAULT",
            "CLAUDE_CODE_MODEL_TIER2": "claude-sonnet-4-6",
            "CODEX_MODEL_TIER1": "",
            "CODEX_MODEL_TIER2": "gpt-5.4",
            "LLM_FALLBACK_MODEL_TIER1": "claude-opus-4-6",
            "LLM_FALLBACK_MODEL_TIER2": "",
        },
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    payload = settings_response.json()["data"]
    assert payload["CLAUDE_CODE_MODEL_TIER1"] == "DEFAULT"
    assert payload["CLAUDE_CODE_MODEL_TIER2"] == "claude-sonnet-4-6"
    assert payload["CODEX_MODEL_TIER1"] == "DEFAULT"
    assert payload["CODEX_MODEL_TIER2"] == "gpt-5.4"
    assert payload["LLM_FALLBACK_MODEL_TIER1"] == "claude-opus-4-6"
    assert payload["LLM_FALLBACK_MODEL_TIER2"] == "DEFAULT"


async def test_admin_settings_updates_llm_runtime_controls(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "LLM_TIER1_CONCURRENCY": 2,
            "LLM_TIER2_CONCURRENCY": 1,
            "CODEX_TIMEOUT_SEC_TIER1": 90,
            "CODEX_TIMEOUT_SEC_TIER2": 180,
            "CLAUDE_CODE_EFFORT_TIER1": "low",
            "CLAUDE_CODE_EFFORT_TIER2": "xhigh",
            "CLAUDE_CODE_BARE_TIER1": True,
            "CLAUDE_CODE_BARE_TIER2": False,
            "CODEX_REASONING_EFFORT_TIER1": "low",
            "CODEX_REASONING_EFFORT_TIER2": "high",
        },
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    payload = settings_response.json()["data"]
    assert payload["LLM_TIER1_CONCURRENCY"] == 2
    assert payload["LLM_TIER2_CONCURRENCY"] == 1
    assert payload["CODEX_TIMEOUT_SEC_TIER1"] == 90
    assert payload["CODEX_TIMEOUT_SEC_TIER2"] == 180
    assert payload["CLAUDE_CODE_EFFORT_TIER1"] == "low"
    assert payload["CLAUDE_CODE_EFFORT_TIER2"] == "xhigh"
    assert payload["CLAUDE_CODE_BARE_TIER1"] is True
    assert payload["CLAUDE_CODE_BARE_TIER2"] is False
    assert payload["CODEX_REASONING_EFFORT_TIER1"] == "low"
    assert payload["CODEX_REASONING_EFFORT_TIER2"] == "high"


async def test_admin_settings_persists_across_runtime_reload(client):
    from core.config import settings
    from services.runtime_settings_service import runtime_settings_service

    original = settings.MANUAL_LLM_PROVIDER

    try:
        response = await client.put(
            "/api/v1/admin/settings",
            json={"MANUAL_LLM_PROVIDER": "CODEX"},
        )

        assert response.status_code == 200

        settings.MANUAL_LLM_PROVIDER = original
        await runtime_settings_service.apply_persisted_settings()

        settings_response = await client.get("/api/v1/admin/settings")
        assert settings_response.status_code == 200
        assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "CODEX"
    finally:
        settings.MANUAL_LLM_PROVIDER = original


async def test_admin_scheduler_routes_persist_enabled_flag(client, monkeypatch):
    from core.config import settings
    from services.runtime_settings_service import runtime_settings_service

    original = settings.SCHEDULER_ENABLED

    async def fake_start() -> None:
        return None

    async def fake_stop() -> None:
        return None

    try:
        monkeypatch.setattr("api.routes.admin.trading_scheduler.start", fake_start)
        monkeypatch.setattr("api.routes.admin.trading_scheduler.stop", fake_stop)
        monkeypatch.setattr("api.routes.admin.trading_scheduler._running", False)

        stop_token = await _admin_confirmation_token(client, "STOP_SCHEDULER", "SCHEDULER")
        stop_response = await client.post(
            "/api/v1/admin/scheduler/stop",
            json={"confirmation_token": stop_token},
        )
        assert stop_response.status_code == 200
        settings.SCHEDULER_ENABLED = original
        await runtime_settings_service.apply_persisted_settings()
        assert settings.SCHEDULER_ENABLED is False

        start_token = await _admin_confirmation_token(client, "START_SCHEDULER", "SCHEDULER")
        start_response = await client.post(
            "/api/v1/admin/scheduler/start",
            json={"confirmation_token": start_token},
        )
        assert start_response.status_code == 200
        settings.SCHEDULER_ENABLED = False
        await runtime_settings_service.apply_persisted_settings()
        assert settings.SCHEDULER_ENABLED is True
    finally:
        settings.SCHEDULER_ENABLED = original


async def test_admin_settings_apply_route_returns_reconfiguration_summary(client, monkeypatch):
    captured = {}

    async def fake_apply_settings(updates):
        captured["updates"] = updates
        return {
            "changed": {
                "LLM_TIER1_CONCURRENCY": {"old": 2, "new": 3},
            },
            "reconfiguration": {
                "scheduler_restarted": True,
                "agent_idle": True,
                "scheduler_idle": True,
            },
        }

    monkeypatch.setattr(
        "api.routes.admin.runtime_reconfiguration_service.apply_settings",
        fake_apply_settings,
    )

    response = await client.post(
        "/api/v1/admin/settings/apply",
        json={"LLM_TIER1_CONCURRENCY": 3},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert captured["updates"] == {"LLM_TIER1_CONCURRENCY": 3}
    assert payload["changed"]["LLM_TIER1_CONCURRENCY"]["new"] == 3
    assert payload["reconfiguration"]["scheduler_restarted"] is True


async def test_admin_settings_apply_requires_confirmation_for_trading_controls(client, monkeypatch):
    called = False

    async def fake_apply_settings(updates):
        nonlocal called
        called = True
        return {"changed": {}, "reconfiguration": {}}

    monkeypatch.setattr(
        "api.routes.admin.runtime_reconfiguration_service.apply_settings",
        fake_apply_settings,
    )

    response = await client.post(
        "/api/v1/admin/settings/apply",
        json={"TRADING_ENABLED": True},
    )

    assert response.status_code == 428
    assert called is False


async def test_llm_status_includes_manual_selection(client):
    response = await client.get("/api/v1/admin/llm/status")

    assert response.status_code == 200
    payload = response.json()
    assert "manual_selection" in payload["data"]


async def test_llm_status_exposes_provider_runtime_visibility(client, monkeypatch):
    from analysis.llm import llm_factory as llm_factory_module

    monkeypatch.setattr(
        llm_factory_module.llm_factory,
        "get_llm_status",
        lambda: {
            "tier1": {"provider": "CODEX"},
            "tier2": {"provider": "CLAUDE_CODE"},
            "available_providers": [
                {
                    "id": "CODEX",
                    "runtime": {
                        "available": False,
                        "cooldown_active": True,
                        "last_failure_kind": "timeout",
                        "last_failure_reason": "Codex CLI timeout (60s)",
                        "disabled_for_sec": 120,
                    },
                }
            ],
            "manual_selection": {"provider": "CODEX", "fallback_provider": "CLAUDE_CODE"},
        },
        raising=False,
    )

    response = await client.get("/api/v1/admin/llm/status")

    assert response.status_code == 200
    runtime = response.json()["data"]["available_providers"][0]["runtime"]
    assert runtime["cooldown_active"] is True
    assert runtime["last_failure_kind"] == "timeout"


async def test_admin_settings_includes_risk_appetite_insights(client):
    response = await client.get("/api/v1/admin/settings")

    assert response.status_code == 200
    payload = response.json()["data"]["strategy_insights"]
    assert payload["selected_risk_appetite"] in {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
    assert payload["risk_appetites"]["MODERATE"]["label"] == "중립"
    assert "AI 자율 한도 결정" in payload["risk_appetites"]["MODERATE"]["system_effects"][0]
