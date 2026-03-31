async def test_admin_settings_exposes_manual_llm_provider(client):
    response = await client.get("/api/v1/admin/settings")

    assert response.status_code == 200
    payload = response.json()
    assert "MANUAL_LLM_PROVIDER" in payload["data"]
    assert "LLM_PROVIDER_TIER1" in payload["data"]
    assert "LLM_PROVIDER_TIER2" in payload["data"]
    assert "LLM_FALLBACK_PROVIDER_TIER1" in payload["data"]
    assert "LLM_FALLBACK_PROVIDER_TIER2" in payload["data"]
    assert "LLM_FALLBACK_MODEL_TIER1" in payload["data"]
    assert "LLM_FALLBACK_MODEL_TIER2" in payload["data"]
    assert "CLAUDE_CODE_MODEL" in payload["data"]
    assert "CLAUDE_CODE_MODEL_TIER1" in payload["data"]
    assert "CLAUDE_CODE_MODEL_TIER2" in payload["data"]
    assert "CODEX_MODEL" in payload["data"]
    assert "CODEX_MODEL_TIER1" in payload["data"]
    assert "CODEX_MODEL_TIER2" in payload["data"]


async def test_admin_settings_updates_manual_llm_provider(client):
    response = await client.put(
        "/api/v1/admin/settings",
        json={"MANUAL_LLM_PROVIDER": "CODEX"},
    )

    assert response.status_code == 200

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "CODEX"


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


async def test_llm_status_includes_manual_selection(client):
    response = await client.get("/api/v1/admin/llm/status")

    assert response.status_code == 200
    payload = response.json()
    assert "manual_selection" in payload["data"]
