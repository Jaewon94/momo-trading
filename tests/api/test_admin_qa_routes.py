from trading.enums import LLMTier


async def test_admin_qa_uses_manual_llm_provider(client, monkeypatch):
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_PROVIDER", "CODEX", raising=False)
    monkeypatch.setattr("api.routes.admin.settings.MANUAL_LLM_MODEL", "gpt-5.4", raising=False)

    called = {}

    async def fake_get_account_snapshot():
        return (
            type(
                "Balance",
                (),
                {
                    "is_valid": True,
                    "total_asset": 1_000_000,
                    "cash": 500_000,
                    "stock_value": 500_000,
                    "total_pnl": 25_000,
                    "total_pnl_rate": 2.5,
                },
            )(),
            [],
        )

    async def fake_generate_manual(prompt, system_prompt="", default_tier=None, **kwargs):
        called["prompt"] = prompt
        called["system_prompt"] = system_prompt
        called["default_tier"] = default_tier
        called["manual_provider_override"] = kwargs.get("manual_provider_override")
        called["manual_model_override"] = kwargs.get("manual_model_override")
        return "answer", "CODEX"

    monkeypatch.setattr(
        "api.routes.admin.account_manager.get_account_snapshot",
        fake_get_account_snapshot,
    )
    monkeypatch.setattr(
        "analysis.llm.llm_factory.llm_factory.generate_manual",
        fake_generate_manual,
    )

    response = await client.post(
        "/api/v1/admin/qa/ask",
        json={"question": "요약해줘"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["llm_provider"] == "CODEX"
    assert called["default_tier"] == LLMTier.TIER1
    assert called["manual_provider_override"] == "CODEX"
    assert called["manual_model_override"] == "gpt-5.4"
