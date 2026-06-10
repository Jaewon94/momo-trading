import pytest

from core.config import settings
from services.runtime_settings_service import runtime_settings_service
from fastapi import HTTPException


async def test_runtime_settings_service_persists_and_reloads_values(
    override_runtime_settings_session,
    reset_runtime_settings,
):
    original_manual = settings.MANUAL_LLM_PROVIDER
    original_manual_model = settings.MANUAL_LLM_MODEL
    original_manual_fallback_provider = settings.MANUAL_LLM_FALLBACK_PROVIDER
    original_manual_fallback_model = settings.MANUAL_LLM_FALLBACK_MODEL
    original_news_poll = settings.NEWS_POLL_ENABLED
    original_interval = settings.NEWS_POLL_INTERVAL_MIN_TRADING
    original_fetch_concurrency = settings.NEWS_FETCH_CONCURRENCY
    original_translation_concurrency = settings.NEWS_TRANSLATION_CONCURRENCY
    original_tier1_execution_mode = settings.LLM_EXECUTION_MODE_TIER1
    original_tier2_execution_mode = settings.LLM_EXECUTION_MODE_TIER2
    original_manual_execution_mode = settings.MANUAL_LLM_EXECUTION_MODE
    original_news_execution_mode = settings.NEWS_LLM_EXECUTION_MODE

    try:
        changed = await runtime_settings_service.update_settings({
            "MANUAL_LLM_PROVIDER": "CODEX",
            "MANUAL_LLM_MODEL": "gpt-5.4",
            "MANUAL_LLM_FALLBACK_PROVIDER": "CLAUDE_CODE",
            "MANUAL_LLM_FALLBACK_MODEL": "claude-sonnet-4-6",
            "NEWS_POLL_ENABLED": False,
            "NEWS_POLL_INTERVAL_MIN_TRADING": 7,
            "NEWS_FETCH_CONCURRENCY": 6,
            "NEWS_TRANSLATION_CONCURRENCY": 2,
            "LLM_EXECUTION_MODE_TIER1": "DISTRIBUTED",
            "LLM_EXECUTION_MODE_TIER2": "CONSENSUS",
            "MANUAL_LLM_EXECUTION_MODE": "SINGLE",
            "NEWS_LLM_EXECUTION_MODE": "DISTRIBUTED",
        })

        assert changed["MANUAL_LLM_PROVIDER"]["new"] == "CODEX"
        assert changed["MANUAL_LLM_MODEL"]["new"] == "gpt-5.4"
        assert changed["MANUAL_LLM_FALLBACK_PROVIDER"]["new"] == "CLAUDE_CODE"
        assert changed["MANUAL_LLM_FALLBACK_MODEL"]["new"] == "claude-sonnet-4-6"
        assert changed["NEWS_POLL_ENABLED"]["new"] is False
        assert changed["NEWS_POLL_INTERVAL_MIN_TRADING"]["new"] == 7
        assert changed["NEWS_FETCH_CONCURRENCY"]["new"] == 6
        assert changed["NEWS_TRANSLATION_CONCURRENCY"]["new"] == 2
        assert changed["LLM_EXECUTION_MODE_TIER1"]["new"] == "DISTRIBUTED"
        assert changed["LLM_EXECUTION_MODE_TIER2"]["new"] == "CONSENSUS"
        assert changed["MANUAL_LLM_EXECUTION_MODE"]["new"] == "SINGLE"
        assert changed["NEWS_LLM_EXECUTION_MODE"]["new"] == "DISTRIBUTED"

        settings.MANUAL_LLM_PROVIDER = original_manual
        settings.MANUAL_LLM_MODEL = original_manual_model
        settings.MANUAL_LLM_FALLBACK_PROVIDER = original_manual_fallback_provider
        settings.MANUAL_LLM_FALLBACK_MODEL = original_manual_fallback_model
        settings.NEWS_POLL_ENABLED = original_news_poll
        settings.NEWS_POLL_INTERVAL_MIN_TRADING = original_interval
        settings.NEWS_FETCH_CONCURRENCY = original_fetch_concurrency
        settings.NEWS_TRANSLATION_CONCURRENCY = original_translation_concurrency
        settings.LLM_EXECUTION_MODE_TIER1 = original_tier1_execution_mode
        settings.LLM_EXECUTION_MODE_TIER2 = original_tier2_execution_mode
        settings.MANUAL_LLM_EXECUTION_MODE = original_manual_execution_mode
        settings.NEWS_LLM_EXECUTION_MODE = original_news_execution_mode

        applied = await runtime_settings_service.apply_persisted_settings()

        assert applied["MANUAL_LLM_PROVIDER"] == "CODEX"
        assert applied["MANUAL_LLM_MODEL"] == "gpt-5.4"
        assert applied["MANUAL_LLM_FALLBACK_PROVIDER"] == "CLAUDE_CODE"
        assert applied["MANUAL_LLM_FALLBACK_MODEL"] == "claude-sonnet-4-6"
        assert applied["NEWS_POLL_ENABLED"] is False
        assert applied["NEWS_POLL_INTERVAL_MIN_TRADING"] == 7
        assert applied["NEWS_FETCH_CONCURRENCY"] == 6
        assert applied["NEWS_TRANSLATION_CONCURRENCY"] == 2
        assert applied["LLM_EXECUTION_MODE_TIER1"] == "DISTRIBUTED"
        assert applied["LLM_EXECUTION_MODE_TIER2"] == "CONSENSUS"
        assert applied["MANUAL_LLM_EXECUTION_MODE"] == "SINGLE"
        assert applied["NEWS_LLM_EXECUTION_MODE"] == "DISTRIBUTED"
        assert settings.MANUAL_LLM_PROVIDER == "CODEX"
        assert settings.MANUAL_LLM_MODEL == "gpt-5.4"
        assert settings.MANUAL_LLM_FALLBACK_PROVIDER == "CLAUDE_CODE"
        assert settings.MANUAL_LLM_FALLBACK_MODEL == "claude-sonnet-4-6"
        assert settings.NEWS_POLL_ENABLED is False
        assert settings.NEWS_POLL_INTERVAL_MIN_TRADING == 7
        assert settings.NEWS_FETCH_CONCURRENCY == 6
        assert settings.NEWS_TRANSLATION_CONCURRENCY == 2
        assert settings.LLM_EXECUTION_MODE_TIER1 == "DISTRIBUTED"
        assert settings.LLM_EXECUTION_MODE_TIER2 == "CONSENSUS"
        assert settings.MANUAL_LLM_EXECUTION_MODE == "SINGLE"
        assert settings.NEWS_LLM_EXECUTION_MODE == "DISTRIBUTED"
    finally:
        settings.MANUAL_LLM_PROVIDER = original_manual
        settings.MANUAL_LLM_MODEL = original_manual_model
        settings.MANUAL_LLM_FALLBACK_PROVIDER = original_manual_fallback_provider
        settings.MANUAL_LLM_FALLBACK_MODEL = original_manual_fallback_model
        settings.NEWS_POLL_ENABLED = original_news_poll
        settings.NEWS_POLL_INTERVAL_MIN_TRADING = original_interval
        settings.NEWS_FETCH_CONCURRENCY = original_fetch_concurrency
        settings.NEWS_TRANSLATION_CONCURRENCY = original_translation_concurrency
        settings.LLM_EXECUTION_MODE_TIER1 = original_tier1_execution_mode
        settings.LLM_EXECUTION_MODE_TIER2 = original_tier2_execution_mode
        settings.MANUAL_LLM_EXECUTION_MODE = original_manual_execution_mode
        settings.NEWS_LLM_EXECUTION_MODE = original_news_execution_mode


