import asyncio

from analysis.llm.claude_code_provider import ClaudeCodeProvider
from trading.enums import LLMTier


def test_claude_provider_model_args_include_explicit_model(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_MODEL", "sonnet")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_MODEL_TIER1", "haiku")

    provider = ClaudeCodeProvider(LLMTier.TIER1)

    assert provider._model_args() == ["--model", "haiku"]


def test_claude_provider_model_args_omit_model_when_using_cli_default(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_MODEL", "DEFAULT")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_MODEL_TIER1", "DEFAULT")

    provider = ClaudeCodeProvider(LLMTier.TIER1)

    assert provider._model_args() == []


def test_claude_provider_reads_effort_and_bare_by_tier(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_EFFORT_TIER1", "low")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_EFFORT_TIER2", "high")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_BARE_TIER1", True)
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_BARE_TIER2", False)

    tier1 = ClaudeCodeProvider(LLMTier.TIER1)
    tier2 = ClaudeCodeProvider(LLMTier.TIER2)

    assert tier1._effort() == "low"
    assert tier1._bare_enabled() is True
    assert tier2._effort() == "high"
    assert tier2._bare_enabled() is False


def test_claude_provider_recreates_session_lock_for_new_event_loop() -> None:
    ClaudeCodeProvider._session_lock = None
    if hasattr(ClaudeCodeProvider, "_session_lock_loop"):
        ClaudeCodeProvider._session_lock_loop = None

    async def get_lock():
        return ClaudeCodeProvider._get_lock()

    first = asyncio.run(get_lock())
    second = asyncio.run(get_lock())

    assert second is not first


def test_claude_provider_builds_session_args_inside_lock(monkeypatch) -> None:
    ClaudeCodeProvider.end_session()
    ClaudeCodeProvider._session_lock = None
    if hasattr(ClaudeCodeProvider, "_session_lock_loop"):
        ClaudeCodeProvider._session_lock_loop = None
    session_id = ClaudeCodeProvider.start_session()
    calls: list[list[str]] = []

    async def fake_execute(self, cmd, prompt):
        calls.append(cmd)
        await asyncio.sleep(0)
        return "ok"

    monkeypatch.setattr(ClaudeCodeProvider, "_find_claude", lambda self: "/bin/claude")
    monkeypatch.setattr(ClaudeCodeProvider, "_execute", fake_execute)
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_EFFORT_TIER1", "low")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_BARE_TIER1", False)

    async def run_concurrent_generates() -> None:
        provider = ClaudeCodeProvider(LLMTier.TIER1)
        await asyncio.gather(
            provider.generate("first", "system"),
            provider.generate("second", "system"),
        )

    try:
        asyncio.run(run_concurrent_generates())
    finally:
        ClaudeCodeProvider.end_session()

    assert calls[0][-4:] == ["--session-id", session_id, "--system-prompt", "system"]
    assert ["--resume", session_id] == calls[1][-2:]


def test_claude_provider_uses_one_shot_when_bare_is_enabled(monkeypatch) -> None:
    ClaudeCodeProvider.end_session()
    session_id = ClaudeCodeProvider.start_session()
    calls: list[list[str]] = []

    async def fake_execute(self, cmd, prompt):
        calls.append(cmd)
        return "ok"

    monkeypatch.setattr(ClaudeCodeProvider, "_find_claude", lambda self: "/bin/claude")
    monkeypatch.setattr(ClaudeCodeProvider, "_execute", fake_execute)
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_EFFORT_TIER1", "low")
    monkeypatch.setattr("analysis.llm.claude_code_provider.settings.CLAUDE_CODE_BARE_TIER1", True)

    try:
        asyncio.run(ClaudeCodeProvider(LLMTier.TIER1).generate("prompt", "system"))
    finally:
        ClaudeCodeProvider.end_session()

    assert session_id
    assert "--bare" in calls[0]
    assert "--no-session-persistence" in calls[0]
    assert "--session-id" not in calls[0]
    assert "--resume" not in calls[0]
