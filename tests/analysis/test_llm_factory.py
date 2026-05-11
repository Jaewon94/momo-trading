import asyncio

import pytest

from analysis.llm.llm_factory import LLMFactory
from analysis.llm.selection_policy import NewsSelection, resolve_news_selection
from core.config import DEFAULT_LLM_MODEL
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


class FakeAlwaysFailingProvider(FakeProvider):
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        raise RuntimeError("provider failed")


class FakeMutatingFailingProvider(FakeProvider):
    def __init__(self, provider: LLMProvider, on_generate) -> None:
        super().__init__(provider, available=True, result="")
        self._on_generate = on_generate

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        self._available = False
        self._on_generate()
        raise RuntimeError("provider failed")


class BlockingProvider(FakeProvider):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, available=True, result="ok")
        self.started = 0
        self.active = 0
        self.max_active = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        self.started += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.entered.set()
        await self.release.wait()
        self.active -= 1
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


@pytest.mark.asyncio
async def test_llm_factory_distributed_tier1_rotates_available_provider_chain(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_EXECUTION_MODE_TIER1", "DISTRIBUTED")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_DISTRIBUTED_PROFILE_TIER1", "FULL")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.ANTHROPIC_API_KEY", "test-key")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude_api = FakeProvider(LLMProvider.CLAUDE_API, available=True, result="claude-api-result")
    claude_code = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-code-result")
    ollama = FakeProvider(LLMProvider.OLLAMA, available=True, result="ollama-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_API: claude_api,
        LLMProvider.CLAUDE_CODE: claude_code,
        LLMProvider.OLLAMA: ollama,
    }

    first = await factory.generate_tier1("first")
    second = await factory.generate_tier1("second")
    third = await factory.generate_tier1("third")
    fourth = await factory.generate_tier1("fourth")

    assert first == ("codex-result", "CODEX")
    assert second == ("claude-code-result", "CLAUDE_CODE")
    assert third == ("claude-api-result", "CLAUDE_API")
    assert fourth == ("codex-result", "CODEX")
    assert codex.calls == [("first", ""), ("fourth", "")]
    assert claude_code.calls == [("second", "")]
    assert claude_api.calls == [("third", "")]
    assert ollama.calls == []


@pytest.mark.asyncio
async def test_llm_factory_distributed_fast_profile_excludes_claude_code(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_EXECUTION_MODE_TIER1", "DISTRIBUTED")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_DISTRIBUTED_PROFILE_TIER1", "FAST")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.ANTHROPIC_API_KEY", "test-key")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude_api = FakeProvider(LLMProvider.CLAUDE_API, available=True, result="claude-api-result")
    claude_code = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-code-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_API: claude_api,
        LLMProvider.CLAUDE_CODE: claude_code,
    }

    first = await factory.generate_tier1("first")
    second = await factory.generate_tier1("second")

    assert first == ("codex-result", "CODEX")
    assert second == ("claude-api-result", "CLAUDE_API")
    assert codex.calls == [("first", "")]
    assert claude_api.calls == [("second", "")]
    assert claude_code.calls == []


