"""Shared position-exit policy helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from strategy.trade_horizon import TradeHorizon

PARTIAL_TAKE_PROFIT_MARKER = "PARTIAL_TAKE_PROFIT_DONE"
PARTIAL_STOP_LOSS_MARKER = "PARTIAL_STOP_LOSS_DONE"


@dataclass(frozen=True)
class StagedStopLossDecision:
    action: str  # "full" | "partial" | "hold"
    quantity: int = 0
    reason: str = ""


def trade_notes_dict(tr: Any) -> dict:
    notes = str(getattr(tr, "notes", "") or "")
    try:
        parsed = json.loads(notes)
    except (TypeError, ValueError):
        try:
            parsed, _end_index = json.JSONDecoder().raw_decode(notes.strip())
        except (TypeError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def trade_horizon_from_result(tr: Any) -> str:
    parsed = trade_notes_dict(tr)
    horizon = str(parsed.get("trade_horizon") or "").upper()
    if horizon in {TradeHorizon.SHORT, TradeHorizon.MID, TradeHorizon.LONG}:
        return horizon

    strategy_type = str(getattr(tr, "strategy_type", "") or "").upper()
    if "AGGRESSIVE" in strategy_type:
        return TradeHorizon.SHORT
    return TradeHorizon.MID


def note_has_marker(tr: Any, marker: str) -> bool:
    return marker in str(getattr(tr, "notes", "") or "")


def position_age_minutes(tr: Any, *, observed_at: datetime | None = None) -> float | None:
    entry_at = getattr(tr, "entry_at", None) or getattr(tr, "created_at", None)
    if not isinstance(entry_at, datetime):
        return None

    current = observed_at or datetime.now(tz=entry_at.tzinfo)
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    if entry_at.tzinfo is not None:
        entry_at = entry_at.replace(tzinfo=None)

    return max((current - entry_at).total_seconds() / 60.0, 0.0)


def is_loss_protective_stop(stop_loss_price: float | int | None, avg_buy_price: float | int | None) -> bool:
    """True only when a stop is below cost basis and therefore loss-protective."""
    try:
        stop = float(stop_loss_price or 0.0)
        avg = float(avg_buy_price or 0.0)
    except (TypeError, ValueError):
        return False
    return stop > 0 and avg > 0 and stop < avg


def is_profit_protection_stop(stop_loss_price: float | int | None, avg_buy_price: float | int | None) -> bool:
    """A stop at/above cost basis is a profit/breakeven guard, not a hard loss stop."""
    try:
        stop = float(stop_loss_price or 0.0)
        avg = float(avg_buy_price or 0.0)
    except (TypeError, ValueError):
        return False
    return stop > 0 and avg > 0 and stop >= avg


def min_hold_minutes_for_profit_exit(settings: Any, horizon: str) -> int:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.SHORT:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_SHORT", 15) or 0), 0)
    if key == TradeHorizon.LONG:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_LONG", 2880) or 0), 0)
    return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_MID", 1440) or 0), 0)


def min_hold_minutes_for_review_exit(settings: Any, horizon: str) -> int:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.SHORT:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_SHORT", 15) or 0), 0)
    if key == TradeHorizon.LONG:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_LONG", 2880) or 0), 0)
    return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_MID", 1440) or 0), 0)


def min_hold_minutes_for_soft_stop_exit(settings: Any, horizon: str) -> int:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.SHORT:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_SOFT_STOP_EXIT_SHORT", 5) or 0), 0)
    if key == TradeHorizon.LONG:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_SOFT_STOP_EXIT_LONG", 2880) or 0), 0)
    return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_SOFT_STOP_EXIT_MID", 1440) or 0), 0)


def partial_stop_loss_size_pct(settings: Any, horizon: str) -> float:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.LONG:
        return min(max(float(getattr(settings, "PARTIAL_STOP_LOSS_SIZE_PCT_LONG", 33.0) or 33.0), 1.0), 95.0)
    if key == TradeHorizon.MID:
        return min(max(float(getattr(settings, "PARTIAL_STOP_LOSS_SIZE_PCT_MID", 50.0) or 50.0), 1.0), 95.0)
    return 0.0


def partial_stop_loss_full_exit_threshold_pct(
    settings: Any,
    horizon: str,
    *,
    default_stop_loss_pct: float,
) -> float:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.LONG:
        extra = float(getattr(settings, "PARTIAL_STOP_LOSS_FULL_EXIT_EXTRA_PCT_LONG", 4.0) or 4.0)
    else:
        extra = float(getattr(settings, "PARTIAL_STOP_LOSS_FULL_EXIT_EXTRA_PCT_MID", 2.5) or 2.5)
    return float(default_stop_loss_pct) - max(extra, 0.0)


def staged_stop_loss_exit_decision(
    *,
    settings: Any,
    tr: Any,
    horizon: str | None,
    pnl_rate: float,
    holding_quantity: int,
    default_stop_loss_pct: float,
) -> StagedStopLossDecision:
    """Return how a MID/LONG default stop breach should be handled.

    SHORT positions keep the old full-exit behavior. MID/LONG first reduce risk
    by selling part of the position unless the breach is already deep.
    """
    resolved_horizon = str(horizon or trade_horizon_from_result(tr)).upper()
    quantity = max(int(holding_quantity or 0), 0)
    if (
        not bool(getattr(settings, "PARTIAL_STOP_LOSS_ENABLED", True))
        or resolved_horizon == TradeHorizon.SHORT
        or quantity <= 1
    ):
        return StagedStopLossDecision("full")

    full_exit_threshold = partial_stop_loss_full_exit_threshold_pct(
        settings,
        resolved_horizon,
        default_stop_loss_pct=default_stop_loss_pct,
    )
    if float(pnl_rate) <= full_exit_threshold:
        return StagedStopLossDecision(
            "full",
            reason=(
                f"{resolved_horizon} 손절선 깊게 이탈 "
                f"({pnl_rate:+.1f}% <= {full_exit_threshold:+.1f}%)"
            ),
        )

    if note_has_marker(tr, PARTIAL_STOP_LOSS_MARKER):
        return StagedStopLossDecision(
            "hold",
            reason=(
                f"{resolved_horizon} 1차 손실축소 완료 — 남은 수량은 "
                f"깊은 이탈 또는 AI 리뷰 전까지 보류 "
                f"(현재 {pnl_rate:+.1f}%, 전량 기준 {full_exit_threshold:+.1f}%)"
            ),
        )

    size_pct = partial_stop_loss_size_pct(settings, resolved_horizon)
    partial_qty = int(quantity * size_pct / 100.0)
    partial_qty = min(max(partial_qty, 1), quantity - 1)
    if partial_qty <= 0:
        return StagedStopLossDecision("full")

    return StagedStopLossDecision(
        "partial",
        quantity=partial_qty,
        reason=(
            f"{resolved_horizon} 1차 손실축소 "
            f"({pnl_rate:+.1f}% <= {default_stop_loss_pct:+.1f}%, "
            f"{partial_qty}/{quantity}주)"
        ),
    )


def strategic_exit_min_hold_block_reason(
    tr: Any,
    *,
    settings: Any,
    horizon: str | None = None,
    exit_scope: str = "profit",
    observed_at: datetime | None = None,
) -> str | None:
    resolved_horizon = str(horizon or trade_horizon_from_result(tr)).upper()
    if exit_scope == "review":
        minimum = min_hold_minutes_for_review_exit(settings, resolved_horizon)
        label = "전략 리뷰 매도"
    else:
        minimum = min_hold_minutes_for_profit_exit(settings, resolved_horizon)
        label = "수익보호 매도"

    if minimum <= 0:
        return None

    age = position_age_minutes(tr, observed_at=observed_at)
    if age is None or age >= minimum:
        return None

    return (
        f"{resolved_horizon} 최소 보유 {minimum}분 전 {label} 보류 "
        f"(현재 {age:.0f}분)"
    )


def soft_loss_stop_min_hold_block_reason(
    tr: Any,
    *,
    settings: Any,
    horizon: str | None = None,
    pnl_rate: float,
    default_stop_loss_pct: float,
    observed_at: datetime | None = None,
) -> str | None:
    """Block tight active stops early, while preserving the horizon default hard stop."""
    if pnl_rate <= default_stop_loss_pct:
        return None

    resolved_horizon = str(horizon or trade_horizon_from_result(tr)).upper()
    minimum = min_hold_minutes_for_soft_stop_exit(settings, resolved_horizon)
    if minimum <= 0:
        return None

    age = position_age_minutes(tr, observed_at=observed_at)
    if age is None or age >= minimum:
        return None

    return (
        f"{resolved_horizon} 최소 보유 {minimum}분 전 소프트 손절 보류 "
        f"(현재 {age:.0f}분, 손익 {pnl_rate:+.1f}% > 기본 손절 {default_stop_loss_pct:+.1f}%)"
    )
