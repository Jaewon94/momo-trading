"""Canonical trading policy owner registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from strategy.policy.types import PolicyScope


@dataclass(frozen=True)
class PolicyRegistryEntry:
    owner: str
    priority: int
    scope: PolicyScope | str
    description: str
    settings: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "priority": int(self.priority),
            "scope": self.scope.value if isinstance(self.scope, PolicyScope) else str(self.scope),
            "description": self.description,
            "settings": list(self.settings),
            "required_tests": list(self.required_tests),
            "notes": self.notes,
        }


POLICY_REGISTRY: tuple[PolicyRegistryEntry, ...] = (
    PolicyRegistryEntry(
        owner="admin_safety",
        priority=1,
        scope="ADMIN",
        description="Admin confirmation and protected runtime-operation controls.",
        settings=(),
        required_tests=("tests/api/test_admin_settings_routes.py",),
    ),
    PolicyRegistryEntry(
        owner="session_safety",
        priority=5,
        scope="SESSION",
        description="Market-session and off-hours trading controls.",
        settings=("DAY_TRADING_ONLY", "BUY_CUTOFF_HOUR", "BUY_CUTOFF_MINUTE"),
        required_tests=("tests/scheduler/test_scheduler_runtime_paths.py",),
    ),
    PolicyRegistryEntry(
        owner="scheduler",
        priority=8,
        scope="SESSION",
        description="Scheduler enabled/running state and recurring job controls.",
        settings=("SCHEDULER_ENABLED",),
        required_tests=("tests/scheduler/test_scheduler_runtime_paths.py",),
    ),
    PolicyRegistryEntry(
        owner="candidate_scoring",
        priority=10,
        scope=PolicyScope.CANDIDATE,
        description="Scanner candidate breadth, ranking, and selected-symbol evidence.",
        settings=("SCANNER_MAX_CANDIDATES",),
        required_tests=("tests/services/test_candidate_scoring_service.py",),
    ),
    PolicyRegistryEntry(
        owner="pre_analysis_gate",
        priority=20,
        scope=PolicyScope.CANDIDATE,
        description="Cheap pre-LLM skips for missing data, insufficient cash, and bearish charts.",
        settings=(),
        required_tests=("tests/services/test_pre_analysis_gate_service.py",),
    ),
    PolicyRegistryEntry(
        owner="deterministic_tier1_fast_gate",
        priority=30,
        scope=PolicyScope.CANDIDATE,
        description="Deterministic LLM avoidance for clear non-buy scan candidates.",
        settings=("DETERMINISTIC_TIER1_FAST_GATE_MODE", "DETERMINISTIC_TIER1_FAST_GATE_ENABLED"),
        required_tests=("tests/agent/test_trading_agent_cycles.py",),
    ),
    PolicyRegistryEntry(
        owner="tier1_analysis",
        priority=35,
        scope=PolicyScope.CANDIDATE,
        description="Tier1 LLM prompt/runtime contract and cache behavior.",
        settings=("TIER1_LLM_TIMEOUT_SEC", "TIER1_PROVIDER", "TIER1_MODEL"),
        required_tests=("tests/agent/test_trading_agent_cycles.py",),
    ),
    PolicyRegistryEntry(
        owner="deterministic_final_gate",
        priority=40,
        scope=PolicyScope.BUY,
        description="Tier2-before deterministic validation for confidence, RR, stop loss, and buying power.",
        settings=(),
        required_tests=("tests/services/test_deterministic_final_gate_service.py",),
    ),
    PolicyRegistryEntry(
        owner="tier1_cost_gate",
        priority=45,
        scope=PolicyScope.BUY,
        description="Pre-Tier2 execution-cost edge gate.",
        settings=("COST_GATE_ENABLED", "ESTIMATED_ENTRY_COST_BPS", "ESTIMATED_EXIT_COST_BPS"),
        required_tests=("tests/agent/test_trading_agent_cost_gate.py",),
    ),
    PolicyRegistryEntry(
        owner="cost_gate",
        priority=50,
        scope=PolicyScope.BUY,
        description="Final BUY execution-cost edge gate.",
        settings=("COST_GATE_ENABLED", "MIN_EDGE_TO_COST_RATIO_MID"),
        required_tests=("tests/agent/test_trading_agent_cost_gate.py",),
    ),
    PolicyRegistryEntry(
        owner="news_gate",
        priority=55,
        scope=PolicyScope.BUY,
        description="News-signal negative-pressure BUY gate and rollout mode.",
        settings=("NEWS_GATE_ENABLED", "NEWS_GATE_ROLLOUT_MODE", "NEWS_NEGATIVE_PRESSURE_THRESHOLD"),
        required_tests=("tests/agent/test_trading_agent_news_gate.py", "tests/services/test_news_gate_rollout_service.py"),
    ),
    PolicyRegistryEntry(
        owner="news_intel",
        priority=56,
        scope=PolicyScope.CANDIDATE,
        description="News polling, enrichment, runtime health, and prompt context evidence.",
        settings=("NEWS_POLL_ENABLED", "NEWS_CONTEXT_LOOKBACK_HOURS"),
        required_tests=("tests/services/test_news_signal_service.py",),
    ),
    PolicyRegistryEntry(
        owner="exposure_alignment",
        priority=60,
        scope=PolicyScope.BUY,
        description="Risk-appetite target exposure sizing floor before risk manager caps.",
        settings=("AGGRESSIVE_EXPOSURE_ALIGNMENT_ENABLED", "AGGRESSIVE_TARGET_EXPOSURE_PCT"),
        required_tests=("tests/agent/test_trading_agent_cycles.py",),
    ),
    PolicyRegistryEntry(
        owner="trading_guard",
        priority=65,
        scope=PolicyScope.BUY,
        description="Daily drawdown, account equity, loss streak, expectancy, and runtime kill-switch controls.",
        settings=("MAX_DAILY_DRAWDOWN_PCT", "MAX_CONSECUTIVE_LOSSES", "AUTO_RISK_KILL_SWITCH_ENABLED"),
        required_tests=("tests/strategy/test_trading_guard.py",),
    ),
    PolicyRegistryEntry(
        owner="risk_manager",
        priority=70,
        scope=PolicyScope.BUY,
        description="Final internal sizing caps, RR validation, cash limits, and position limits.",
        settings=("MAX_DAILY_TRADES", "MAX_SINGLE_ORDER_KRW", "MIN_CASH_RATIO", "MAX_POSITION_PCT"),
        required_tests=("tests/strategy/test_risk_manager_enhancements.py",),
    ),
    PolicyRegistryEntry(
        owner="scale_in",
        priority=72,
        scope=PolicyScope.BUY,
        description="Scale-in eligibility and additional lot sizing constraints.",
        settings=("SCALE_IN_ENABLED",),
        required_tests=("tests/strategy/policy/test_settings_catalog.py",),
    ),
    PolicyRegistryEntry(
        owner="holding_review",
        priority=75,
        scope=PolicyScope.HOLDING_EXIT,
        description="Scheduled holding review prompts and hold/sell decision context.",
        settings=("HOLDING_REVIEW_ENABLED",),
        required_tests=("tests/scheduler/test_scheduler_runtime_paths.py",),
    ),
    PolicyRegistryEntry(
        owner="holding_exit",
        priority=80,
        scope=PolicyScope.HOLDING_EXIT,
        description="Stop loss, take profit, min-hold, staged exit, and event-triggered sell policy.",
        settings=("DEFAULT_STOP_LOSS_PCT_MID", "DEFAULT_TAKE_PROFIT_PCT_MID"),
        required_tests=("tests/strategy/test_position_exit_policy.py", "tests/agent/test_trading_agent_cycles.py"),
    ),
    PolicyRegistryEntry(
        owner="order_reservation",
        priority=85,
        scope=PolicyScope.ORDER_SUBMISSION,
        description="In-cycle BUY cash reservation before final order submission.",
        settings=("ORDER_RESERVATION_ENFORCEMENT",),
        required_tests=("tests/agent/test_order_reservation.py", "tests/agent/test_trading_agent_risk_reservation.py"),
    ),
    PolicyRegistryEntry(
        owner="order_submission",
        priority=90,
        scope=PolicyScope.ORDER_SUBMISSION,
        description="Final order mode, post-liquidation BUY block, and pending order gates.",
        settings=("TRADING_ENABLED", "ORDER_SUBMISSION_MODE", "POST_LIQUIDATION_BUY_BLOCK_ENABLED"),
        required_tests=("tests/agent/test_decision_maker.py", "tests/core/test_post_liquidation_guard.py"),
    ),
    PolicyRegistryEntry(
        owner="broker_reconciliation",
        priority=95,
        scope=PolicyScope.ORDER_SUBMISSION,
        description="Broker pending/open-position reconciliation and pending confirm recovery.",
        settings=("BROKER_PROVIDER",),
        required_tests=("tests/scheduler/test_portfolio_sync_job.py", "tests/scripts/test_check_runtime_integrity.py"),
    ),
    PolicyRegistryEntry(
        owner="llm_runtime",
        priority=110,
        scope="RUNTIME",
        description="LLM provider/model runtime selection, cooldown, and health controls.",
        settings=("TIER1_PROVIDER", "TIER2_PROVIDER", "LLM_RUNTIME_COOLDOWN_SEC"),
        required_tests=("tests/services/test_runtime_settings_service.py",),
    ),
    PolicyRegistryEntry(
        owner="manual_llm_runtime",
        priority=111,
        scope="RUNTIME",
        description="Manual provider/model override runtime controls.",
        settings=("MANUAL_LLM_PROVIDER", "MANUAL_LLM_MODEL"),
        required_tests=("tests/agent/test_trading_agent_cycles.py",),
    ),
    PolicyRegistryEntry(
        owner="recommendation_lifecycle",
        priority=120,
        scope="RECOMMENDATION",
        description="Semi-auto recommendation expiry, approval, and lifecycle controls.",
        settings=("RECOMMENDATION_EXPIRE_MIN",),
        required_tests=("tests/agent/test_decision_maker.py",),
    ),
    PolicyRegistryEntry(
        owner="runtime_settings",
        priority=130,
        scope="RUNTIME",
        description="Mutable runtime setting validation and persisted override lifecycle.",
        settings=(),
        required_tests=("tests/api/test_admin_settings_validation.py", "tests/services/test_runtime_settings_service.py"),
    ),
)


def registry_by_owner(entries: Iterable[PolicyRegistryEntry] = POLICY_REGISTRY) -> dict[str, PolicyRegistryEntry]:
    return {entry.owner: entry for entry in entries}


def registry_as_dict(entries: Iterable[PolicyRegistryEntry] = POLICY_REGISTRY) -> list[dict]:
    return [entry.to_dict() for entry in entries]


def render_policy_registry_markdown(entries: Iterable[PolicyRegistryEntry] = POLICY_REGISTRY) -> str:
    lines = [
        "| Priority | Owner | Scope | Description | Key settings | Required tests |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in sorted(entries, key=lambda item: (item.priority, item.owner)):
        scope = entry.scope.value if isinstance(entry.scope, PolicyScope) else str(entry.scope)
        settings = ", ".join(f"`{item}`" for item in entry.settings) or "-"
        tests = ", ".join(f"`{item}`" for item in entry.required_tests) or "-"
        lines.append(
            f"| {entry.priority} | `{entry.owner}` | {scope} | {entry.description} | {settings} | {tests} |"
        )
    return "\n".join(lines)
