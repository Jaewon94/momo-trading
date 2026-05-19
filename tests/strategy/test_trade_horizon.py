from strategy.trade_horizon import TradeHorizon, decide_trade_horizon


def test_decide_trade_horizon_short_for_aggressive_event():
    horizon = decide_trade_horizon(
        strategy_type="AGGRESSIVE_SHORT",
        trigger="PRICE_SURGE",
        change_rate=7.1,
        confidence=0.66,
        market_regime="THEME",
    )
    assert horizon == TradeHorizon.SHORT


def test_decide_trade_horizon_long_for_high_confidence_bull():
    horizon = decide_trade_horizon(
        strategy_type="STABLE_SHORT",
        trigger="",
        change_rate=1.2,
        confidence=0.82,
        market_regime="BULL",
    )
    assert horizon == TradeHorizon.LONG


def test_decide_trade_horizon_mid_as_default():
    horizon = decide_trade_horizon(
        strategy_type="STABLE_SHORT",
        trigger="",
        change_rate=2.2,
        confidence=0.62,
        market_regime="SIDEWAYS",
    )
    assert horizon == TradeHorizon.MID


def test_decide_trade_horizon_mid_for_overheated_aggressive_move():
    horizon = decide_trade_horizon(
        strategy_type="AGGRESSIVE_SHORT",
        trigger="PRICE_SURGE",
        change_rate=22.0,
        confidence=0.7,
        market_regime="THEME",
    )
    assert horizon == TradeHorizon.MID


def test_decide_trade_horizon_mid_for_aggressive_without_short_trigger():
    horizon = decide_trade_horizon(
        strategy_type="AGGRESSIVE_SHORT",
        trigger="",
        change_rate=4.0,
        confidence=0.7,
        market_regime="BULL",
    )
    assert horizon == TradeHorizon.MID
