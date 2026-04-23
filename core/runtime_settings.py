from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.config import normalize_llm_model_value, settings
from core.order_submission import VALID_ORDER_SUBMISSION_MODES, normalize_order_submission_mode

MUTABLE_SETTINGS = [
    "TRADING_ENABLED", "ORDER_SUBMISSION_MODE", "AUTONOMY_MODE",
    "RECOMMENDATION_EXPIRE_MIN",
    "SCHEDULER_ENABLED",
    "RISK_APPETITE",
    "BUY_ORDER_EXECUTION_MODE",
    "BUY_SLIPPAGE_GUARD_BPS",
    "AUTO_RISK_KILL_SWITCH_ENABLED",
    "MAX_DAILY_DRAWDOWN_PCT",
    "MAX_CONSECUTIVE_LOSSES",
    "MIN_STRATEGY_EXPECTANCY",
    "EXPECTANCY_SAMPLE_SIZE",
    "VOLATILITY_POSITION_SIZING_ENABLED",
    "RISK_PER_TRADE_PCT",
    "RISK_MULTIPLIER_SHORT",
    "RISK_MULTIPLIER_MID",
    "RISK_MULTIPLIER_LONG",
    "COST_GATE_ENABLED",
    "ESTIMATED_ENTRY_COST_BPS",
    "ESTIMATED_EXIT_COST_BPS",
    "ESTIMATED_SLIPPAGE_BPS_SHORT",
    "ESTIMATED_SLIPPAGE_BPS_MID",
    "ESTIMATED_SLIPPAGE_BPS_LONG",
    "MIN_EDGE_TO_COST_RATIO_SHORT",
    "MIN_EDGE_TO_COST_RATIO_MID",
    "MIN_EDGE_TO_COST_RATIO_LONG",
    "LLM_PROVIDER_TIER1",
    "LLM_PROVIDER_TIER2",
    "LLM_FALLBACK_PROVIDER_TIER1",
    "LLM_FALLBACK_PROVIDER_TIER2",
    "LLM_FALLBACK_MODEL_TIER1",
    "LLM_FALLBACK_MODEL_TIER2",
    "CLAUDE_CODE_MODEL",
    "CLAUDE_CODE_MODEL_TIER1",
    "CLAUDE_CODE_MODEL_TIER2",
    "CODEX_MODEL",
    "CODEX_MODEL_TIER1",
    "CODEX_MODEL_TIER2",
    "CODEX_TIMEOUT_SEC_TIER1",
    "CODEX_TIMEOUT_SEC_TIER2",
    "LLM_SLOW_CALL_WARN_SEC",
    "LLM_TIER1_CONCURRENCY",
    "LLM_TIER2_CONCURRENCY",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_MODEL_TIER1",
    "OLLAMA_MODEL_TIER2",
    "MANUAL_LLM_PROVIDER",
    "MANUAL_LLM_MODEL",
    "MANUAL_LLM_FALLBACK_PROVIDER",
    "MANUAL_LLM_FALLBACK_MODEL",
    "NEWS_LLM_ENABLED",
    "NEWS_LLM_PROVIDER",
    "NEWS_LLM_MODEL",
    "NEWS_LLM_FALLBACK_PROVIDER",
    "NEWS_LLM_FALLBACK_MODEL",
    "NEWS_DOMESTIC_MEDIA_ENABLED",
    "NEWS_INCLUDE_FOREIGN",
    "NEWS_TRANSLATE_FOREIGN_ENABLED",
    "NEWS_NASDAQ_ENABLED",
    "NEWS_GATE_ENABLED",
    "NEWS_LOOKBACK_HOURS",
    "NEWS_MAX_ITEMS_PER_SYMBOL",
    "NEWS_NEGATIVE_BLOCK_THRESHOLD",
    "NEWS_FRESHNESS_HALFLIFE_HOURS",
    "NEWS_POLL_ENABLED",
    "NEWS_POLL_INTERVAL_MIN_TRADING",
    "NEWS_POLL_INTERVAL_MIN_OFF_HOURS",
    "NEWS_POLL_PAGE_COUNT",
    "NEWS_FETCH_CONCURRENCY",
    "NEWS_SOURCE_FAILURE_THRESHOLD",
    "NEWS_SOURCE_FAILURE_COOLDOWN_MIN",
    "NEWS_TRANSLATION_CONCURRENCY",
    "NEWS_CLAUDE_SHARE_SESSION",
    "NEWS_RECHECK_COOLDOWN_SEC",
    "BROKER_BALANCE_RETRY_COUNT",
    "BROKER_BALANCE_RETRY_DELAY_MS",
    "NEWS_SHADOW_ENABLED",
    "NEWS_ROLLOUT_MIN_SAMPLE_SIZE",
    "NEWS_ROLLOUT_MIN_PROFIT_FACTOR",
    "NEWS_ROLLOUT_MIN_EXPECTANCY",
    "NEWS_ROLLOUT_MAX_DRAWDOWN_KRW",
]

