"""Exposure alignment helpers for risk-appetite-aware buy sizing."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Any

from trading.enums import SignalAction


@dataclass(frozen=True)
class ExposureAlignmentDecision:
    applied: bool
    reason: str
    initial_quantity: int
    final_quantity: int
    initial_notional: float
    final_notional: float
    current_exposure_pct: float
    target_exposure_pct: float
    min_order_krw: float
    cap_order_krw: float

    @property
    def quantity_delta(self) -> int:
        return int(self.final_quantity - self.initial_quantity)


def resolve_aggressive_exposure_alignment(
    *,
    enabled: bool,
    risk_appetite: str,
    market_regime: str,
    action: SignalAction | str,
    confidence: float,
    min_confidence: float,
    price: float,
    quantity: int,
    portfolio_snapshot: dict[str, Any] | None,
    dynamic_limits: dict[str, Any] | None,
    target_exposure_pct: float,
    min_order_krw: float,
) -> ExposureAlignmentDecision:
    """Return a quantity floor for AGGRESSIVE mode without bypassing hard gates.

    The helper only raises an already-approved BUY quantity. Risk manager,
    broker buying-power checks, and order submission gates still run after this.
    """
    snapshot = portfolio_snapshot or {}
    limits = dynamic_limits or {}
    quantity = max(int(quantity or 0), 0)
    price = float(price or 0.0)
    total_asset = float(snapshot.get("total_asset") or 0.0)
    cash = float(snapshot.get("cash") or 0.0)
    current_exposure_pct = _current_exposure_pct(snapshot)
    target_exposure_pct = max(float(target_exposure_pct or 0.0), 0.0)
    min_order_krw = max(float(min_order_krw or 0.0), 0.0)
    initial_notional = price * quantity

    def decision(applied: bool, reason: str, final_quantity: int = quantity) -> ExposureAlignmentDecision:
        final_quantity = max(int(final_quantity or 0), 0)
        return ExposureAlignmentDecision(
            applied=applied,
            reason=reason,
            initial_quantity=quantity,
            final_quantity=final_quantity,
            initial_notional=initial_notional,
            final_notional=price * final_quantity,
            current_exposure_pct=current_exposure_pct,
            target_exposure_pct=target_exposure_pct,
            min_order_krw=min_order_krw,
            cap_order_krw=_cap_order_krw(
                total_asset=total_asset,
                cash=cash,
                current_exposure_pct=current_exposure_pct,
                target_exposure_pct=target_exposure_pct,
                dynamic_limits=limits,
            ),
        )

    if not enabled:
        return decision(False, "disabled")
    if str(risk_appetite or "").upper() != "AGGRESSIVE":
        return decision(False, "risk_appetite_not_aggressive")
    if str(market_regime or "").upper() not in {"BULL", "THEME"}:
        return decision(False, "market_regime_not_bullish")
    action_value = action.value if hasattr(action, "value") else str(action or "").upper()
    if action_value != SignalAction.BUY.value:
        return decision(False, "not_buy")
    if price <= 0 or total_asset <= 0 or cash <= 0:
        return decision(False, "missing_price_or_account")
    if confidence < float(min_confidence or 0.0):
        return decision(False, "confidence_below_floor")
    if target_exposure_pct <= 0 or current_exposure_pct >= target_exposure_pct:
        return decision(False, "target_exposure_reached")

    cap_order_krw = _cap_order_krw(
        total_asset=total_asset,
        cash=cash,
        current_exposure_pct=current_exposure_pct,
        target_exposure_pct=target_exposure_pct,
        dynamic_limits=limits,
    )
    if cap_order_krw <= initial_notional:
        return decision(False, "existing_quantity_at_or_above_cap")

    desired_notional = min(max(initial_notional, min_order_krw), cap_order_krw)
    if desired_notional <= initial_notional:
        return decision(False, "existing_quantity_at_or_above_floor")

    desired_qty = ceil(desired_notional / price)
    cap_qty = floor(cap_order_krw / price)
    final_qty = min(max(quantity, desired_qty), cap_qty)
    if final_qty <= quantity:
        return decision(False, "floor_below_one_share_or_cap")

    return decision(True, "aggressive_exposure_floor", final_qty)


def _current_exposure_pct(snapshot: dict[str, Any]) -> float:
    explicit = snapshot.get("current_exposure_pct")
    if explicit is not None:
        return max(float(explicit or 0.0), 0.0)

    total_asset = float(snapshot.get("total_asset") or 0.0)
    if total_asset <= 0:
        return 0.0
    stock_value = snapshot.get("stock_value")
    if stock_value is None:
        cash = float(snapshot.get("cash") or 0.0)
        stock_value = max(total_asset - cash, 0.0)
    return max(float(stock_value or 0.0) / total_asset * 100.0, 0.0)


def _cap_order_krw(
    *,
    total_asset: float,
    cash: float,
    current_exposure_pct: float,
    target_exposure_pct: float,
    dynamic_limits: dict[str, Any],
) -> float:
    caps = [max(cash, 0.0)]

    max_order = float(dynamic_limits.get("max_single_order_krw") or 0.0)
    if max_order > 0:
        caps.append(max_order)

    max_position_pct = float(dynamic_limits.get("max_position_pct") or 0.0)
    if total_asset > 0 and max_position_pct > 0:
        caps.append(total_asset * max_position_pct / 100.0)

    exposure_gap_pct = max(float(target_exposure_pct) - float(current_exposure_pct), 0.0)
    if total_asset > 0 and exposure_gap_pct > 0:
        caps.append(total_asset * exposure_gap_pct / 100.0)

    return max(min(caps), 0.0)
