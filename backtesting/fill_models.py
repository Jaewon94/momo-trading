"""Fill models for backtesting."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FillResult:
    filled: bool
    price: float = 0.0
    quantity: int = 0
    reason: str = "FILLED"


@dataclass(frozen=True)
class NextBarOHLCFillModel:
    """Market fill model using the selected OHLC reference price plus slippage."""

    slippage_rate_pct: float = 0.05

    def fill_market_order(
        self,
        *,
        side: str,
        requested_quantity: int,
        reference_price: float,
        bar: Any | None = None,
    ) -> FillResult:
        if requested_quantity <= 0 or reference_price <= 0:
            return FillResult(filled=False, reason="INVALID_ORDER")

        direction = 1 if side.upper() == "BUY" else -1
        price = float(reference_price) * (1 + direction * self.slippage_rate_pct / 100)
        return FillResult(
            filled=True,
            price=round(price, 4),
            quantity=int(requested_quantity),
        )

    def metadata(self) -> dict:
        return {
            "name": "NEXT_BAR_OHLC",
            "slippage_rate_pct": self.slippage_rate_pct,
        }


@dataclass(frozen=True)
class LimitGuardFillModel:
    """Adds halt and limit-lock guards before delegating to a base fill model."""

    base_model: NextBarOHLCFillModel

    def fill_market_order(
        self,
        *,
        side: str,
        requested_quantity: int,
        reference_price: float,
        bar: Any | None = None,
    ) -> FillResult:
        guard_reason = self._guard_reason(side=side, bar=bar)
        if guard_reason:
            return FillResult(filled=False, reason=guard_reason)
        return self.base_model.fill_market_order(
            side=side,
            requested_quantity=requested_quantity,
            reference_price=reference_price,
            bar=bar,
        )

    def metadata(self) -> dict:
        return {
            "name": "LIMIT_GUARDED_NEXT_BAR_OHLC",
            "slippage_rate_pct": self.base_model.slippage_rate_pct,
            "guards": ["HALTED_OR_ZERO_VOLUME", "UPPER_LIMIT_LOCKED", "LOWER_LIMIT_LOCKED"],
        }

    @staticmethod
    def _guard_reason(*, side: str, bar: Any | None) -> str | None:
        if bar is None:
            return None
        volume = _bar_value(bar, "volume")
        if volume is not None and float(volume) <= 0:
            return "HALTED_OR_ZERO_VOLUME"

        high = _bar_value(bar, "high")
        low = _bar_value(bar, "low")
        upper_limit = _bar_value(bar, "upper_limit")
        lower_limit = _bar_value(bar, "lower_limit")
        normalized_side = side.upper()

        if normalized_side == "BUY" and upper_limit is not None and high is not None:
            if float(high) >= float(upper_limit) and _flat_bar(bar):
                return "UPPER_LIMIT_LOCKED"
        if normalized_side == "SELL" and lower_limit is not None and low is not None:
            if float(low) <= float(lower_limit) and _flat_bar(bar):
                return "LOWER_LIMIT_LOCKED"
        return None


def _bar_value(bar: Any, key: str) -> Any:
    if isinstance(bar, dict):
        return bar.get(key)
    getter = getattr(bar, "get", None)
    if callable(getter):
        return getter(key)
    return getattr(bar, key, None)


def _flat_bar(bar: Any) -> bool:
    high = _bar_value(bar, "high")
    low = _bar_value(bar, "low")
    return high is not None and low is not None and float(high) == float(low)
