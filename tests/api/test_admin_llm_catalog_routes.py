async def test_admin_llm_catalog_route_returns_catalog_payload(client, monkeypatch):
    expected = {
        "fetched_at": "2026-03-31T12:30:00+09:00",
        "stale": False,
        "providers": [
            {
                "id": "CLAUDE_CODE",
                "entries": [
                    {"value": "DEFAULT", "label": "기본값 사용"},
                    {"value": "sonnet", "label": "sonnet"},
                ],
            },
            {
                "id": "CODEX",
                "entries": [
                    {"value": "DEFAULT", "label": "기본값 사용"},
                    {"value": "gpt-5-codex", "label": "gpt-5-codex"},
                ],
            },
        ],
    }

    async def fake_get_catalog(*, force_refresh=False):
        assert force_refresh is False
        return expected

    monkeypatch.setattr(
        "api.routes.admin.model_catalog_service.get_catalog",
        fake_get_catalog,
        raising=False,
    )

    response = await client.get("/api/v1/admin/llm/catalog")

    assert response.status_code == 200
    assert response.json()["data"] == expected


async def test_admin_llm_catalog_route_supports_force_refresh(client, monkeypatch):
    captured = {"force_refresh": None}

    async def fake_get_catalog(*, force_refresh=False):
        captured["force_refresh"] = force_refresh
        return {"fetched_at": None, "stale": False, "providers": []}

    monkeypatch.setattr(
        "api.routes.admin.model_catalog_service.get_catalog",
        fake_get_catalog,
        raising=False,
    )

    response = await client.get("/api/v1/admin/llm/catalog?force_refresh=true")

    assert response.status_code == 200
    assert captured["force_refresh"] is True
