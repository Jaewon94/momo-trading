"""Shared position-exit policy helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from strategy.trade_horizon import TradeHorizon


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


def min_hold_minutes_for_profit_exit(settings: Any, horizon: str) -> int:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.SHORT:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_SHORT", 15) or 0), 0)
    if key == TradeHorizon.LONG:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_LONG", 390) or 0), 0)
    return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_PROFIT_EXIT_MID", 180) or 0), 0)


def min_hold_minutes_for_review_exit(settings: Any, horizon: str) -> int:
    key = str(horizon or TradeHorizon.MID).upper()
    if key == TradeHorizon.SHORT:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_SHORT", 15) or 0), 0)
    if key == TradeHorizon.LONG:
        return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_LONG", 390) or 0), 0)
    return max(int(getattr(settings, "MIN_HOLD_MINUTES_BEFORE_REVIEW_EXIT_MID", 120) or 0), 0)


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
