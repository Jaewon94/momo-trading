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
    """신호 성격을 기준으로 거래 호라이즌을 판정한다."""
    strategy_key = (strategy_type or "").upper()
    trigger_key = (trigger or "").upper()
    regime_key = (market_regime or "").upper()

    confidence_value = float(confidence or 0.0)
    abs_change = abs(float(change_rate or 0.0))
    has_short_trigger = trigger_key in {"PRICE_SURGE", "PRICE_DROP", "VOLUME_SPIKE"}
    is_aggressive = "AGGRESSIVE" in strategy_key

    # AI/broker latency makes broad ultra-short chasing fragile. Prefer a longer
    # horizon unless the candidate is a strong but not yet overheated momentum setup.
    if regime_key in {"BULL", "THEME"} and confidence_value >= 0.78 and abs_change <= 12.0:
        return TradeHorizon.LONG

    if (
        is_aggressive
        and has_short_trigger
        and 5.0 <= abs_change <= 15.0
        and confidence_value >= 0.62
    ):
        return TradeHorizon.SHORT

    return TradeHorizon.MID


def get_horizon_risk_multiplier(horizon: str) -> float:
    key = (horizon or "").upper()
    if key == TradeHorizon.SHORT:
        return 0.7
    if key == TradeHorizon.LONG:
        return 1.2
    return 1.0
