from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.config import normalize_llm_model_value, settings
from core.order_submission import VALID_ORDER_SUBMISSION_MODES, normalize_order_submission_mode

MUTABLE_SETTINGS = [
    "TRADING_ENABLED", "ORDER_SUBMISSION_MODE", "AUTONOMY_MODE",
    "ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED",
    "ADMIN_ACTION_CONFIRMATION_TTL_SEC",
    "POST_LIQUIDATION_BUY_BLOCK_ENABLED",
    "DAY_TRADING_ONLY",
    "RECOMMENDATION_EXPIRE_MIN",
    "SCHEDULER_ENABLED",
    "INTRADAY_RESCAN_INTERVAL_MIN",
    "RISK_APPETITE",
    "BUY_ORDER_EXECUTION_MODE",
    "BUY_SLIPPAGE_GUARD_BPS",
    "BUY_ORDER_CONFIRM_WAIT_SEC_CONSERVATIVE",
    "BUY_ORDER_CONFIRM_WAIT_SEC_MODERATE",
    "BUY_ORDER_CONFIRM_WAIT_SEC_AGGRESSIVE",
    "SELL_ORDER_CONFIRM_WAIT_SEC",
    "ORDER_CONFIRM_STATUS_TIMEOUT_SEC",
    "AUTO_RISK_KILL_SWITCH_ENABLED",
    "MAX_DAILY_DRAWDOWN_PCT",
    "ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE",
    "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT",
    "ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT",
    "BUY_GUARD_LLM_RUNTIME_BLOCK_ENABLED",
    "MAX_CONSECUTIVE_LOSSES",
    "LOSS_STREAK_RECOVERY_MODE",
    "LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS",
    "LOSS_STREAK_RECOVERY_MAX_ORDER_KRW",
    "LOSS_STREAK_RECOVERY_MAX_POSITION_PCT",
    "LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER",
    "LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT",
    "LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT",
    "MIN_STRATEGY_EXPECTANCY",
    "EXPECTANCY_SAMPLE_SIZE",
    "STRATEGY_EXPECTANCY_GUARD_MODE",
    "NEGATIVE_EXPECTANCY_SIZE_MULTIPLIER",
    "VOLATILITY_POSITION_SIZING_ENABLED",
    "RISK_PER_TRADE_PCT",
    "RISK_MULTIPLIER_SHORT",
    "RISK_MULTIPLIER_MID",
    "RISK_MULTIPLIER_LONG",
    "POSITION_EXIT_MANAGEMENT_ENABLED",
    "FAST_HOLDINGS_GUARD_ENABLED",
    "FAST_HOLDINGS_GUARD_INTERVAL_MIN",
    "PARTIAL_TAKE_PROFIT_ENABLED",
    "PARTIAL_TAKE_PROFIT_PCT_SHORT",
    "PARTIAL_TAKE_PROFIT_PCT_MID",
    "PARTIAL_TAKE_PROFIT_PCT_LONG",
    "PARTIAL_TAKE_PROFIT_SIZE_PCT_SHORT",
    "PARTIAL_TAKE_PROFIT_SIZE_PCT_MID",
    "PARTIAL_TAKE_PROFIT_SIZE_PCT_LONG",
    "BREAKEVEN_STOP_ENABLED",
    "BREAKEVEN_TRIGGER_PCT_SHORT",
    "BREAKEVEN_TRIGGER_PCT_MID",
    "BREAKEVEN_TRIGGER_PCT_LONG",
    "BREAKEVEN_BUFFER_BPS",
    "TRAILING_PROFIT_GUARD_ENABLED",
    "TRAILING_PROFIT_ACTIVATE_PCT_SHORT",
    "TRAILING_PROFIT_ACTIVATE_PCT_MID",
    "TRAILING_PROFIT_ACTIVATE_PCT_LONG",
    "TRAILING_PROFIT_DRAWDOWN_PCT_SHORT",
    "TRAILING_PROFIT_DRAWDOWN_PCT_MID",
    "TRAILING_PROFIT_DRAWDOWN_PCT_LONG",
    "DEFAULT_STOP_LOSS_PCT_SHORT",
    "DEFAULT_STOP_LOSS_PCT_MID",
    "DEFAULT_STOP_LOSS_PCT_LONG",
    "DEFAULT_TAKE_PROFIT_PCT_SHORT",
    "DEFAULT_TAKE_PROFIT_PCT_MID",
    "DEFAULT_TAKE_PROFIT_PCT_LONG",
    "SCALE_IN_CANDIDATE_ENABLED",
    "SCALE_IN_MIN_PULLBACK_PCT_MID",
    "SCALE_IN_MIN_PULLBACK_PCT_LONG",
    "SCALE_IN_MAX_PULLBACK_PCT",
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
    "LLM_EXECUTION_MODE_TIER1",
    "LLM_EXECUTION_MODE_TIER2",
    "LLM_DISTRIBUTED_PROFILE_TIER1",
    "LLM_DISTRIBUTED_PROFILE_TIER2",
    "LLM_FALLBACK_MODEL_TIER1",
    "LLM_FALLBACK_MODEL_TIER2",
    "CLAUDE_CODE_MODEL",
    "CLAUDE_CODE_MODEL_TIER1",
    "CLAUDE_CODE_MODEL_TIER2",
    "CLAUDE_CODE_EFFORT_TIER1",
    "CLAUDE_CODE_EFFORT_TIER2",
    "CLAUDE_CODE_BARE_TIER1",
    "CLAUDE_CODE_BARE_TIER2",
    "CODEX_MODEL",
    "CODEX_MODEL_TIER1",
    "CODEX_MODEL_TIER2",
    "CODEX_REASONING_EFFORT_TIER1",
    "CODEX_REASONING_EFFORT_TIER2",
    "CODEX_TIMEOUT_SEC_TIER1",
    "CODEX_TIMEOUT_SEC_TIER2",
    "LLM_SLOW_CALL_WARN_SEC",
    "LLM_TIER1_CONCURRENCY",
    "LLM_TIER2_CONCURRENCY",
    "TIER1_LLM_TIMEOUT_SEC",
    "DETERMINISTIC_TIER1_FAST_GATE_MODE",
    "DETERMINISTIC_TIER1_FAST_GATE_ENABLED",
    "TIER1_ANALYSIS_CACHE_TTL_SEC",
    "TIER1_ANALYSIS_CACHE_PRICE_BUCKET_BPS",
    "TIER1_FAST_GATE_LATE_BUY_CUTOFF_HOUR",
    "TIER1_FAST_GATE_LATE_BUY_CUTOFF_MINUTE",
    "TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT",
    "TIER1_FAST_GATE_MIN_CONTINUE_SCORE",
    "TIER1_FAST_GATE_BULL_MOMENTUM_ALLOW_ENABLED",
    "TIER1_FAST_GATE_BULL_MOMENTUM_MIN_CHANGE_PCT",
    "TIER1_FAST_GATE_BULL_MOMENTUM_MIN_SCORE",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_MODEL_TIER1",
    "OLLAMA_MODEL_TIER2",
    "MANUAL_LLM_PROVIDER",
    "MANUAL_LLM_EXECUTION_MODE",
    "MANUAL_LLM_MODEL",
    "MANUAL_LLM_FALLBACK_PROVIDER",
    "MANUAL_LLM_FALLBACK_MODEL",
    "NEWS_LLM_ENABLED",
    "NEWS_LLM_PROVIDER",
    "NEWS_LLM_EXECUTION_MODE",
    "NEWS_LLM_MODEL",
    "NEWS_LLM_FALLBACK_PROVIDER",
    "NEWS_LLM_FALLBACK_MODEL",
    "NEWS_DOMESTIC_MEDIA_ENABLED",
    "NEWS_INCLUDE_FOREIGN",
    "NEWS_TRANSLATE_FOREIGN_ENABLED",
    "NEWS_NASDAQ_ENABLED",
    "NEWS_GATE_ROLLOUT_MODE",
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

SECRET_RUNTIME_SETTINGS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_API_KEY_REGISTRY",
}

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
        if key == "TIER1_LLM_TIMEOUT_SEC":
            if normalized_int < 10 or normalized_int > 180:
                raise HTTPException(status_code=400, detail=f"{key} must be between 10 and 180")
        if key == "TIER1_ANALYSIS_CACHE_TTL_SEC":
            if normalized_int < 10 or normalized_int > 1800:
                raise HTTPException(status_code=400, detail=f"{key} must be between 10 and 1800")
        if key == "TIER1_ANALYSIS_CACHE_PRICE_BUCKET_BPS":
            if normalized_int < 0 or normalized_int > 200:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 200")
        if key == "NEWS_SOURCE_FAILURE_COOLDOWN_MIN":
            if normalized_int < 1 or normalized_int > 240:
                raise HTTPException(status_code=400, detail=f"{key} must be between 1 and 240")
        if key == "BROKER_BALANCE_RETRY_DELAY_MS":
            if normalized_int < 100 or normalized_int > 5000:
                raise HTTPException(status_code=400, detail=f"{key} must be between 100 and 5000")
        if key == "INTRADAY_RESCAN_INTERVAL_MIN":
            if normalized_int < 1 or normalized_int > 60:
                raise HTTPException(status_code=400, detail=f"{key} must be between 1 and 60")
        if key == "LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS":
            if normalized_int < 0 or normalized_int > 3:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 3")
        if key == "LOSS_STREAK_RECOVERY_MAX_ORDER_KRW":
            if normalized_int < 0 or normalized_int > 10_000_000:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 10000000")
        return normalized_int

    if isinstance(current, float):
        try:
            normalized_float = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc
        if key in {
            "MAX_DAILY_DRAWDOWN_PCT",
            "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT",
            "ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT",
            "LOSS_STREAK_RECOVERY_MAX_POSITION_PCT",
            "LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT",
            "LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT",
        }:
            if normalized_float < 0 or normalized_float > 100:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 100")
        if key == "LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER":
            if normalized_float <= 0 or normalized_float > 1:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 1")
        return normalized_float

    if key in {
        "LLM_PROVIDER_TIER1",
        "LLM_PROVIDER_TIER2",
        "LLM_FALLBACK_PROVIDER_TIER1",
        "LLM_FALLBACK_PROVIDER_TIER2",
    }:
        normalized = str(value).upper()
        if key.startswith("LLM_FALLBACK_PROVIDER_") and normalized in {"", "NONE"}:
            return ""
        if normalized not in {"CLAUDE_CODE", "CLAUDE_API", "CODEX", "OLLAMA"}:
            return _SKIP
        return normalized

    if key in {"MANUAL_LLM_PROVIDER", "NEWS_LLM_PROVIDER"}:
        normalized = str(value).upper()
        if normalized not in {"CLAUDE_CODE", "CLAUDE_API", "CODEX", "OLLAMA"}:
            return _SKIP
        return normalized

    if key in {"MANUAL_LLM_FALLBACK_PROVIDER", "NEWS_LLM_FALLBACK_PROVIDER"}:
        normalized = str(value).upper()
        if normalized in {"", "NONE"}:
            return ""
        if normalized not in {"CLAUDE_CODE", "CLAUDE_API", "CODEX", "OLLAMA"}:
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

    if key == "ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE":
        normalized = str(value or "").upper().strip()
        if normalized not in {"OFF", "REPORT_ONLY", "BLOCK_BUY", "KILL_SWITCH"}:
            return _SKIP
        return normalized

    if key == "LOSS_STREAK_RECOVERY_MODE":
        normalized = str(value or "").upper().strip()
        if normalized not in {"OFF", "BLOCK_BUY", "SHADOW", "REDUCE_SIZE", "PROBATION"}:
            return _SKIP
        return normalized

    if key == "NEWS_GATE_ROLLOUT_MODE":
        normalized = str(value or "").upper().strip()
        if normalized in {"", "LEGACY"}:
            return ""
        if normalized not in {
            "OFF",
            "POLL_ONLY",
            "SHADOW_ONLY",
            "SEMI_AUTO_GATE_RECOMMENDATION",
            "BUY_BLOCK_GATE",
        }:
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

    if key in {"CLAUDE_CODE_EFFORT_TIER1", "CLAUDE_CODE_EFFORT_TIER2"}:
        normalized = str(value or "").lower().strip()
        if normalized not in {"low", "medium", "high", "xhigh", "max"}:
            return _SKIP
        return normalized

    if key in {"CODEX_REASONING_EFFORT_TIER1", "CODEX_REASONING_EFFORT_TIER2"}:
        normalized = str(value or "").lower().strip()
        if normalized not in {"low", "medium", "high", "xhigh"}:
            return _SKIP
        return normalized

    if key in {
        "LLM_EXECUTION_MODE_TIER1",
        "LLM_EXECUTION_MODE_TIER2",
        "MANUAL_LLM_EXECUTION_MODE",
        "NEWS_LLM_EXECUTION_MODE",
    }:
        normalized = str(value or "").upper().strip()
        if normalized not in {"SINGLE", "DISTRIBUTED", "CONSENSUS"}:
            return _SKIP
        return normalized

    if key == "DETERMINISTIC_TIER1_FAST_GATE_MODE":
        normalized = str(value or "").upper().strip()
        if normalized in {"", "LEGACY"}:
            return ""
        if normalized not in {"OFF", "SHADOW", "ENFORCE"}:
            return _SKIP
        return normalized

    if key in {"LLM_DISTRIBUTED_PROFILE_TIER1", "LLM_DISTRIBUTED_PROFILE_TIER2"}:
        normalized = str(value or "").upper().strip()
        if normalized not in {"FAST", "FULL"}:
            return _SKIP
        return normalized

    if isinstance(current, str):
        return str(value)

    return value


def is_skipped_runtime_setting_value(value: Any) -> bool:
    return value is _SKIP
