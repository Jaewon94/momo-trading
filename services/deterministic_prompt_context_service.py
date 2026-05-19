"""Formatter for deterministic pre-AI trading context."""
from __future__ import annotations

from typing import Any

from analysis.chart_analyzer import ChartAnalysisResult
from core.config import settings
from strategy.risk_manager import risk_manager
from trading.symbols import normalize_krx_symbol


class DeterministicPromptContextService:
    def build_tier1_context(
        self,
        *,
        symbol: str,
        strategy_type: str,
        current_price: float,
        chart_result: ChartAnalysisResult,
        portfolio_snapshot: dict | None,
        market_regime: str,
        dynamic_limits: dict | None = None,
    ) -> str:
        holding_symbols = [
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        ]
        is_holding = normalize_krx_symbol(symbol) in holding_symbols
        available_cash = float((portfolio_snapshot or {}).get("cash", 0.0) or 0.0)
        min_buy_quantity = (
            dynamic_limits.get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
            if dynamic_limits else settings.MIN_BUY_QUANTITY
        )
        min_buy_cost = float(current_price or 0.0) * float(min_buy_quantity or 0)
        signal = chart_result.signal_summary or {}
        direction = str(signal.get("direction", "UNKNOWN") or "UNKNOWN").upper()
        confidence = float(signal.get("confidence", 0.0) or 0.0)
        lines = [
            f"- deterministic_stage: TIER1_PRECHECK",
            f"- strategy_type: {strategy_type}",
            "- strategy_semantics: STABLE_SHORT/AGGRESSIVE_SHORT are legacy execution/risk profile names, not target holding horizons.",
            "- horizon_policy: Prefer MID/LONG decisions; SHORT is only for rare, high-confidence tactical momentum exceptions.",
            "- allowed_scan_action: For non-held KRX cash equities, evaluate BUY or HOLD only; SELL only applies to already-held positions.",
            f"- market_regime: {str(market_regime or 'UNKNOWN').upper()}",
            f"- is_holding: {is_holding}",
            f"- min_buy_quantity: {min_buy_quantity}",
            f"- min_buy_cost: {min_buy_cost:,.0f}원",
            f"- available_cash: {available_cash:,.0f}원",
            f"- chart_signal: {direction} / confidence {confidence:.0%}",
        ]
        return "\n".join(lines)

    def build_tier2_context(
        self,
        *,
        symbol: str,
        strategy_type: str,
        current_price: float,
        tier1_analysis: dict,
        portfolio_snapshot: dict | None,
        market_regime: str,
        dynamic_limits: dict | None = None,
        active_rules: dict | None = None,
        buying_power: dict | None = None,
    ) -> str:
        active_rules = active_rules or {}
        validation_flags = active_rules.get("validation_flags", {})
        recommendation = str(tier1_analysis.get("recommendation", "UNKNOWN") or "UNKNOWN").upper()
        target_price = self._to_float(tier1_analysis.get("target_price"))
        stop_loss_price = self._to_float(tier1_analysis.get("stop_loss_price"))
        rr_ratio = self._rr_ratio(current_price, target_price, stop_loss_price)
        min_rr = float(
            (active_rules.get("rr_floor_overrides") or {}).get(
                str(market_regime or "").upper(),
                risk_manager.RR_FLOOR.get(str(market_regime or "").upper(), 1.2),
            )
        )
        min_buy_quantity = (
            dynamic_limits.get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
            if dynamic_limits else settings.MIN_BUY_QUANTITY
        )
        max_qty = (buying_power or {}).get("max_qty")
        holding_symbols = [
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        ]
        normalized_symbol = normalize_krx_symbol(symbol)
        holding_quantities = (portfolio_snapshot or {}).get("holding_quantities") or {}
        is_holding = normalized_symbol in holding_symbols
        holding_quantity = int(holding_quantities.get(normalized_symbol, 0) or 0)
        lines = [
            "- deterministic_stage: TIER2_PRECHECK",
            f"- strategy_type: {strategy_type}",
            "- strategy_semantics: STABLE_SHORT/AGGRESSIVE_SHORT are legacy execution/risk profile names, not target holding horizons.",
            "- horizon_policy: Prefer MID/LONG decisions; SHORT is only for rare, high-confidence tactical momentum exceptions.",
            "- allowed_scan_action: For non-held KRX cash equities, evaluate BUY or HOLD only; SELL only applies to already-held positions.",
            f"- market_regime: {str(market_regime or 'UNKNOWN').upper()}",
            f"- is_holding: {is_holding}",
            f"- holding_quantity: {holding_quantity}",
            f"- tier1_recommendation: {recommendation}",
            f"- tier1_confidence: {float(tier1_analysis.get('confidence', 0.0) or 0.0):.0%}",
            f"- code_rr_ratio: {rr_ratio:.2f}" if rr_ratio is not None else "- code_rr_ratio: 계산 불가",
            f"- min_rr_required: {min_rr:.2f}",
            f"- stop_loss_required: {bool(validation_flags.get('require_stop_loss_logging'))}",
            f"- min_buy_quantity: {min_buy_quantity}",
            f"- buying_power_max_qty: {max_qty if max_qty is not None else 'UNKNOWN'}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _rr_ratio(current_price: float, target_price: float, stop_loss_price: float) -> float | None:
        if current_price <= 0 or target_price <= 0 or stop_loss_price <= 0:
            return None
        risk = abs(float(current_price) - float(stop_loss_price))
        if risk <= 0:
            return None
        reward = abs(float(target_price) - float(current_price))
        return reward / risk


deterministic_prompt_context_service = DeterministicPromptContextService()
