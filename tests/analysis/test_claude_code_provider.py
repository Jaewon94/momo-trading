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
