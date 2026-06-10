"""Runtime trading policy settings catalog.

The catalog is metadata only. It does not own validation or change live values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.runtime_settings import MUTABLE_SETTINGS
from strategy.policy.types import PolicyScope


@dataclass(frozen=True)
class PolicySettingMetadata:
    key: str
    owner: str
    scope: PolicyScope | str
    risk: str
    mutable: bool = True
    source: str = "core.runtime_settings.MUTABLE_SETTINGS"
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        scope = self.scope.value if isinstance(self.scope, PolicyScope) else self.scope
        return {
            "key": self.key,
            "owner": self.owner,
            "scope": scope,
            "risk": self.risk,
            "mutable": self.mutable,
            "source": self.source,
            "notes": self.notes,
        }


def build_policy_settings_catalog(keys: Iterable[str] = MUTABLE_SETTINGS) -> dict[str, PolicySettingMetadata]:
    return {key: classify_policy_setting(key) for key in keys}


def classify_policy_setting(key: str) -> PolicySettingMetadata:
    key = str(key or "").upper()
    owner, scope, risk, notes = _classify(key)
    return PolicySettingMetadata(
        key=key,
        owner=owner,
        scope=scope,
        risk=risk,
        notes=notes,
    )


def catalog_by_owner(
    catalog: dict[str, PolicySettingMetadata] | None = None,
) -> dict[str, list[PolicySettingMetadata]]:
    grouped: dict[str, list[PolicySettingMetadata]] = {}
    for item in (catalog or POLICY_SETTINGS_CATALOG).values():
        grouped.setdefault(item.owner, []).append(item)
    for values in grouped.values():
        values.sort(key=lambda item: item.key)
    return dict(sorted(grouped.items()))


def catalog_as_dict(
    catalog: dict[str, PolicySettingMetadata] | None = None,
) -> dict[str, dict[str, object]]:
    return {
        key: metadata.to_dict()
        for key, metadata in (catalog or POLICY_SETTINGS_CATALOG).items()
    }


def _classify(key: str) -> tuple[str, PolicyScope | str, str, str]:
    if key in {"TRADING_ENABLED", "ORDER_SUBMISSION_MODE", "AUTONOMY_MODE"}:
        return "order_submission", PolicyScope.ORDER_SUBMISSION, "high", "Can enable, disable, or route order submission."
    if key.startswith("ADMIN_"):
        return "admin_safety", "ADMIN", "medium", "Controls protected admin write confirmation behavior."
    if key in {"SCHEDULER_ENABLED", "INTRADAY_RESCAN_INTERVAL_MIN"}:
        return "scheduler", "SCHEDULER", "medium", "Controls cycle scheduling and scan cadence."
    if key in {"POST_LIQUIDATION_BUY_BLOCK_ENABLED", "DAY_TRADING_ONLY"}:
        return "session_safety", PolicyScope.ORDER_SUBMISSION, "high", "Controls end-of-day and session buy eligibility."
    if key.startswith("BUY_ORDER_") or key.startswith("SELL_ORDER_") or key.startswith("ORDER_CONFIRM_"):
        return "order_submission", PolicyScope.ORDER_SUBMISSION, "high", "Controls order execution or confirmation behavior."
    if key == "ORDER_RESERVATION_ENFORCEMENT":
        return "order_reservation", PolicyScope.BUY, "medium", "Controls cycle-local cash reservation enforcement."

    if key in {
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
    }:
        return "trading_guard", PolicyScope.BUY, "high", "Can block, reduce, or kill-switch BUY behavior."

    if key in {
        "VOLATILITY_POSITION_SIZING_ENABLED",
        "RISK_PER_TRADE_PCT",
        "RISK_MULTIPLIER_SHORT",
        "RISK_MULTIPLIER_MID",
        "RISK_MULTIPLIER_LONG",
        "RISK_APPETITE",
    }:
        return "risk_manager", PolicyScope.BUY, "high", "Controls risk sizing or risk-appetite interpretation."

    if key.startswith("AGGRESSIVE_EXPOSURE_") or key in {
        "AGGRESSIVE_TARGET_EXPOSURE_PCT",
        "AGGRESSIVE_MIN_BUY_ORDER_KRW",
    }:
        return "exposure_alignment", PolicyScope.BUY, "high", "Can raise BUY quantity under aggressive exposure policy."

    if (
        key.startswith("POSITION_EXIT_")
        or key.startswith("FAST_HOLDINGS_")
        or key.startswith("PARTIAL_TAKE_PROFIT_")
        or key.startswith("PARTIAL_STOP_LOSS_")
        or key.startswith("BREAKEVEN_")
        or key.startswith("TRAILING_PROFIT_")
        or key.startswith("DEFAULT_STOP_LOSS_")
        or key.startswith("DEFAULT_TAKE_PROFIT_")
        or key.startswith("MIN_HOLD_MINUTES_")
    ):
        return "holding_exit", PolicyScope.HOLDING_EXIT, "high", "Controls holding review, sell timing, or exit thresholds."

    if key.startswith("SCALE_IN_"):
        return "scale_in", PolicyScope.BUY, "medium", "Controls add-buy candidate criteria."

    if (
        key == "COST_GATE_ENABLED"
        or key.startswith("ESTIMATED_")
        or key.startswith("MIN_EDGE_TO_COST_RATIO_")
    ):
        return "cost_gate", PolicyScope.BUY, "medium", "Controls expected-edge versus execution-cost gating."

    if key.startswith("DETERMINISTIC_TIER1_FAST_GATE_") or key.startswith("TIER1_FAST_GATE_"):
        return "deterministic_tier1_fast_gate", PolicyScope.CANDIDATE, "medium", "Controls pre-LLM Tier1 skip decisions."

    if key.startswith("TIER1_ANALYSIS_CACHE_") or key == "TIER1_LLM_TIMEOUT_SEC":
        return "tier1_analysis", PolicyScope.CANDIDATE, "medium", "Controls Tier1 analysis caching or timeout behavior."

    if key.startswith("HOLDINGS_REVIEW_CACHE_") or key.startswith("HOLDINGS_PRECHECK_"):
        return "holding_review", PolicyScope.HOLDING_EXIT, "medium", "Controls holding review cache or LLM skip behavior."

    if key.startswith("NEWS_GATE_") or key.startswith("NEWS_SHADOW_") or key.startswith("NEWS_ROLLOUT_"):
        return "news_gate", PolicyScope.BUY, "medium", "Controls news gate rollout or blocking behavior."
    if key.startswith("NEWS_"):
        return "news_intel", "NEWS", "low", "Controls news collection, translation, or LLM enrichment."

    if key.startswith("BROKER_BALANCE_"):
        return "broker_reconciliation", "BROKER", "medium", "Controls broker balance retry behavior."

    if key.startswith("LLM_") or key.startswith("CLAUDE_") or key.startswith("CODEX_") or key.startswith("OLLAMA_"):
        return "llm_runtime", "LLM", "medium", "Controls LLM provider, model, fallback, timeout, or concurrency."
    if key.startswith("MANUAL_LLM_"):
        return "manual_llm_runtime", "LLM", "low", "Controls manual analysis LLM provider and model."

    if key == "RECOMMENDATION_EXPIRE_MIN":
        return "recommendation_lifecycle", "RECOMMENDATION", "low", "Controls semi-auto recommendation expiry."

    return "runtime_settings", "RUNTIME", "medium", "Unclassified mutable setting; review owner before behavior changes."


POLICY_SETTINGS_CATALOG = build_policy_settings_catalog()
