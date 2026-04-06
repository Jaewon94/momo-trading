from core.config import settings
from services.runtime_settings_service import runtime_settings_service


async def test_runtime_settings_service_persists_and_reloads_values(
    override_runtime_settings_session,
    reset_runtime_settings,
):
    original_manual = settings.MANUAL_LLM_PROVIDER
    original_manual_model = settings.MANUAL_LLM_MODEL
    original_news_poll = settings.NEWS_POLL_ENABLED
    original_interval = settings.NEWS_POLL_INTERVAL_MIN_TRADING

    try:
        changed = await runtime_settings_service.update_settings({
            "MANUAL_LLM_PROVIDER": "CODEX",
            "MANUAL_LLM_MODEL": "gpt-5.4",
            "NEWS_POLL_ENABLED": False,
            "NEWS_POLL_INTERVAL_MIN_TRADING": 7,
        })

        assert changed["MANUAL_LLM_PROVIDER"]["new"] == "CODEX"
        assert changed["MANUAL_LLM_MODEL"]["new"] == "gpt-5.4"
        assert changed["NEWS_POLL_ENABLED"]["new"] is False
        assert changed["NEWS_POLL_INTERVAL_MIN_TRADING"]["new"] == 7

        settings.MANUAL_LLM_PROVIDER = original_manual
        settings.MANUAL_LLM_MODEL = original_manual_model
        settings.NEWS_POLL_ENABLED = original_news_poll
        settings.NEWS_POLL_INTERVAL_MIN_TRADING = original_interval

        applied = await runtime_settings_service.apply_persisted_settings()

        assert applied["MANUAL_LLM_PROVIDER"] == "CODEX"
        assert applied["MANUAL_LLM_MODEL"] == "gpt-5.4"
        assert applied["NEWS_POLL_ENABLED"] is False
        assert applied["NEWS_POLL_INTERVAL_MIN_TRADING"] == 7
        assert settings.MANUAL_LLM_PROVIDER == "CODEX"
        assert settings.MANUAL_LLM_MODEL == "gpt-5.4"
        assert settings.NEWS_POLL_ENABLED is False
        assert settings.NEWS_POLL_INTERVAL_MIN_TRADING == 7
    finally:
        settings.MANUAL_LLM_PROVIDER = original_manual
        settings.MANUAL_LLM_MODEL = original_manual_model
        settings.NEWS_POLL_ENABLED = original_news_poll
        settings.NEWS_POLL_INTERVAL_MIN_TRADING = original_interval


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
