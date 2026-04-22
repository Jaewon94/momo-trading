import pytest


@pytest.mark.asyncio
async def test_llm_usage_service_returns_provider_scoped_snapshot(monkeypatch):
    from services.llm_usage_service import LLMUsageService

    service = LLMUsageService()

    async def fake_claude() -> dict:
        return {
            "provider": "CLAUDE_CODE",
            "available": True,
            "auth": {"logged_in": True},
            "official": {"live_rate_limits_supported": True},
        }

    async def fake_codex() -> dict:
        return {
            "provider": "CODEX",
            "available": True,
            "auth": {"logged_in": True},
            "official": {"local_remaining_usage_supported": False},
        }

    monkeypatch.setattr(service, "_collect_claude_code_usage", fake_claude)
    monkeypatch.setattr(service, "_collect_codex_usage", fake_codex)

    snapshot = await service.get_snapshot()

    assert snapshot["claude_code"]["official"]["live_rate_limits_supported"] is True
    assert snapshot["codex"]["official"]["local_remaining_usage_supported"] is False
    assert "updated_at" in snapshot
