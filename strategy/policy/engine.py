"""Behavior-preserving facade for trading policy gate evaluations."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal
from core.order_submission import decide_order_submission
from core.post_liquidation_guard import POST_LIQUIDATION_BUY_BLOCK_REASON
from services.deterministic_final_gate_service import deterministic_final_gate_service
from services.deterministic_tier1_fast_gate_service import deterministic_tier1_fast_gate_service
from services.news_gate_rollout_service import news_gate_rollout_service
from services.news_signal_service import news_signal_service
from services.pre_analysis_gate_service import pre_analysis_gate_service
from strategy.exposure_policy import resolve_aggressive_exposure_alignment
from strategy.policy.trace import (
    from_cost_gate,
    from_exit_event,
    from_exposure_alignment,
    from_final_gate,
    from_news_gate,
    from_order_block,
    from_order_submission,
    from_pre_analysis_gate,
    from_risk_result,
    from_tier1_fast_gate,
)
from strategy.policy.types import PolicyDecision
from strategy.risk_manager import risk_manager
from strategy.signal import TradeSignal
from strategy.trade_horizon import TradeHorizon
from trading.enums import OrderSide, SignalAction


@dataclass(frozen=True)
class PolicyEvaluation:
    """Existing policy result plus shared trace decision metadata."""

    stage: str
    value: Any
    decision: PolicyDecision | None = None


class TradingPolicyEngine:
    """Central policy facade.

    Phase 2 intentionally preserves existing behavior: it delegates to the same
    services and helpers that callers used before, then returns the same result
    object together with a typed `PolicyDecision`.
    """

    def __init__(
        self,
        *,
        pre_gate_service: Any = pre_analysis_gate_service,
        fast_gate_service: Any = deterministic_tier1_fast_gate_service,
        final_gate_service: Any = deterministic_final_gate_service,
        news_rollout_service: Any = news_gate_rollout_service,
        news_service: Any = news_signal_service,
        session_factory: Callable[[], Any] = AsyncSessionLocal,
        exposure_alignment_resolver: Callable[..., Any] = resolve_aggressive_exposure_alignment,
        risk_manager_service: Any = risk_manager,
        order_submission_decider: Callable[[Any], Any] = decide_order_submission,
    ) -> None:
        self._pre_gate_service = pre_gate_service
        self._fast_gate_service = fast_gate_service
        self._final_gate_service = final_gate_service
        self._news_rollout_service = news_rollout_service
        self._news_service = news_service
        self._session_factory = session_factory
        self._exposure_alignment_resolver = exposure_alignment_resolver
        self._risk_manager = risk_manager_service
        self._order_submission_decider = order_submission_decider

    def evaluate_pre_analysis_gate(self, **kwargs: Any) -> PolicyEvaluation:
        gate = self._pre_gate_service.evaluate(**kwargs)
        return PolicyEvaluation(
            stage="PRE_ANALYSIS_GATE",
            value=gate,
            decision=from_pre_analysis_gate(gate),
        )

    def evaluate_tier1_fast_gate(self, *, mode: str, **kwargs: Any) -> PolicyEvaluation:
        gate = self._fast_gate_service.evaluate(**kwargs)
        return PolicyEvaluation(
            stage="DETERMINISTIC_TIER1_FAST_GATE",
            value=gate,
            decision=from_tier1_fast_gate(gate, mode=mode),
        )

    def decision_from_tier1_fast_gate(self, gate: Any, *, mode: str) -> PolicyDecision:
        return from_tier1_fast_gate(gate, mode=mode)

    def evaluate_final_gate(self, **kwargs: Any) -> PolicyEvaluation:
        gate = self._final_gate_service.evaluate(**kwargs)
        return PolicyEvaluation(
            stage="DETERMINISTIC_FINAL_GATE",
            value=gate,
            decision=from_final_gate(gate),
        )

    def evaluate_tier1_cost_gate(
        self,
        *,
        analysis: dict,
        current_price: float,
        horizon: str | None = None,
    ) -> PolicyEvaluation:
        result = self.evaluate_tier1_cost_gate_payload(
            analysis=analysis,
            current_price=current_price,
            horizon=horizon,
        )
        return PolicyEvaluation(
            stage="TIER1_COST_GATE",
            value=result,
            decision=from_cost_gate(
                result,
                owner="tier1_cost_gate",
                reason_code="LOW_EDGE_AFTER_COST",
            ),
        )

    def evaluate_cost_gate(
        self,
        *,
        signal: TradeSignal,
        current_price: float,
        horizon: str | None = None,
    ) -> PolicyEvaluation:
        result = self.evaluate_cost_gate_payload(
            signal=signal,
            current_price=current_price,
            horizon=horizon,
        )
        return PolicyEvaluation(
            stage="COST_GATE",
            value=result,
            decision=from_cost_gate(result, owner="cost_gate"),
        )

    async def evaluate_news_gate(self, *, symbol: str, horizon: str | None = None) -> PolicyEvaluation:
        result = await self.evaluate_news_gate_payload(symbol=symbol, horizon=horizon)
        return PolicyEvaluation(
            stage="NEWS_GATE",
            value=result,
            decision=from_news_gate(result),
        )

    def evaluate_exposure_alignment(
        self,
        *,
        signal: TradeSignal,
        portfolio_snapshot: dict | None,
        dynamic_limits: dict | None,
        market_regime: str,
    ) -> PolicyEvaluation:
        decision = self._exposure_alignment_resolver(
            enabled=bool(getattr(settings, "AGGRESSIVE_EXPOSURE_ALIGNMENT_ENABLED", True)),
            risk_appetite=str(getattr(settings, "RISK_APPETITE", "MODERATE") or "MODERATE"),
            market_regime=market_regime,
            action=signal.action,
            confidence=float(signal.confidence or signal.strength or 0.0),
            min_confidence=float(getattr(settings, "AGGRESSIVE_EXPOSURE_MIN_CONFIDENCE", 0.65) or 0.0),
            price=float(signal.suggested_price or 0.0),
            quantity=int(signal.suggested_quantity or 0),
            portfolio_snapshot=portfolio_snapshot,
            dynamic_limits=dynamic_limits,
            target_exposure_pct=float(getattr(settings, "AGGRESSIVE_TARGET_EXPOSURE_PCT", 25.0) or 0.0),
            min_order_krw=float(getattr(settings, "AGGRESSIVE_MIN_BUY_ORDER_KRW", 0) or 0.0),
        )
        return PolicyEvaluation(
            stage="AGGRESSIVE_EXPOSURE_ALIGNMENT",
            value=decision,
            decision=from_exposure_alignment(decision),
        )

    async def evaluate_risk_manager(
        self,
        *,
        input_quantity: int | None = None,
        **kwargs: Any,
    ) -> PolicyEvaluation:
        result = await self._risk_manager.check(**kwargs)
        return PolicyEvaluation(
            stage="RISK_MANAGER",
            value=result,
            decision=from_risk_result(result, input_quantity=input_quantity),
        )

    def evaluate_order_submission(self, side: Any) -> PolicyEvaluation:
        decision = self._order_submission_decider(side)
        return PolicyEvaluation(
            stage="ORDER_SUBMISSION",
            value=decision,
            decision=from_order_submission(decision, side=getattr(side, "value", side)),
        )

    def evaluate_post_liquidation_buy_block(
        self,
        *,
        side: Any,
        is_blocked: Callable[[], bool],
    ) -> PolicyEvaluation | None:
        side_value = str(getattr(side, "value", side) or "").upper()
        if side_value != OrderSide.BUY.value or not is_blocked():
            return None
        block_msg = "장마감 청산 이후 자동 BUY 차단"
        return PolicyEvaluation(
            stage="POST_LIQUIDATION_BUY_BLOCK",
            value={
                "blocked": True,
                "message": block_msg,
                "reason_code": POST_LIQUIDATION_BUY_BLOCK_REASON,
            },
            decision=from_order_block(
                reason_code=POST_LIQUIDATION_BUY_BLOCK_REASON,
                reason=block_msg,
                side=side_value,
            ),
        )

    def evaluate_order_block(
        self,
        *,
        reason_code: str,
        reason: str,
        side: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyEvaluation:
        return PolicyEvaluation(
            stage="ORDER_BLOCK",
            value={"reason_code": reason_code, "reason": reason, **(metadata or {})},
            decision=from_order_block(
                reason_code=reason_code,
                reason=reason,
                side=getattr(side, "value", side),
                metadata=metadata,
            ),
        )

    def evaluate_exit_event(self, **kwargs: Any) -> PolicyEvaluation:
        return PolicyEvaluation(
            stage="HOLDING_EXIT",
            value=dict(kwargs),
            decision=from_exit_event(**kwargs),
        )

    async def evaluate_news_gate_payload(self, *, symbol: str, horizon: str | None = None) -> dict:
        rollout = await self._news_rollout_service.resolve()
        if not rollout.evaluate_gate:
            return {
                "approved": True,
                "reason": rollout.reason,
                "negative_pressure": 0.0,
                "negative_count": 0,
                "news_gate_rollout": {
                    "requested_mode": rollout.requested_mode,
                    "effective_mode": rollout.effective_mode,
                    "block_buy": rollout.block_buy,
                },
            }

        try:
            async with self._session_factory() as session:
                result = await self._news_service.evaluate_gate(
                    session,
                    symbol=symbol,
                    horizon=horizon,
                )
                result["blocking_enabled"] = rollout.block_buy
                result["news_gate_rollout"] = {
                    "requested_mode": rollout.requested_mode,
                    "effective_mode": rollout.effective_mode,
                    "block_buy": rollout.block_buy,
                    "reason": rollout.reason,
                    **rollout.detail,
                }
                return result
        except Exception as exc:
            logger.warning("[{}] 뉴스 게이트 평가 실패, 보수적 통과: {}", symbol, str(exc))
            return {
                "approved": True,
                "reason": f"뉴스 게이트 평가 실패: {str(exc)[:80]}",
                "negative_pressure": 0.0,
                "negative_count": 0,
            }

    @staticmethod
    def evaluate_tier1_cost_gate_payload(
        *,
        analysis: dict,
        current_price: float,
        horizon: str | None = None,
    ) -> dict:
        if str(analysis.get("recommendation", "") or "").upper() != "BUY":
            return {"approved": True, "reason": "BUY 추천 아님", "stage": "TIER1_COST_GATE"}
        signal = TradeSignal(
            symbol="",
            stock_id="",
            action=SignalAction.BUY,
            strength=float(analysis.get("confidence", 0.0) or 0.0),
            suggested_price=float(current_price or 0.0),
            suggested_quantity=1,
            target_price=float(analysis.get("target_price", 0.0) or 0.0),
            confidence=float(analysis.get("confidence", 0.0) or 0.0),
        )
        result = TradingPolicyEngine.evaluate_cost_gate_payload(
            signal=signal,
            current_price=current_price,
            horizon=horizon,
        )
        return {"stage": "TIER1_COST_GATE", **result}

    @staticmethod
    def evaluate_cost_gate_payload(
        *,
        signal: TradeSignal,
        current_price: float,
        horizon: str | None = None,
    ) -> dict:
        if not settings.COST_GATE_ENABLED or signal.action != SignalAction.BUY:
            return {"approved": True, "reason": "비용 게이트 비활성화"}

        entry_price = float(signal.suggested_price or current_price or 0.0)
        target_price = float(signal.target_price or 0.0)
        if entry_price <= 0 or target_price <= entry_price:
            return {"approved": True, "reason": "엣지 계산 불가(보수적 통과)"}

        horizon_key = str(horizon or TradeHorizon.MID).upper()
        slippage_bps = {
            TradeHorizon.SHORT: int(settings.ESTIMATED_SLIPPAGE_BPS_SHORT or 0),
            TradeHorizon.MID: int(settings.ESTIMATED_SLIPPAGE_BPS_MID or 0),
            TradeHorizon.LONG: int(settings.ESTIMATED_SLIPPAGE_BPS_LONG or 0),
        }.get(horizon_key, int(settings.ESTIMATED_SLIPPAGE_BPS_MID or 0))
        min_ratio = {
            TradeHorizon.SHORT: float(settings.MIN_EDGE_TO_COST_RATIO_SHORT or 1.0),
            TradeHorizon.MID: float(settings.MIN_EDGE_TO_COST_RATIO_MID or 1.0),
            TradeHorizon.LONG: float(settings.MIN_EDGE_TO_COST_RATIO_LONG or 1.0),
        }.get(horizon_key, float(settings.MIN_EDGE_TO_COST_RATIO_MID or 1.0))

        total_cost_bps = (
            int(settings.ESTIMATED_ENTRY_COST_BPS or 0)
            + int(settings.ESTIMATED_EXIT_COST_BPS or 0)
            + slippage_bps
        )
        edge_bps = ((target_price - entry_price) / entry_price) * 10000

        approved = edge_bps >= (total_cost_bps * min_ratio)
        return {
            "approved": approved,
            "reason": (
                f"엣지 {edge_bps:.1f}bp < 비용×배수 {total_cost_bps * min_ratio:.1f}bp"
                if not approved else
                f"엣지 {edge_bps:.1f}bp >= 비용×배수 {total_cost_bps * min_ratio:.1f}bp"
            ),
            "edge_bps": edge_bps,
            "cost_bps": total_cost_bps,
            "edge_to_cost_ratio": (edge_bps / total_cost_bps) if total_cost_bps > 0 else None,
            "min_ratio": min_ratio,
            "horizon": horizon_key,
        }
