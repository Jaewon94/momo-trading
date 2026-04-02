import os
import time

import pytest

from analysis.llm.codex_provider import CodexProvider
from trading.enums import LLMTier


def test_codex_provider_builds_ephemeral_exec_command(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.codex_provider.settings.CODEX_MODEL", "gpt-5-codex")
    monkeypatch.setattr("analysis.llm.codex_provider.settings.CODEX_MODEL_TIER1", "gpt-5-codex")
    provider = CodexProvider(LLMTier.TIER1)
    monkeypatch.setattr(provider, "_find_codex", lambda: "/opt/homebrew/bin/codex")

    command = provider._build_command("/tmp/result.txt")

    assert command == [
        "/opt/homebrew/bin/codex",
        "exec",
        "-c",
        f'model_reasoning_effort="medium"',
        "-c",
        "mcp_servers={}",
        "-c",
        "features.multi_agent=false",
        "--ephemeral",
        "--model",
        provider._model,
        "--sandbox",
        "read-only",
        "--output-last-message",
        "/tmp/result.txt",
        "-",
    ]


def test_codex_provider_omits_model_flag_when_using_cli_default(monkeypatch) -> None:
    monkeypatch.setattr("analysis.llm.codex_provider.settings.CODEX_MODEL", "DEFAULT")
    monkeypatch.setattr("analysis.llm.codex_provider.settings.CODEX_MODEL_TIER1", "DEFAULT")
    provider = CodexProvider(LLMTier.TIER1)
    monkeypatch.setattr(provider, "_find_codex", lambda: "/opt/homebrew/bin/codex")

    command = provider._build_command("/tmp/result.txt")

    assert "--model" not in command


def test_codex_provider_clean_env_removes_nested_cli_state(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "shell")
    monkeypatch.setenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "codex_vscode")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    env = CodexProvider._clean_env()

    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert "CODEX_INTERNAL_ORIGINATOR_OVERRIDE" not in env
    assert "CODEX_THREAD_ID" not in env
    assert "CODEX_SANDBOX" not in env
    assert "CODEX_SANDBOX_NETWORK_DISABLED" not in env
    assert env["OTEL_SDK_DISABLED"] == "true"
    assert env["PATH"] == os.environ["PATH"]


@pytest.mark.asyncio
async def test_codex_provider_is_temporarily_unavailable_during_failure_cooldown(monkeypatch) -> None:
    provider = CodexProvider(LLMTier.TIER1)
    monkeypatch.setattr(provider, "_find_codex", lambda: "/opt/homebrew/bin/codex")
    provider._disabled_until = time.monotonic() + 60

    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_codex_provider_timeout_enters_failure_cooldown(monkeypatch) -> None:
    provider = CodexProvider(LLMTier.TIER1)
    monkeypatch.setattr(provider, "_find_codex", lambda: "/opt/homebrew/bin/codex")

    class FakeProc:
        def __init__(self) -> None:
            self.returncode = None
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        async def communicate(self, input=None):
            return b"", b""

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> None:
            self.wait_calls += 1
            self.returncode = -15

    proc = FakeProc()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr("analysis.llm.codex_provider.asyncio.create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("analysis.llm.codex_provider.asyncio.wait_for", fake_wait_for)

    with pytest.raises(RuntimeError, match="timeout"):
        await provider.generate("hello")

    assert proc.terminated is True
    assert proc.wait_calls == 1
    assert provider._disabled_until > time.monotonic()
