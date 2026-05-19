"""거래 호라이즌(단기/중기/장기) 판정 유틸리티."""


class TradeHorizon:
    SHORT = "SHORT"
    MID = "MID"
    LONG = "LONG"


def decide_trade_horizon(
    *,
    strategy_type: str,
    trigger: str = "",
    change_rate: float = 0.0,
    confidence: float = 0.0,
    market_regime: str = "",
) -> str:
    """신호 성격을 기준으로 거래 호라이즌을 판정한다.

    기본 운용은 AI가 시간 여유를 갖고 판단할 수 있는 MID/LONG이다.
    SHORT는 지연에 취약하므로 명시적인 전술 모멘텀 예외에만 부여한다.
    """
    strategy_key = (strategy_type or "").upper()
    trigger_key = (trigger or "").upper()
    regime_key = (market_regime or "").upper()

    confidence_value = float(confidence or 0.0)
    abs_change = abs(float(change_rate or 0.0))
    has_short_trigger = trigger_key in {"PRICE_SURGE", "VOLUME_SPIKE"}
    has_tactical_trigger = trigger_key in {"PRICE_SURGE", "VOLUME_SPIKE", "PRICE_DROP"}
    is_aggressive = "AGGRESSIVE" in strategy_key

    if (
        is_aggressive
        and has_short_trigger
        and regime_key in {"BULL", "THEME"}
        and 5.0 <= abs_change <= 10.0
        and confidence_value >= 0.78
    ):
        return TradeHorizon.SHORT

    if (
        not has_tactical_trigger
        and regime_key in {"BULL", "THEME"}
        and confidence_value >= 0.72
        and abs_change <= 10.0
    ):
        return TradeHorizon.LONG

    return TradeHorizon.MID


def get_horizon_risk_multiplier(horizon: str) -> float:
    key = (horizon or "").upper()
    if key == TradeHorizon.SHORT:
        return 0.7
    if key == TradeHorizon.LONG:
        return 1.2
    return 1.0
