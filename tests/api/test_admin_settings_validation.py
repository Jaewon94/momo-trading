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
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "AUTOMATIC")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"MANUAL_LLM_PROVIDER": "invalid-provider"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["MANUAL_LLM_PROVIDER"] == "AUTOMATIC"


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
    monkeypatch.setattr("api.routes.admin.settings.NEWS_LLM_PROVIDER", "AUTOMATIC")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"NEWS_LLM_PROVIDER": "invalid-provider"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {}

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_LLM_PROVIDER"] == "AUTOMATIC"


@pytest.mark.asyncio
async def test_admin_settings_normalizes_empty_news_ollama_model_to_default(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.NEWS_OLLAMA_MODEL", "qwen2.5:14b")

    response = await client.put(
        "/api/v1/admin/settings",
        json={"NEWS_OLLAMA_MODEL": "   "},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["NEWS_OLLAMA_MODEL"]["new"] == "DEFAULT"

    settings_response = await client.get("/api/v1/admin/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["data"]["NEWS_OLLAMA_MODEL"] == "DEFAULT"


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
