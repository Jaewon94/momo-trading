"""Fee models for backtesting."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FeeBreakdown:
    side: str
    notional: float
    commission: float
    tax: float
    cash_delta: float


@dataclass(frozen=True)
class KoreaStockFeeModel:
    """KRX-style configurable commission and sell-side transaction tax model."""

    commission_rate_pct: float = 0.015
    sell_tax_rate_pct: float = 0.0

    def calculate(self, *, side: str, price: float, quantity: int) -> FeeBreakdown:
        normalized_side = side.upper()
        notional = float(price) * int(quantity)
        commission = notional * (self.commission_rate_pct / 100)
        tax = notional * (self.sell_tax_rate_pct / 100) if normalized_side == "SELL" else 0.0
        if normalized_side == "BUY":
            cash_delta = -(notional + commission)
        else:
            cash_delta = notional - commission - tax
        return FeeBreakdown(
            side=normalized_side,
            notional=round(notional, 2),
            commission=round(commission, 2),
            tax=round(tax, 2),
            cash_delta=round(cash_delta, 2),
        )

    def metadata(self) -> dict:
        return {
            "name": "KOREA_STOCK_FEE_MODEL",
            "commission_rate_pct": self.commission_rate_pct,
            "sell_tax_rate_pct": self.sell_tax_rate_pct,
        }
