"""Adapters from existing trading gates to shared policy trace metadata."""
from __future__ import annotations

from typing import Any

from strategy.policy.types import (
    PolicyAction,
    PolicyDecision,
    PolicyEffect,
    PolicyEffectType,
    PolicyScope,
    PolicyTrace,
)


PRIORITY = {
    "candidate_scoring": 10,
    "pre_analysis_gate": 20,
    "deterministic_tier1_fast_gate": 30,
    "deterministic_final_gate": 40,
    "tier1_cost_gate": 45,
    "cost_gate": 50,
    "news_gate": 55,
    "exposure_alignment": 60,
    "risk_manager": 70,
    "order_submission": 90,
    "holding_exit": 80,
}


def trace_dict(*decisions: PolicyDecision | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return PolicyTrace(
        decisions=tuple(decision for decision in decisions if decision is not None),
        context=context or {},
    ).to_dict()


def with_policy_trace(
    detail: dict[str, Any] | None,
    *decisions: PolicyDecision | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(detail or {})
    payload["policy_trace"] = trace_dict(*decisions, context=context)
    return payload


def from_pre_analysis_gate(gate: Any) -> PolicyDecision:
    approved = bool(getattr(gate, "approved", False))
    return PolicyDecision(
        owner="pre_analysis_gate",
        scope=PolicyScope.CANDIDATE,
        action=PolicyAction.ALLOW if approved else PolicyAction.BLOCK,
        priority=PRIORITY["pre_analysis_gate"],
        reason_code=str(getattr(gate, "code", "") or ("APPROVED" if approved else "BLOCKED")),
        reason=str(getattr(gate, "reason", "") or ""),
        metadata=dict(getattr(gate, "detail", {}) or {}),
    )


def from_tier1_fast_gate(gate: Any, *, mode: str = "ENFORCE") -> PolicyDecision:
    should_skip = bool(getattr(gate, "should_skip_tier1", False))
    normalized_mode = str(mode or "ENFORCE").upper()
    action = PolicyAction.OBSERVE if normalized_mode == "SHADOW" else (
        PolicyAction.BLOCK if should_skip else PolicyAction.ALLOW
    )
    detail = dict(getattr(gate, "detail", {}) or {})
    detail.setdefault("score", getattr(gate, "score", None))
    detail["mode"] = normalized_mode
    detail["would_skip_tier1"] = should_skip
    return PolicyDecision(
        owner="deterministic_tier1_fast_gate",
        scope=PolicyScope.CANDIDATE,
        action=action,
        priority=PRIORITY["deterministic_tier1_fast_gate"],
        reason_code=str(getattr(gate, "code", "") or "UNKNOWN"),
        reason=str(getattr(gate, "reason", "") or ""),
        metadata=detail,
    )


def from_final_gate(gate: Any) -> PolicyDecision:
    approved = bool(getattr(gate, "approved", False))
    return PolicyDecision(
        owner="deterministic_final_gate",
        scope=PolicyScope.BUY,
        action=PolicyAction.ALLOW if approved else PolicyAction.BLOCK,
        priority=PRIORITY["deterministic_final_gate"],
        reason_code=str(getattr(gate, "code", "") or ("APPROVED" if approved else "BLOCKED")),
        reason=str(getattr(gate, "reason", "") or ""),
        metadata=dict(getattr(gate, "detail", {}) or {}),
    )


def from_cost_gate(gate: dict[str, Any], *, owner: str = "cost_gate", reason_code: str = "LOW_EDGE_AFTER_COST") -> PolicyDecision:
    approved = bool(gate.get("approved", False))
    stage = str(gate.get("stage") or owner).lower()
    return PolicyDecision(
        owner=owner,
        scope=PolicyScope.BUY,
        action=PolicyAction.ALLOW if approved else PolicyAction.BLOCK,
        priority=PRIORITY.get(owner, PRIORITY["cost_gate"]),
        reason_code="APPROVED" if approved else reason_code,
        reason=str(gate.get("reason") or ""),
        metadata={**gate, "stage": stage},
    )


def from_news_gate(gate: dict[str, Any]) -> PolicyDecision:
    approved = bool(gate.get("approved", True)) or not bool(gate.get("blocking_enabled", True))
    return PolicyDecision(
        owner="news_gate",
        scope=PolicyScope.BUY,
        action=PolicyAction.ALLOW if approved else PolicyAction.BLOCK,
        priority=PRIORITY["news_gate"],
        reason_code="APPROVED" if approved else "NEWS_NEGATIVE_PRESSURE",
        reason=str(gate.get("reason") or ""),
        metadata=gate,
    )


def from_exposure_alignment(decision: Any) -> PolicyDecision:
    initial_quantity = int(getattr(decision, "initial_quantity", 0) or 0)
    final_quantity = int(getattr(decision, "final_quantity", 0) or 0)
    effects: tuple[PolicyEffect, ...] = ()
    if final_quantity != initial_quantity:
        effects = (
            PolicyEffect(
                field="suggested_quantity",
                before=initial_quantity,
                after=final_quantity,
                effect_type=(
                    PolicyEffectType.RAISE if final_quantity > initial_quantity else PolicyEffectType.REDUCE
                ),
                reason=str(getattr(decision, "reason", "") or ""),
            ),
        )
    return PolicyDecision(
        owner="exposure_alignment",
        scope=PolicyScope.BUY,
        action=PolicyAction.ADJUST if bool(getattr(decision, "applied", False)) else PolicyAction.OBSERVE,
        priority=PRIORITY["exposure_alignment"],
        reason_code=str(getattr(decision, "reason", "") or "not_applied").upper(),
        reason=str(getattr(decision, "reason", "") or ""),
        effects=effects,
        metadata={
            "applied": bool(getattr(decision, "applied", False)),
            "initial_notional": getattr(decision, "initial_notional", None),
            "final_notional": getattr(decision, "final_notional", None),
            "current_exposure_pct": getattr(decision, "current_exposure_pct", None),
            "target_exposure_pct": getattr(decision, "target_exposure_pct", None),
            "min_order_krw": getattr(decision, "min_order_krw", None),
            "cap_order_krw": getattr(decision, "cap_order_krw", None),
        },
    )


def from_risk_result(result: dict[str, Any], *, input_quantity: int | None = None) -> PolicyDecision:
    approved = bool(result.get("approved", False))
    adjustments = [item for item in result.get("adjustments", []) if isinstance(item, dict)]
    effects = tuple(_effect_from_adjustment(item) for item in adjustments)
    if not approved:
        action = PolicyAction.BLOCK
    elif effects:
        action = PolicyAction.ADJUST
    else:
        action = PolicyAction.ALLOW
    metadata = {
        key: value
        for key, value in result.items()
        if key not in {"policy_trace", "adjustments"}
    }
    if input_quantity is not None:
        metadata["input_quantity"] = int(input_quantity)
    return PolicyDecision(
        owner="risk_manager",
        scope=PolicyScope.BUY,
        action=action,
        priority=PRIORITY["risk_manager"],
        reason_code=str(result.get("trigger") or ("APPROVED" if approved else "RISK_BLOCK")),
        reason=str(result.get("reason") or ""),
        effects=effects,
        metadata={**metadata, "adjustments": adjustments},
    )


def from_order_submission(decision: Any, *, side: str | None = None) -> PolicyDecision:
    allowed = bool(getattr(decision, "allowed", False))
    mode = str(getattr(decision, "mode", "") or "")
    side_value = str(side or "").upper()
    return PolicyDecision(
        owner="order_submission",
        scope=PolicyScope.ORDER_SUBMISSION,
        action=PolicyAction.ALLOW if allowed else PolicyAction.BLOCK,
        priority=PRIORITY["order_submission"],
        reason_code="APPROVED" if allowed else (mode or "ORDER_SUBMISSION_BLOCK"),
        reason=str(getattr(decision, "reason", "") or ""),
        metadata={"mode": mode, "side": side_value},
    )


def from_order_block(
    *,
    reason_code: str,
    reason: str,
    side: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        owner="order_submission",
        scope=PolicyScope.ORDER_SUBMISSION,
        action=PolicyAction.BLOCK,
        priority=PRIORITY["order_submission"],
        reason_code=str(reason_code or "ORDER_SUBMISSION_BLOCK"),
        reason=str(reason or ""),
        metadata={"side": str(side or "").upper(), **(metadata or {})},
    )


def from_exit_event(
    *,
    event_type: str,
    blocked: bool = False,
    exit_reason: str = "",
    quantity: int | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> PolicyDecision:
    if blocked:
        action = PolicyAction.DEFER
    elif quantity is not None:
        action = PolicyAction.ADJUST
    else:
        action = PolicyAction.ALLOW
    effects: tuple[PolicyEffect, ...] = ()
    if quantity is not None:
        effects = (
            PolicyEffect(
                field="sell_quantity",
                before=None,
                after=int(quantity),
                effect_type=PolicyEffectType.SET,
                reason=reason,
            ),
        )
    return PolicyDecision(
        owner="holding_exit",
        scope=PolicyScope.HOLDING_EXIT,
        action=action,
        priority=PRIORITY["holding_exit"],
        reason_code=str(exit_reason or event_type or "HOLDING_EXIT").upper(),
        reason=reason,
        effects=effects,
        metadata={"event_type": event_type, **(metadata or {})},
    )


def _effect_from_adjustment(item: dict[str, Any]) -> PolicyEffect:
    before = _int_or_none(item.get("previous_quantity"))
    after = _int_or_none(item.get("adjusted_quantity"))
    if before is not None and after is not None:
        effect_type = PolicyEffectType.RAISE if after > before else (
            PolicyEffectType.REDUCE if after < before else PolicyEffectType.SET
        )
    else:
        effect_type = PolicyEffectType.SET
    return PolicyEffect(
        field="suggested_quantity",
        before=before,
        after=after,
        effect_type=effect_type,
        reason=str(item.get("reason") or ""),
        metadata={key: value for key, value in item.items() if key not in {"previous_quantity", "adjusted_quantity", "reason"}},
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
