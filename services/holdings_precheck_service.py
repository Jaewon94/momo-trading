"""Deterministic precheck for holdings review/liquidation before LLM."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from strategy.holding_policy import evaluate_overnight_hold


@dataclass
class HoldingsPrecheckDecision:
    should_skip_llm: bool
    action: str
    reason: str
    source: str


class HoldingsPrecheckService:
    def evaluate(
        self,
        *,
        holding,
        trade_result,
        current_price: float,
        settings,
    ) -> HoldingsPrecheckDecision:
        try:
            fallback = evaluate_overnight_hold(holding, trade_result, current_price, settings)
            reason = str(fallback.reason or "")
            action = str(fallback.action or "HOLD").upper()
        except Exception as exc:
            logger.debug("holdings precheck skipped due to evaluation error: {}", str(exc))
            return HoldingsPrecheckDecision(
                should_skip_llm=False,
                action="HOLD",
                reason=f"precheck_unavailable:{str(exc)[:60]}",
                source="HOLDING_POLICY",
            )

        emergency_sell_prefixes = (
            "TradeResult 없음",
            "매입가 정보 없음",
        )
        if action == "SELL" and reason.startswith(emergency_sell_prefixes):
            return HoldingsPrecheckDecision(
                should_skip_llm=True,
                action="SELL",
                reason=reason,
                source="HOLDING_POLICY",
            )

        if action == "HOLD" and self._is_clear_hold(
            holding=holding,
            trade_result=trade_result,
            current_price=current_price,
            settings=settings,
        ):
            return HoldingsPrecheckDecision(
                should_skip_llm=True,
                action="HOLD",
                reason=f"{reason} — 명확한 HOLD 사전판단",
                source="HOLDING_POLICY",
            )

        return HoldingsPrecheckDecision(
            should_skip_llm=False,
            action=action,
            reason=reason,
            source="HOLDING_POLICY",
        )

    def _is_clear_hold(
        self,
        *,
        holding,
        trade_result,
        current_price: float,
        settings,
    ) -> bool:
        if not bool(getattr(settings, "HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED", False)):
            return False
        if trade_result is None:
            return False

        avg_price = float(getattr(holding, "avg_buy_price", 0.0) or 0.0)
        if avg_price <= 0 or current_price <= 0:
            return False

        pnl_rate = (float(current_price) - avg_price) / avg_price * 100
        if pnl_rate < 0:
            return False

        confidence = float(getattr(trade_result, "ai_confidence", 0.0) or 0.0)
        if confidence < 0.65:
            return False

        target_price = float(getattr(trade_result, "ai_target_price", 0.0) or 0.0)
        if target_price > 0:
            target_gap_pct = (target_price - float(current_price)) / float(current_price) * 100
            if target_gap_pct < 1.0:
                return False

        from strategy.holding_policy import _calc_hold_days, _get_max_hold_days

        hold_days = _calc_hold_days(trade_result)
        max_days = _get_max_hold_days(str(getattr(trade_result, "strategy_type", "")), settings)
        return hold_days < max(max_days - 1, 0)


holdings_precheck_service = HoldingsPrecheckService()
