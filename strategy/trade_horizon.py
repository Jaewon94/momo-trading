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

    if (
        "AGGRESSIVE" in strategy_key
        or trigger_key in {"PRICE_SURGE", "PRICE_DROP", "VOLUME_SPIKE"}
        or abs(float(change_rate or 0.0)) >= 6.0
    ):
        return TradeHorizon.SHORT

    if regime_key in {"BULL", "THEME"} and float(confidence or 0.0) >= 0.78:
        return TradeHorizon.LONG

    return TradeHorizon.MID


def get_horizon_risk_multiplier(horizon: str) -> float:
    key = (horizon or "").upper()
    if key == TradeHorizon.SHORT:
        return 0.7
    if key == TradeHorizon.LONG:
        return 1.2
    return 1.0