async def test_runtime_settings_service_normalizes_default_model(
    override_runtime_settings_session,
    reset_runtime_settings,
):
    original_codex_model = settings.CODEX_MODEL_TIER1

    try:
        await runtime_settings_service.update_settings({"CODEX_MODEL_TIER1": ""})

        settings.CODEX_MODEL_TIER1 = "gpt-5.4"
        applied = await runtime_settings_service.apply_persisted_settings()

        assert applied["CODEX_MODEL_TIER1"] == "DEFAULT"
        assert settings.CODEX_MODEL_TIER1 == "DEFAULT"
    finally:
        settings.CODEX_MODEL_TIER1 = original_codex_model


async def test_runtime_settings_service_validates_all_updates_before_mutating_settings(
    override_runtime_settings_session,
    reset_runtime_settings,
):
    original_provider = settings.LLM_PROVIDER_TIER1
    original_timeout = settings.CODEX_TIMEOUT_SEC_TIER1

    with pytest.raises(HTTPException):
        await runtime_settings_service.update_settings({
            "LLM_PROVIDER_TIER1": "CODEX",
            "CODEX_TIMEOUT_SEC_TIER1": 20,
        })

    assert settings.LLM_PROVIDER_TIER1 == original_provider
    assert settings.CODEX_TIMEOUT_SEC_TIER1 == original_timeout


def test_runtime_settings_horizon_values_are_validated() -> None:
    from core.runtime_settings import coerce_runtime_setting_value, is_skipped_runtime_setting_value

    assert coerce_runtime_setting_value("HORIZON_MID_MAX_CANDIDATES", 60) == 60
    assert coerce_runtime_setting_value("HORIZON_SCAN_LONG_DAY_OF_WEEK", "fri") == "fri"
    assert is_skipped_runtime_setting_value(
        coerce_runtime_setting_value("HORIZON_SCAN_LONG_DAY_OF_WEEK", "sun")
    )
    with pytest.raises(HTTPException):
        coerce_runtime_setting_value("HORIZON_LONG_NEWS_LOOKBACK_HOURS", 0)
