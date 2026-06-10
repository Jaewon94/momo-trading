"""안정형 스윙 실행 프로파일: 저변동 우량주, 중기 보유, 과도한 추격 억제

판단(BUY/SELL/HOLD)은 AI 분석 결과를 신뢰하고,
전략은 실행 파라미터(손절/익절/긴급도)와 이유 텍스트를 제공한다.
"""
from strategy.base import strategy_profile_metadata
from strategy.signal import TradeSignal
from trading.enums import SignalAction, SignalUrgency


class StableShortStrategy:
    """
    안정형 스윙 실행 프로파일 (legacy: STABLE_SHORT)
    - 대상: 대형 우량주, ETF (변동성 낮은 종목)
    - 기본 보유 기간: 중기, 필요 시 장기
    - 손절: -7%, 익절: +12% (기본값, 시장 국면별 동적 조정)
    - 판단: AI recommendation + confidence 기반
    """

    strategy_type = "STABLE_SHORT"

    REGIME_PARAMS = {
        "BULL":  {"stop_loss_pct": -7.0, "take_profit_pct": 14.0},
        "THEME": {"stop_loss_pct": -8.0, "take_profit_pct": 16.0},
        "BEAR":  {"stop_loss_pct": -5.0, "take_profit_pct": 8.0},
    }

    def __init__(
        self,
        stop_loss_pct: float = -7.0,
        take_profit_pct: float = 12.0,
        min_confidence: float = 0.58,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.min_confidence = min_confidence

    async def evaluate(self, analysis: dict, market_regime: str = "") -> TradeSignal | None:
        """AI 분석 결과 기반 시그널 생성 — 실행 파라미터 제공"""
        recommendation = analysis.get("recommendation", "HOLD")
        confidence = analysis.get("confidence", 0)
        indicators = analysis.get("indicators", {})
        symbol = analysis.get("symbol", "")
        stock_id = analysis.get("stock_id", "")
        current_price = analysis.get("current_price", 0)

        # 국면별 동적 파라미터 (기본값 폴백)
        params = self.REGIME_PARAMS.get(market_regime, {})
        eff_stop = params.get("stop_loss_pct", self.stop_loss_pct)
        eff_target = params.get("take_profit_pct", self.take_profit_pct)

        # 최소 신뢰도 미달 → 스킵 (SELL은 면제)
        if confidence < self.min_confidence and recommendation != "SELL":
            return None

        # HOLD → 스킵
        if recommendation == "HOLD":
            return None

        # 차트 분석 정보 (이유 텍스트용)
        chart_result = analysis.get("chart_result")
        signal_summary = {}
        if chart_result:
            signal_summary = getattr(chart_result, "signal_summary", {}) or {}

        rsi = indicators.get("rsi_14")

        # === BUY ===
        if recommendation == "BUY":
            reasons = [f"AI 매수 추천 (신뢰도 {confidence:.0%})"]

            # 지표 기반 이유 보강 (판단 차단 아님, 로깅용)
            if rsi is not None and rsi < 35:
                reasons.append(f"RSI 과매도({rsi:.0f})")
            bb_lower = indicators.get("bb_lower")
            if bb_lower and current_price <= bb_lower * 1.01:
                reasons.append("볼린저밴드 하단 접근")
            if signal_summary.get("direction") == "BULLISH":
                reasons.append("차트 매수 시그널")

            target_price = current_price * (1 + eff_target / 100)
            stop_loss = current_price * (1 + eff_stop / 100)

            return TradeSignal(
                symbol=symbol,
                stock_id=stock_id,
                action=SignalAction.BUY,
                strength=confidence,
                suggested_price=current_price,
                target_price=target_price,
                stop_loss_price=stop_loss,
                urgency=SignalUrgency.WAIT,
                strategy_type=self.strategy_type,
                reason=" + ".join(reasons),
                confidence=confidence,
                metadata=strategy_profile_metadata(self.strategy_type),
            )

        # === SELL ===
        if recommendation == "SELL":
            target_price = current_price * (1 + eff_stop / 100)
            stop_loss = current_price * (1 - eff_stop / 100)
            return TradeSignal(
                symbol=symbol,
                stock_id=stock_id,
                action=SignalAction.SELL,
                strength=confidence,
                suggested_price=current_price,
                target_price=target_price,
                stop_loss_price=stop_loss,
                urgency=SignalUrgency.WAIT,
                strategy_type=self.strategy_type,
                reason=f"AI 매도 추천 (신뢰도 {confidence:.0%})",
                confidence=confidence,
                metadata=strategy_profile_metadata(self.strategy_type),
            )

        return None
