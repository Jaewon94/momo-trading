"""Utilities for preserving TradeResult notes across pending confirmation states."""
from __future__ import annotations


_PARTIAL_PREFIX = "PENDING_CONFIRM_PARTIAL:"
_PENDING_MARKERS = ("PENDING_CONFIRM",)


def with_pending_partial_note(
    notes: object,
    *,
    filled_qty: int,
    remaining_qty: int,
    filled_price: float | None = None,
) -> str:
    base = _without_pending_markers(notes)
    partial = f"{_PARTIAL_PREFIX} filled_qty={int(filled_qty or 0)}, remaining_qty={int(remaining_qty or 0)}"
    if filled_price is not None:
        partial += f", filled_price={float(filled_price or 0.0):.2f}"
    return f"{base} | {partial}" if base else partial


def confirmed_notes(notes: object) -> str | None:
    base = _without_pending_markers(notes)
    return base or None


def _without_pending_markers(notes: object) -> str:
    text = str(notes or "").strip()
    if not text:
        return ""
    kept: list[str] = []
    for part in (item.strip() for item in text.split(" | ")):
        if not part:
            continue
        if part.startswith(_PARTIAL_PREFIX):
            continue
        if part in _PENDING_MARKERS:
            continue
        kept.append(part)
    return " | ".join(kept)