@pytest.mark.asyncio
async def test_llm_factory_single_mode_keeps_primary_fallback_chain(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_EXECUTION_MODE_TIER1", "SINGLE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    ollama = FakeProvider(LLMProvider.OLLAMA, available=True, result="ollama-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
        LLMProvider.OLLAMA: ollama,
    }

    await factory.generate_tier1("first")
    await factory.generate_tier1("second")

    assert codex.calls == [("first", ""), ("second", "")]
    assert claude.calls == []
    assert ollama.calls == []


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
    assert {item["id"] for item in status["available_providers"]} == {"CLAUDE_CODE", "CLAUDE_API", "CODEX", "OLLAMA"}


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


def test_llm_factory_reset_runtime_state_rebuilds_provider_instances(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER1", "gpt-5-codex")

    factory = LLMFactory()
    stale_codex = factory._providers[LLMTier.TIER1][LLMProvider.CODEX]

    monkeypatch.setattr("analysis.llm.llm_factory.settings.CODEX_MODEL_TIER1", "gpt-5.4")
    factory.reset_runtime_state()
    refreshed_codex = factory._providers[LLMTier.TIER1][LLMProvider.CODEX]

    assert refreshed_codex is not stale_codex
    assert refreshed_codex.model_id == "codex:gpt-5.4"


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
async def test_llm_factory_captures_error_when_all_providers_fail(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr("analysis.llm.llm_factory.asyncio.sleep", fake_sleep)

    captured = {}

    async def fake_capture_exception(**kwargs):
        captured.update(kwargs)
        return {"fingerprint": "fp-1"}

    async def fake_record_llm_call(**kwargs):
        return None

    factory = LLMFactory()
    codex = FakeAlwaysFailingProvider(LLMProvider.CODEX, available=True, result="")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
    }

    monkeypatch.setattr("analysis.llm.llm_factory.error_capture_service.capture_exception", fake_capture_exception)
    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    with pytest.raises(RuntimeError, match="provider failed"):
        await factory.generate("hello", LLMTier.TIER1, symbol="005930", cycle_id="cycle-1")

    assert captured["component"] == "llm_factory"
    assert captured["operation"] == "generate"
    assert captured["symbol"] == "005930"
    assert captured["cycle_id"] == "cycle-1"
    assert captured["detail"]["tier"] == "TIER1"


@pytest.mark.asyncio
async def test_llm_factory_suppresses_repeated_cooldown_incident_capture(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")

    captured = []

    async def fake_capture_exception(**kwargs):
        captured.append(kwargs)
        return {"fingerprint": "fp-1"}

    async def fake_record_llm_call(**kwargs):
        return None

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=False)
    codex.status.update({
        "available": False,
        "cooldown_active": True,
        "last_failure_reason": "Codex CLI timeout (90s)",
        "last_failure_kind": "timeout",
        "disabled_for_sec": 300,
    })
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
    }

    monkeypatch.setattr("analysis.llm.llm_factory.error_capture_service.capture_exception", fake_capture_exception)
    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="최근 호출 실패로 비활성화"):
            await factory.generate("hello", LLMTier.TIER1, symbol="005930")

    assert len(captured) == 1
    assert captured[0]["detail"]["cooldown_suppression_key"].startswith("TIER1:CODEX:")


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
    assert observed["detail"]["call_context"] == "tier1_analysis"


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


