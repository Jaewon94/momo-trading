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
        self.status = {
            "available": available,
            "cooldown_active": False,
            "last_failure_reason": "",
            "last_failure_kind": "",
            "disabled_for_sec": 0,
            "cli_path": f"/tmp/{provider.value.lower()}",
        }

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

    def status_snapshot(self) -> dict:
        return dict(self.status)


class FakeFailingProvider(FakeProvider):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, available=True, result="")

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        self._available = False
        raise RuntimeError("provider failed")


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
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER1", "DEFAULT")

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
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER1", "claude-opus-4-6")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER2", "DEFAULT")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CLAUDE_CODE_MODEL_TIER1", "DEFAULT")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CLAUDE_CODE_MODEL_TIER2", "claude-sonnet-4-6")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER1", "DEFAULT")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER2", "gpt-5-codex")

    status = LLMFactory().get_llm_status()

    assert status["tier1"]["provider"] == "CODEX"
    assert status["tier1"]["fallback_provider"] == "CLAUDE_CODE"
    assert status["tier1"]["fallback_model"] == "claude-opus-4-6"
    assert status["tier1"]["fallback_model_mode"] == "explicit"
    assert status["tier1"]["model"] == "DEFAULT"
    assert status["tier1"]["model_mode"] == "default"
    assert status["tier2"]["provider"] == "CLAUDE_CODE"
    assert status["tier2"]["fallback_provider"] == "CODEX"
    assert status["tier2"]["fallback_model"] == "DEFAULT"
    assert status["tier2"]["fallback_model_mode"] == "default"
    assert status["tier2"]["model"] == "claude-sonnet-4-6"
    assert status["tier2"]["model_mode"] == "explicit"
    assert {item["id"] for item in status["available_providers"]} == {"CLAUDE_CODE", "CODEX", "OLLAMA"}


def test_llm_factory_includes_provider_runtime_status(monkeypatch) -> None:
    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=False)
    codex.status.update({
        "available": False,
        "cooldown_active": True,
        "last_failure_reason": "Codex CLI timeout (60s)",
        "last_failure_kind": "timeout",
        "disabled_for_sec": 123,
    })
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True)
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }
    factory._providers[LLMTier.TIER2] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    status = factory.get_llm_status()

    codex_status = next(item for item in status["available_providers"] if item["id"] == "CODEX")
    assert codex_status["runtime"]["cooldown_active"] is True
    assert codex_status["runtime"]["last_failure_kind"] == "timeout"
    assert codex_status["runtime"]["last_failure_reason"] == "Codex CLI timeout (60s)"


@pytest.mark.asyncio
async def test_llm_factory_manual_generate_uses_configured_primary_and_fallback(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_MODEL", "gpt-5.4")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_MODEL", "DEFAULT")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=False, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate_manual("hello", default_tier=LLMTier.TIER1)

    assert result == "claude-result"
    assert provider == "CLAUDE_CODE"


@pytest.mark.asyncio
async def test_llm_factory_manual_generate_forces_claude(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate_manual("hello", default_tier=LLMTier.TIER1)

    assert result == "claude-result"
    assert provider == "CLAUDE_CODE"
    assert codex.calls == []
    assert claude.calls == [("hello", "")]


@pytest.mark.asyncio
async def test_llm_factory_manual_generate_forces_codex(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate_manual("hello", default_tier=LLMTier.TIER1)

    assert result == "codex-result"
    assert provider == "CODEX"
    assert codex.calls == [("hello", "")]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_llm_factory_manual_generate_forces_ollama(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "OLLAMA")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    ollama = FakeProvider(LLMProvider.OLLAMA, available=True, result="ollama-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
        LLMProvider.OLLAMA: ollama,
    }

    result, provider = await factory.generate_manual("hello", default_tier=LLMTier.TIER1)

    assert result == "ollama-result"
    assert provider == "OLLAMA"
    assert ollama.calls == [("hello", "")]
    assert codex.calls == []
    assert claude.calls == []


@pytest.mark.asyncio
async def test_llm_factory_skips_retry_when_provider_becomes_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER1", "DEFAULT")

    factory = LLMFactory()
    codex = FakeFailingProvider(LLMProvider.CODEX)
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    result, provider = await factory.generate("hello", LLMTier.TIER1)

    assert result == "claude-result"
    assert provider == "CLAUDE_CODE"
    assert codex.calls == [("hello", "")]
    assert claude.calls == [("hello", "")]


@pytest.mark.asyncio
async def test_llm_factory_builds_fallback_provider_with_override_model(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER1", "claude-opus-4-6")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=False, result="codex-result")
    claude_default = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-default")
    claude_override = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-override")
    claude_override.model_id = "claude-code:claude-opus-4-6"
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude_default,
    }

    captured: list[tuple[LLMTier, LLMProvider, str | None]] = []

    def fake_build_provider(tier, provider_key, model_override=None):
        captured.append((tier, provider_key, model_override))
        if provider_key == LLMProvider.CLAUDE_CODE and model_override == "claude-opus-4-6":
            return claude_override
        return factory._providers[tier][provider_key]

    monkeypatch.setattr(factory, "_build_provider", fake_build_provider)

    result, provider = await factory.generate("hello", LLMTier.TIER1)

    assert result == "claude-override"
    assert provider == "CLAUDE_CODE"
    assert captured == [
        (LLMTier.TIER1, LLMProvider.CODEX, None),
        (LLMTier.TIER1, LLMProvider.CLAUDE_CODE, "claude-opus-4-6"),
    ]


@pytest.mark.asyncio
async def test_llm_factory_records_observability_metric_on_success(monkeypatch) -> None:
    factory = LLMFactory()
    observed = {}
    ollama = FakeProvider(LLMProvider.OLLAMA, available=True, result="ollama-result")
    factory._providers[LLMTier.TIER1] = {LLMProvider.OLLAMA: ollama}

    async def fake_record_llm_call(**kwargs):
        observed.update(kwargs)
        return None

    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    result, provider = await factory.generate(
        "hello",
        LLMTier.TIER1,
        provider_chain=[LLMProvider.OLLAMA],
    )

    assert result == "ollama-result"
    assert provider == "OLLAMA"
    assert observed["status"] == "SUCCESS"
    assert observed["provider"] == "OLLAMA"
    assert observed["prompt_chars"] == 5


@pytest.mark.asyncio
async def test_llm_factory_records_observability_metric_on_failure(monkeypatch) -> None:
    factory = LLMFactory()
    observed = {}
    failing = FakeFailingProvider(LLMProvider.OLLAMA)
    factory._providers[LLMTier.TIER1] = {LLMProvider.OLLAMA: failing}

    async def fake_record_llm_call(**kwargs):
        observed.update(kwargs)
        return None

    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    with pytest.raises(RuntimeError):
        await factory.generate(
            "hello",
            LLMTier.TIER1,
            provider_chain=[LLMProvider.OLLAMA],
        )

    assert observed["status"] == "ERROR"
    assert observed["fallback_used"] is False
