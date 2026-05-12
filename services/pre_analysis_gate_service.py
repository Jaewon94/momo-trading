"""Deterministic gate before per-symbol Tier1 analysis."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analysis.chart_analyzer import ChartAnalysisResult
from core.config import settings
from trading.symbols import normalize_krx_symbol


@dataclass
class PreAnalysisGateDecision:
    approved: bool
    code: str
    reason: str
    detail: dict = field(default_factory=dict)


class PreAnalysisGateService:
    BEARISH_CONFIDENCE_THRESHOLD = 0.6

    def evaluate(
        self,
        *,
        symbol: str,
        current_price: float,
        daily_df: pd.DataFrame,
        chart_result: ChartAnalysisResult,
        portfolio_snapshot: dict | None,
        dynamic_limits: dict | None,
    ) -> PreAnalysisGateDecision:
        holding_symbols = [
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        ]
        is_holding = normalize_krx_symbol(symbol) in holding_symbols

        if not is_holding and current_price > 0:
            available_cash = float((portfolio_snapshot or {}).get("cash", 0) or 0)
            min_buy_quantity = (
                dynamic_limits.get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
                if dynamic_limits
                else settings.MIN_BUY_QUANTITY
            )
            min_buy_cost = current_price * min_buy_quantity
            if available_cash < min_buy_cost:
                return PreAnalysisGateDecision(
                    approved=False,
                    code="INSUFFICIENT_CASH",
                    reason="현금 부족으로 Tier1 분석을 진행하지 않음",
                    detail={
                        "available_cash": available_cash,
                        "min_buy_cost": min_buy_cost,
                        "min_buy_quantity": min_buy_quantity,
                    },
                )

        if current_price <= 0 and daily_df.empty:
            return PreAnalysisGateDecision(
                approved=False,
                code="MISSING_CORE_MARKET_DATA",
                reason="현재가와 일봉이 모두 없어 Tier1 분석을 진행하지 않음",
            )

        indicator_quality = self._evaluate_indicator_quality(chart_result)
        if not is_holding and indicator_quality is not None:
            return PreAnalysisGateDecision(
                approved=False,
                code="INVALID_INDICATOR_DATA",
                reason=indicator_quality["reason"],
                detail=indicator_quality,
            )

        signal_summary = chart_result.signal_summary or {}
        direction = str(signal_summary.get("direction", "") or "").upper()
        confidence = float(signal_summary.get("confidence", 0.0) or 0.0)
        if (
            not is_holding
            and direction == "BEARISH"
            and confidence >= self.BEARISH_CONFIDENCE_THRESHOLD
        ):
            return PreAnalysisGateDecision(
                approved=False,
                code="BEARISH_PRE_GATE",
                reason="강한 하락 추세 후보로 판단되어 Tier1 분석을 진행하지 않음",
                detail={
                    "direction": direction,
                    "confidence": confidence,
                },
            )

        return PreAnalysisGateDecision(
            approved=True,
            code="APPROVED",
            reason="Tier1 분석 진행 가능",
        )

    @staticmethod
    def _evaluate_indicator_quality(chart_result: ChartAnalysisResult) -> dict | None:
        indicators = chart_result.indicators or {}
        bb_upper = PreAnalysisGateService._to_float(indicators.get("bb_upper"))
        bb_middle = PreAnalysisGateService._to_float(indicators.get("bb_middle"))
        bb_lower = PreAnalysisGateService._to_float(indicators.get("bb_lower"))
        if all(value is not None for value in [bb_upper, bb_middle, bb_lower]):
            if not (bb_upper >= bb_middle >= bb_lower):
                return {
                    "reason": "볼린저 밴드 상/중/하단 순서가 비정상이라 분석을 보류합니다.",
                    "bb_upper": bb_upper,
                    "bb_middle": bb_middle,
                    "bb_lower": bb_lower,
                }
        return None

    @staticmethod
    def _to_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


pre_analysis_gate_service = PreAnalysisGateService()
