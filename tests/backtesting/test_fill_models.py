from backtesting.fill_models import LimitGuardFillModel, NextBarOHLCFillModel


def test_next_bar_ohlc_fill_model_applies_side_specific_slippage() -> None:
    model = NextBarOHLCFillModel(slippage_rate_pct=0.05)

    buy = model.fill_market_order(side="BUY", requested_quantity=10, reference_price=10_000)
    sell = model.fill_market_order(side="SELL", requested_quantity=10, reference_price=10_000)

    assert buy.filled is True
    assert buy.quantity == 10
    assert buy.price == 10_005
    assert sell.price == 9_995


def test_limit_guard_fill_model_rejects_halted_or_limit_locked_bar() -> None:
    model = LimitGuardFillModel(NextBarOHLCFillModel())

    halted = model.fill_market_order(
        side="BUY",
        requested_quantity=10,
        reference_price=10_000,
        bar={"volume": 0, "high": 10_000, "low": 10_000, "close": 10_000},
    )
    upper_locked = model.fill_market_order(
        side="BUY",
        requested_quantity=10,
        reference_price=10_000,
        bar={"volume": 100, "high": 10_000, "low": 10_000, "close": 10_000, "upper_limit": 10_000},
    )
    lower_locked = model.fill_market_order(
        side="SELL",
        requested_quantity=10,
        reference_price=10_000,
        bar={"volume": 100, "high": 10_000, "low": 10_000, "close": 10_000, "lower_limit": 10_000},
    )

    assert halted.filled is False
    assert halted.reason == "HALTED_OR_ZERO_VOLUME"
    assert upper_locked.filled is False
    assert upper_locked.reason == "UPPER_LIMIT_LOCKED"
    assert lower_locked.filled is False
    assert lower_locked.reason == "LOWER_LIMIT_LOCKED"
