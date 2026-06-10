"""Typed policy decision contracts for trading policy trace metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ADJUST = "ADJUST"
    DEFER = "DEFER"
    OBSERVE = "OBSERVE"


class PolicyScope(str, Enum):
    CANDIDATE = "CANDIDATE"
    BUY = "BUY"
    SELL = "SELL"
    HOLDING_EXIT = "HOLDING_EXIT"
    ORDER_SUBMISSION = "ORDER_SUBMISSION"


class PolicyEffectType(str, Enum):
    RAISE = "RAISE"
    REDUCE = "REDUCE"
    SET = "SET"
    CLEAR = "CLEAR"
    NONE = "NONE"


@dataclass(frozen=True)
class PolicyEffect:
    field: str
    before: Any = None
    after: Any = None
    effect_type: PolicyEffectType | str = PolicyEffectType.NONE
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_enforcement: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "before": _jsonable(self.before),
            "after": _jsonable(self.after),
            "effect_type": _enum_value(self.effect_type),
            "reason": self.reason,
            "metadata": _jsonable(self.metadata),
            "requires_enforcement": bool(self.requires_enforcement),
        }


@dataclass(frozen=True)
class PolicyDecision:
    owner: str
    scope: PolicyScope | str
    action: PolicyAction | str
    reason_code: str
    reason: str
    priority: int = 0
    effects: tuple[PolicyEffect, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "scope": _enum_value(self.scope),
            "action": _enum_value(self.action),
            "priority": int(self.priority),
            "reason_code": self.reason_code,
            "reason": self.reason,
            "effects": [effect.to_dict() for effect in self.effects],
            "metadata": _jsonable(self.metadata),
        }


@dataclass(frozen=True)
class PolicyTrace:
    decisions: tuple[PolicyDecision, ...]
    schema_version: str = "momo.policy_trace.v1"
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decisions = tuple(self.decisions or ())
        return {
            "schema_version": self.schema_version,
            "decision_count": len(decisions),
            "blocked": any(_enum_value(decision.action) == PolicyAction.BLOCK.value for decision in decisions),
            "adjusted": any(_enum_value(decision.action) == PolicyAction.ADJUST.value for decision in decisions),
            "decisions": [decision.to_dict() for decision in decisions],
            "context": _jsonable(self.context),
        }


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