_SKIP = object()


def coerce_runtime_setting_value(key: str, value: Any) -> Any:
    current = getattr(settings, key, None)

    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "on")

    if isinstance(current, int) and not isinstance(current, bool):
        try:
            normalized_int = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be an integer") from exc
        if key in {
            "LLM_TIER1_CONCURRENCY",
            "LLM_TIER2_CONCURRENCY",
            "NEWS_FETCH_CONCURRENCY",
            "NEWS_TRANSLATION_CONCURRENCY",
            "NEWS_SOURCE_FAILURE_THRESHOLD",
            "BROKER_BALANCE_RETRY_COUNT",
        }:
            if normalized_int < 1 or normalized_int > 8:
                raise HTTPException(status_code=400, detail=f"{key} must be between 1 and 8")
        if key in {
            "CODEX_TIMEOUT_SEC_TIER1",
            "CODEX_TIMEOUT_SEC_TIER2",
        }:
            if normalized_int < 30 or normalized_int > 300:
                raise HTTPException(status_code=400, detail=f"{key} must be between 30 and 300")
        if key == "LLM_SLOW_CALL_WARN_SEC":
            if normalized_int < 0 or normalized_int > 300:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 300")
        if key == "NEWS_SOURCE_FAILURE_COOLDOWN_MIN":
            if normalized_int < 1 or normalized_int > 240:
                raise HTTPException(status_code=400, detail=f"{key} must be between 1 and 240")
        if key == "BROKER_BALANCE_RETRY_DELAY_MS":
            if normalized_int < 100 or normalized_int > 5000:
                raise HTTPException(status_code=400, detail=f"{key} must be between 100 and 5000")
        return normalized_int

    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc

    if key in {
        "LLM_PROVIDER_TIER1",
        "LLM_PROVIDER_TIER2",
        "LLM_FALLBACK_PROVIDER_TIER1",
        "LLM_FALLBACK_PROVIDER_TIER2",
    }:
        normalized = str(value).upper()
        if key.startswith("LLM_FALLBACK_PROVIDER_") and normalized in {"", "NONE"}:
            return ""
        if normalized not in {"CLAUDE_CODE", "CODEX", "OLLAMA"}:
            return _SKIP
        return normalized

    if key in {"MANUAL_LLM_PROVIDER", "NEWS_LLM_PROVIDER"}:
        normalized = str(value).upper()
        if normalized not in {"CLAUDE_CODE", "CODEX", "OLLAMA"}:
            return _SKIP
        return normalized

    if key in {"MANUAL_LLM_FALLBACK_PROVIDER", "NEWS_LLM_FALLBACK_PROVIDER"}:
        normalized = str(value).upper()
        if normalized in {"", "NONE"}:
            return ""
        if normalized not in {"CLAUDE_CODE", "CODEX", "OLLAMA"}:
            return _SKIP
        return normalized

    if key == "BUY_ORDER_EXECUTION_MODE":
        normalized = str(value).upper()
        if normalized not in {"LIMIT_GUARD", "MARKET"}:
            return _SKIP
        return normalized

    if key == "ORDER_SUBMISSION_MODE":
        normalized = normalize_order_submission_mode(value)
        if normalized not in VALID_ORDER_SUBMISSION_MODES:
            return _SKIP
        return normalized

    if key in {
        "LLM_FALLBACK_MODEL_TIER1",
        "LLM_FALLBACK_MODEL_TIER2",
        "CLAUDE_CODE_MODEL",
        "CLAUDE_CODE_MODEL_TIER1",
        "CLAUDE_CODE_MODEL_TIER2",
        "CODEX_MODEL",
        "CODEX_MODEL_TIER1",
        "CODEX_MODEL_TIER2",
        "OLLAMA_MODEL",
        "OLLAMA_MODEL_TIER1",
        "OLLAMA_MODEL_TIER2",
        "MANUAL_LLM_MODEL",
        "MANUAL_LLM_FALLBACK_MODEL",
        "NEWS_LLM_MODEL",
        "NEWS_LLM_FALLBACK_MODEL",
    }:
        return normalize_llm_model_value(str(value))

    if isinstance(current, str):
        return str(value)

    return value


def is_skipped_runtime_setting_value(value: Any) -> bool:
    return value is _SKIP
