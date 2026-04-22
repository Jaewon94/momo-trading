from __future__ import annotations

from dataclasses import dataclass

from core.config import settings

ORDER_SUBMISSION_FULL = "FULL"
ORDER_SUBMISSION_SELL_ONLY = "SELL_ONLY"
ORDER_SUBMISSION_READ_ONLY = "READ_ONLY"
VALID_ORDER_SUBMISSION_MODES = {
    ORDER_SUBMISSION_FULL,
    ORDER_SUBMISSION_SELL_ONLY,
    ORDER_SUBMISSION_READ_ONLY,
}


@dataclass(frozen=True)
class OrderSubmissionDecision:
    allowed: bool
    mode: str
    reason: str = ""

    def as_detail(self) -> dict[str, str]:
        return {
            "order_submission_mode": self.mode,
            "reason": self.reason,
        }


def normalize_order_submission_mode(value: object) -> str:
    mode = str(value or ORDER_SUBMISSION_FULL).upper()
    return mode if mode in VALID_ORDER_SUBMISSION_MODES else ORDER_SUBMISSION_FULL


def current_order_submission_mode() -> str:
    return normalize_order_submission_mode(getattr(settings, "ORDER_SUBMISSION_MODE", ORDER_SUBMISSION_FULL))


def decide_order_submission(side: object | None = None) -> OrderSubmissionDecision:
    if not settings.TRADING_ENABLED:
        return OrderSubmissionDecision(
            allowed=False,
            mode=current_order_submission_mode(),
            reason="TRADING_ENABLED=false",
        )

    mode = current_order_submission_mode()
    side_value = str(getattr(side, "value", side) or "").upper()

    if mode == ORDER_SUBMISSION_READ_ONLY:
        return OrderSubmissionDecision(
            allowed=False,
            mode=mode,
            reason="ORDER_SUBMISSION_MODE=READ_ONLY",
        )

    if mode == ORDER_SUBMISSION_SELL_ONLY and side_value == "BUY":
        return OrderSubmissionDecision(
            allowed=False,
            mode=mode,
            reason="ORDER_SUBMISSION_MODE=SELL_ONLY blocks BUY",
        )

    return OrderSubmissionDecision(allowed=True, mode=mode)


def effective_order_submission_mode() -> str:
    if not settings.TRADING_ENABLED:
        return "DISABLED"
    return current_order_submission_mode()


def runtime_order_override_active() -> bool:
    return current_order_submission_mode() != ORDER_SUBMISSION_FULL