@pytest.mark.asyncio
async def test_llm_factory_limits_concurrent_generation_per_tier(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_TIER1_CONCURRENCY", 1)

    async def fake_record_llm_call(**kwargs):
        return None

    factory = LLMFactory()
    provider = BlockingProvider(LLMProvider.OLLAMA)
    factory._providers[LLMTier.TIER1] = {LLMProvider.OLLAMA: provider}
    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    first = asyncio.create_task(
        factory.generate("first", LLMTier.TIER1, provider_chain=[LLMProvider.OLLAMA]),
    )
    await provider.entered.wait()

    second = asyncio.create_task(
        factory.generate("second", LLMTier.TIER1, provider_chain=[LLMProvider.OLLAMA]),
    )
    await asyncio.sleep(0.05)

    assert provider.started == 1
    assert provider.max_active == 1

    provider.release.set()
    await first
    await second

    assert provider.started == 2
    assert provider.max_active == 1


@pytest.mark.asyncio
async def test_llm_factory_serializes_codex_generation_globally(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_TIER1_CONCURRENCY", 3)

    async def fake_record_llm_call(**kwargs):
        return None

    factory = LLMFactory()
    provider = BlockingProvider(LLMProvider.CODEX)
    factory._providers[LLMTier.TIER1] = {LLMProvider.CODEX: provider}
    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)

    first = asyncio.create_task(
        factory.generate("first", LLMTier.TIER1, provider_chain=[LLMProvider.CODEX]),
    )
    await provider.entered.wait()

    second = asyncio.create_task(
        factory.generate("second", LLMTier.TIER1, provider_chain=[LLMProvider.CODEX]),
    )
    await asyncio.sleep(0.05)

    assert provider.started == 1
    assert provider.max_active == 1

    provider.release.set()
    await first
    await second

    assert provider.started == 2
    assert provider.max_active == 1


@pytest.mark.asyncio
async def test_llm_factory_logs_progress_when_llm_call_is_slow(monkeypatch) -> None:
    async def fake_record_llm_call(**kwargs):
        return None

    warnings = []

    async def fake_activity_log(*args, **kwargs):
        warnings.append((args, kwargs))
        return None

    factory = LLMFactory()
    provider = BlockingProvider(LLMProvider.CODEX)
    factory._providers[LLMTier.TIER1] = {LLMProvider.CODEX: provider}
    monkeypatch.setattr(factory, "_slow_call_warn_sec", lambda: 0.01)
    monkeypatch.setattr("analysis.llm.llm_factory.observability_service.record_llm_call", fake_record_llm_call)
    monkeypatch.setattr("analysis.llm.llm_factory.activity_logger.log", fake_activity_log)

    task = asyncio.create_task(
        factory.generate("slow", LLMTier.TIER1, provider_chain=[LLMProvider.CODEX], symbol="005930", cycle_id="cycle-1"),
    )
    await provider.entered.wait()
    await asyncio.sleep(0.05)

    assert len(warnings) >= 2
    start_event = warnings[0]
    slow_event = warnings[1]
    assert start_event[0][0].value == "LLM_CALL"
    assert start_event[0][1].value == "START"
    assert "호출 시작" in start_event[0][2]
    assert start_event[1]["llm_provider"] == "CODEX"
    assert start_event[1]["symbol"] == "005930"
    assert start_event[1]["cycle_id"] == "cycle-1"
    assert slow_event[0][0].value == "LLM_CALL"
    assert slow_event[0][1].value == "PROGRESS"
    assert "호출 지연" in slow_event[0][2]
    assert slow_event[1]["symbol"] == "005930"
    assert slow_event[1]["cycle_id"] == "cycle-1"

    provider.release.set()
    await task


async def test_llm_factory_re_resolves_default_chain_after_primary_failure(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_PROVIDER_TIER1", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_MODEL_TIER1", "DEFAULT")

    def disable_fallback() -> None:
        monkeypatch.setattr("analysis.llm.llm_factory.settings.LLM_FALLBACK_PROVIDER_TIER1", "")

    factory = LLMFactory()
    codex = FakeMutatingFailingProvider(LLMProvider.CODEX, on_generate=disable_fallback)
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    with pytest.raises(RuntimeError, match="provider failed"):
        await factory.generate("hello", LLMTier.TIER1)

    assert codex.calls == [("hello", "")]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_llm_factory_re_resolves_manual_chain_after_primary_failure(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_MODEL", "DEFAULT")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_MODEL", "DEFAULT")

    def disable_manual_fallback() -> None:
        monkeypatch.setattr("analysis.llm.llm_factory.settings.MANUAL_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeMutatingFailingProvider(LLMProvider.CODEX, on_generate=disable_manual_fallback)
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    with pytest.raises(RuntimeError, match="provider failed"):
        await factory.generate_manual("hello", default_tier=LLMTier.TIER1)

    assert codex.calls == [("hello", "")]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_llm_factory_re_resolves_news_chain_after_primary_failure(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_EXECUTION_MODE", "SINGLE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_MODEL", "DEFAULT")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_FALLBACK_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_FALLBACK_MODEL", "DEFAULT")

    def disable_news_fallback() -> None:
        monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeMutatingFailingProvider(LLMProvider.CODEX, on_generate=disable_news_fallback)
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    with pytest.raises(RuntimeError, match="provider failed"):
        await factory.generate_news("hello")

    assert codex.calls == [("hello", "")]
    assert claude.calls == []


def test_resolve_news_selection_preserves_default_fallback_model_override(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_PROVIDER", "CODEX")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_MODEL", "DEFAULT")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_FALLBACK_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.selection_policy.settings.NEWS_LLM_FALLBACK_MODEL", "DEFAULT")

    selection = resolve_news_selection()

    assert selection.provider_model_overrides is not None
    assert selection.provider_model_overrides[LLMProvider.CLAUDE_CODE] == DEFAULT_LLM_MODEL


@pytest.mark.asyncio
async def test_llm_factory_generate_news_uses_provided_selection_over_runtime_settings(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_PROVIDER", "CLAUDE_CODE")
    monkeypatch.setattr("analysis.llm.llm_factory.settings.NEWS_LLM_FALLBACK_PROVIDER", "")

    factory = LLMFactory()
    codex = FakeProvider(LLMProvider.CODEX, available=True, result="codex-result")
    claude = FakeProvider(LLMProvider.CLAUDE_CODE, available=True, result="claude-result")
    factory._providers[LLMTier.TIER1] = {
        LLMProvider.CODEX: codex,
        LLMProvider.CLAUDE_CODE: claude,
    }

    selection = NewsSelection(
        enabled=True,
        provider="CODEX",
        model=DEFAULT_LLM_MODEL,
        fallback_provider="",
        fallback_model=DEFAULT_LLM_MODEL,
        provider_chain=(LLMProvider.CODEX,),
        provider_model_overrides=None,
    )

    result, provider = await factory.generate_news("hello", news_selection=selection)

    assert result == "codex-result"
    assert provider == "CODEX"
    assert codex.calls == [("hello", "")]
    assert claude.calls == []
