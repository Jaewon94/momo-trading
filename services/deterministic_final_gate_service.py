"""Deterministic gate before Tier2 review."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.config import settings
from strategy.risk_manager import risk_manager
from trading.symbols import normalize_krx_symbol


@dataclass
class DeterministicFinalGateDecision:
    approved: bool
    code: str
    reason: str
    detail: dict = field(default_factory=dict)


class DeterministicFinalGateService:
    def evaluate(
        self,
        *,
        symbol: str,
        strategy_type: str,
        analysis: dict,
        current_price: float,
        market_regime: str,
        portfolio_snapshot: dict | None,
        dynamic_limits: dict | None,
        active_rules: dict | None,
        buying_power: dict | None,
    ) -> DeterministicFinalGateDecision:
        active_rules = active_rules or {}
        param_overrides = active_rules.get("param_overrides", {})
        validation_flags = active_rules.get("validation_flags", {})

        recommendation = str(analysis.get("recommendation", "") or "").upper()
        tier1_confidence = float(analysis.get("confidence", 0.0) or 0.0)
        holding_symbols = [
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        ]
        is_sell_or_holding = (
            recommendation == "SELL" or normalize_krx_symbol(symbol) in holding_symbols
        )

        rule_min_conf = None
        for scope in [strategy_type, "ALL"]:
            val = param_overrides.get(scope, {}).get("min_confidence")
            if val is not None and (rule_min_conf is None or val > rule_min_conf):
                rule_min_conf = val

        if rule_min_conf and not is_sell_or_holding:
            regime_adj = {"BULL": -0.05, "THEME": -0.03, "SIDEWAYS": 0.0, "BEAR": 0.03}
            adj = regime_adj.get(str(market_regime or "").upper(), 0.0)
            effective_min_conf = max(0.50, min(0.85, float(rule_min_conf) + adj))
            if tier1_confidence < effective_min_conf:
                return DeterministicFinalGateDecision(
                    approved=False,
                    code="CONFIDENCE_GATE",
                    reason=f"신뢰도 {tier1_confidence:.0%} < 실효 최소 {effective_min_conf:.0%}",
                    detail={
                        "confidence": tier1_confidence,
                        "effective_min_confidence": effective_min_conf,
                        "rule_min_confidence": float(rule_min_conf),
                        "market_regime": str(market_regime or "").upper(),
                    },
                )

        if validation_flags.get("revalidate_rr_ratio"):
            target_price = float(analysis.get("target_price") or 0.0)
            stop_loss_price = float(analysis.get("stop_loss_price") or 0.0)
            if current_price > 0 and target_price > 0 and stop_loss_price > 0:
                code_reward = abs(target_price - current_price)
                code_risk = abs(current_price - stop_loss_price)
                if code_risk > 0:
                    code_rr = code_reward / code_risk
                    rr_overrides = active_rules.get("rr_floor_overrides", {})
                    min_rr = float(
                        rr_overrides.get(
                            str(market_regime or "").upper(),
                            risk_manager.RR_FLOOR.get(str(market_regime or "").upper(), 1.2),
                        )
                    )
                    if code_rr < min_rr:
                        return DeterministicFinalGateDecision(
                            approved=False,
                            code="RR_RATIO_GATE",
                            reason=f"코드 계산 RR {code_rr:.2f}:1 < 최소 {min_rr}:1",
                            detail={
                                "code_rr": code_rr,
                                "min_rr": min_rr,
                                "target_price": target_price,
                                "stop_loss_price": stop_loss_price,
                                "current_price": current_price,
                            },
                        )
                elif recommendation == "BUY":
                    return DeterministicFinalGateDecision(
                        approved=False,
                        code="RR_UNDEFINED_GATE",
                        reason="손절가가 현재가와 같아 RR 계산 불가",
                        detail={
                            "target_price": target_price,
                            "stop_loss_price": stop_loss_price,
                            "current_price": current_price,
                        },
                    )

        if validation_flags.get("require_stop_loss_logging") and recommendation == "BUY":
            stop_loss_price = float(analysis.get("stop_loss_price") or 0.0)
            if stop_loss_price <= 0:
                return DeterministicFinalGateDecision(
                    approved=False,
                    code="STOP_LOSS_REQUIRED_GATE",
                    reason="손절가 미설정",
                )

        if recommendation == "BUY":
            min_buy_qty = (
                dynamic_limits.get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
                if dynamic_limits else settings.MIN_BUY_QUANTITY
            )
            if buying_power and buying_power.get("success") and int(buying_power.get("max_qty", 0) or 0) < min_buy_qty:
                return DeterministicFinalGateDecision(
                    approved=False,
                    code="BUYING_POWER_GATE",
                    reason=f"매수가능수량 부족 ({int(buying_power.get('max_qty', 0) or 0)}주 < 최소 {min_buy_qty}주)",
                    detail={
                        "max_qty": int(buying_power.get("max_qty", 0) or 0),
                        "min_buy_quantity": min_buy_qty,
                    },
                )

        return DeterministicFinalGateDecision(
            approved=True,
            code="APPROVED",
            reason="Tier2 검토 진행 가능",
        )


deterministic_final_gate_service = DeterministicFinalGateService()
