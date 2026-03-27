import pytest

from analysis.llm.llm_factory import LLMFactory
from trading.enums import LLMProvider, LLMTier


class FakeProvider:
    def __init__(self, provider: LLMProvider, available: bool = True, result: str = "ok") -> None:
        self._provider = provider
        self._available = available
        self._result = result
        self.calls: list[tuple[str, str]] = []
        self.model_id = f"{provider.value.lower()}-model"

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def tier(self) -> LLMTier:
        return LLMTier.TIER1

    async def is_available(self) -> bool:
        return self._available

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        return self._result


@pytest.mark.asyncio
async def test_llm_factory_uses_configured_primary_provider(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate("hello", LLMTier.TIER1)

    assert result == "codex-result"
    assert provider == "CODEX"
    assert codex.calls == [("hello", "")]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_llm_factory_falls_back_when_primary_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=False, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate("hello", LLMTier.TIER1)

    assert result == "claude-result"
    assert provider == "CLAUDE_CODE"
    assert codex.calls == []
    assert claude.calls == [("hello", "")]


def test_llm_factory_reports_status_for_both_providers(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER2", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER2", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CLAUDE_CODE_MODEL_TIER1", "haiku")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CLAUDE_CODE_MODEL_TIER2", "sonnet")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER1", "gpt-5-codex")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER2", "gpt-5-codex")

    status = LLMFactory().get_llm_status()

    assert status["tier1"]["provider"] == "CODEX"
    assert status["tier1"]["fallback_provider"] == "CLAUDE_CODE"
    assert status["tier2"]["provider"] == "CLAUDE_CODE"
    assert status["tier2"]["fallback_provider"] == "CODEX"
    assert {item["id"] for item in status["available_providers"]} == {"CLAUDE_CODE", "CODEX"}
