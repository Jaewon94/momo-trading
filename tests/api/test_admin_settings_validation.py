import pytest


@pytest.mark.asyncio
async def test_admin_settings_ignores_unknown_keys(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"UNKNOWN_SETTING": "value"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == {}


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_manual_provider_without_overwriting(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CLAUDE_CODE")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"MANUAL_LLM_PROVIDER": "invalid-provider"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "CLAUDE_CODE"


@pytest.mark.asyncio
async def test_admin_settings_normalizes_empty_manual_model_to_default(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_MODEL", "gpt-5.4")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"MANUAL_LLM_MODEL": "   "},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["MANUAL_LLM_MODEL"]["new"] == "DEFAULT"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_news_provider_without_overwriting(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_PROVIDER", "CLAUDE_CODE")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"NEWS_LLM_PROVIDER": "invalid-provider"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_LLM_PROVIDER"] == "CLAUDE_CODE"


@pytest.mark.asyncio
async def test_admin_settings_accepts_execution_modes_case_insensitively(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "LLM_EXECUTION_MODE_TIER1": "distributed",
            "LLM_EXECUTION_MODE_TIER2": "consensus",
            "MANUAL_LLM_EXECUTION_MODE": "single",
            "NEWS_LLM_EXECUTION_MODE": "DISTRIBUTED",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["LLM_EXECUTION_MODE_TIER1"]["new"] == "DISTRIBUTED"
    assert payload["LLM_EXECUTION_MODE_TIER2"]["new"] == "CONSENSUS"
    assert payload["MANUAL_LLM_EXECUTION_MODE"]["new"] == "SINGLE"
    assert payload["NEWS_LLM_EXECUTION_MODE"]["new"] == "DISTRIBUTED"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_execution_mode_without_overwriting(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.LLM_EXECUTION_MODE_TIER2", "SINGLE", raising=False)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"LLM_EXECUTION_MODE_TIER2": "PARALLEL"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["LLM_EXECUTION_MODE_TIER2"] == "SINGLE"


@pytest.mark.asyncio
async def test_admin_settings_accepts_deterministic_tier1_fast_gate_mode_case_insensitively(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"DETERMINISTIC_TIER1_FAST_GATE_MODE": "shadow"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["DETERMINISTIC_TIER1_FAST_GATE_MODE"]["new"] == "SHADOW"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_deterministic_tier1_fast_gate_mode(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.DETERMINISTIC_TIER1_FAST_GATE_MODE", "ENFORCE", raising=False)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"DETERMINISTIC_TIER1_FAST_GATE_MODE": "PARALLEL"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["DETERMINISTIC_TIER1_FAST_GATE_MODE"] == "ENFORCE"


@pytest.mark.asyncio
async def test_llm_api_key_registry_adds_masks_counts_and_deletes_api_workers(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.LLM_API_KEY_REGISTRY", [], raising=False)

    async def fake_llm_usage_snapshot():
        return {
            "claude_code": {"available": True},
            "codex": {"available": True},
        }

    monkeypatch.setattr(
        "api.routes.admin.llm_usage_service.get_snapshot",
        fake_llm_usage_snapshot,
    )
    secret = "sk-ant-test-secret-123456"

    create_response = await client.post(
        "/api/v1/admin/llm/api-keys",
        json={
            "provider": "CLAUDE_API",
            "label": "claude-fast-worker",
            "api_key": secret,
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["provider"] == "CLAUDE_API"
    assert created["label"] == "claude-fast-worker"
    assert created["configured"] is True
    assert created["masked"] == "sk-a...3456"
    assert secret not in str(create_response.json())

    status_response = await client.get("/api/v1/admin/llm/api-keys")

    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["CLAUDE_CODE"]["configured"] is True
    assert status["CLAUDE_CODE"]["masked"] == "sk-a...3456"
    assert status["worker_summary"]["cli_slots"] == 2
    assert status["worker_summary"]["api_slots"] == 1
    assert status["worker_summary"]["total_slots"] == 3
    assert status["items"][0]["id"] == created["id"]
    assert secret not in str(status_response.json())

    delete_response = await client.delete(f"/api/v1/admin/llm/api-keys/{created['id']}")

    assert delete_response.status_code == 200

    empty_response = await client.get("/api/v1/admin/llm/api-keys")

    assert empty_response.status_code == 200
    assert empty_response.json()["data"]["CLAUDE_CODE"]["configured"] is False
    assert empty_response.json()["data"]["worker_summary"]["api_slots"] == 0
    assert empty_response.json()["data"]["worker_summary"]["total_slots"] == 2


@pytest.mark.asyncio
async def test_admin_settings_accepts_account_equity_drawdown_guard_mode(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE": "block_buy"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE"]["new"] == "BLOCK_BUY"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE"] == "BLOCK_BUY"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_account_equity_drawdown_guard_mode(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "REPORT_ONLY")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE": "INVALID"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE"] == "REPORT_ONLY"


@pytest.mark.asyncio
async def test_admin_settings_accepts_account_equity_drawdown_thresholds(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT": "0.5",
            "ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT": "1.0",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT"]["new"] == 0.5
    assert payload["ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT"]["new"] == 1.0


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_account_equity_drawdown_threshold(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT": -0.1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT must be between 0 and 100"


@pytest.mark.asyncio
async def test_admin_settings_accepts_loss_streak_recovery_mode(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={
            "LOSS_STREAK_RECOVERY_MODE": "probation",
            "LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS": "1",
            "LOSS_STREAK_RECOVERY_MAX_ORDER_KRW": "1000000",
            "LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER": "0.2",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["LOSS_STREAK_RECOVERY_MODE"]["new"] == "PROBATION"
    assert payload["LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS"]["new"] == 1
    assert payload["LOSS_STREAK_RECOVERY_MAX_ORDER_KRW"]["new"] == 1_000_000
    assert payload["LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER"]["new"] == 0.2


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_loss_streak_recovery_multiplier(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER": 1.5},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER must be between 0 and 1"


@pytest.mark.asyncio
async def test_admin_settings_normalizes_empty_news_model_to_default(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_MODEL", "qwen2.5:14b")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"NEWS_LLM_MODEL": "   "},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["NEWS_LLM_MODEL"]["new"] == "DEFAULT"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_LLM_MODEL"] == "DEFAULT"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_ollama_base_url_type(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.OLLAMA_BASE_URL", "http://localhost:11434")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"OLLAMA_BASE_URL": 123},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["OLLAMA_BASE_URL"]["new"] == "123"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_tier_provider_without_overwriting(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.LLM_PROVIDER_TIER1", "CLAUDE_CODE")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"LLM_PROVIDER_TIER1": "not-a-provider"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["LLM_PROVIDER_TIER1"] == "CLAUDE_CODE"


@pytest.mark.asyncio
async def test_admin_settings_normalizes_empty_model_value_to_default(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.CODEX_MODEL", "gpt-5.4")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"CODEX_MODEL": "   "},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["CODEX_MODEL"]["new"] == "DEFAULT"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["CODEX_MODEL"] == "DEFAULT"


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_integer_value_with_clear_400(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.RECOMMENDATION_EXPIRE_MIN", 60)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"RECOMMENDATION_EXPIRE_MIN": "abc"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "RECOMMENDATION_EXPIRE_MIN must be an integer"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["RECOMMENDATION_EXPIRE_MIN"] == 60


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_news_concurrency_range(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.NEWS_FETCH_CONCURRENCY", 4)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"NEWS_FETCH_CONCURRENCY": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "NEWS_FETCH_CONCURRENCY must be between 1 and 8"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_FETCH_CONCURRENCY"] == 4


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_llm_concurrency_range(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.LLM_TIER1_CONCURRENCY", 2)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"LLM_TIER1_CONCURRENCY": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "LLM_TIER1_CONCURRENCY must be between 1 and 8"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["LLM_TIER1_CONCURRENCY"] == 2


@pytest.mark.asyncio
async def test_admin_settings_rejects_invalid_codex_timeout_range(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.CODEX_TIMEOUT_SEC_TIER1", 90)

    response = await client.put(
        "/api/v1/admin/settings",
        json={"CODEX_TIMEOUT_SEC_TIER1": 20},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "CODEX_TIMEOUT_SEC_TIER1 must be between 30 and 300"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["CODEX_TIMEOUT_SEC_TIER1"] == 90


@pytest.mark.asyncio
async def test_admin_settings_rejects_codex_max_reasoning_effort(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.CODEX_REASONING_EFFORT_TIER1", "low")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"CODEX_REASONING_EFFORT_TIER1": "max"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["CODEX_REASONING_EFFORT_TIER1"] == "low"


@pytest.mark.asyncio
async def test_admin_settings_accepts_claude_max_effort(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"CLAUDE_CODE_EFFORT_TIER2": "max"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["CLAUDE_CODE_EFFORT_TIER2"]["new"] == "max"
