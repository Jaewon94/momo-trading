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

        sell_prefixes = (
            "TradeResult 없음",
            "매입가 정보 없음",
            "손실 과대",
            "보유 ",
            "AI 신뢰도",
            "목표가 도달",
        )
        if action == "SELL" and reason.startswith(sell_prefixes):
            return HoldingsPrecheckDecision(
                should_skip_llm=True,
                action="SELL",
                reason=reason,
                source="HOLDING_POLICY",
            )

        return HoldingsPrecheckDecision(
            should_skip_llm=False,
            action=action,
            reason=reason,
            source="HOLDING_POLICY",
        )


holdings_precheck_service = HoldingsPrecheckService()
