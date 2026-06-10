from trading.enums import SignalAction

from strategy.exposure_policy import resolve_aggressive_exposure_alignment


def _base_kwargs(**overrides):
    payload = {
        "enabled": True,
        "risk_appetite": "AGGRESSIVE",
        "market_regime": "BULL",
        "action": SignalAction.BUY,
        "confidence": 0.7,
        "min_confidence": 0.65,
        "price": 100_000,
        "quantity": 50,
        "portfolio_snapshot": {
            "cash": 400_000_000,
            "total_asset": 500_000_000,
            "stock_value": 25_000_000,
            "current_exposure_pct": 5.0,
        },
        "dynamic_limits": {
            "max_single_order_krw": 50_000_000,
            "max_position_pct": 15.0,
        },
        "target_exposure_pct": 25.0,
        "min_order_krw": 20_000_000,
    }
    payload.update(overrides)
    return payload


def test_aggressive_exposure_alignment_raises_small_buy_to_min_order():
    decision = resolve_aggressive_exposure_alignment(**_base_kwargs())

    assert decision.applied is True
    assert decision.reason == "aggressive_exposure_floor"
    assert decision.initial_quantity == 50
    assert decision.final_quantity == 200
    assert decision.final_notional == 20_000_000


def test_aggressive_exposure_alignment_respects_dynamic_order_cap():
    decision = resolve_aggressive_exposure_alignment(
        **_base_kwargs(dynamic_limits={"max_single_order_krw": 12_000_000, "max_position_pct": 15.0})
    )

    assert decision.applied is True
    assert decision.final_quantity == 120
    assert decision.final_notional == 12_000_000


def test_aggressive_exposure_alignment_skips_when_confidence_too_low():
    decision = resolve_aggressive_exposure_alignment(**_base_kwargs(confidence=0.64))

    assert decision.applied is False
    assert decision.reason == "confidence_below_floor"
    assert decision.final_quantity == 50


def test_aggressive_exposure_alignment_skips_when_not_aggressive():
    decision = resolve_aggressive_exposure_alignment(**_base_kwargs(risk_appetite="MODERATE"))

    assert decision.applied is False
    assert decision.reason == "risk_appetite_not_aggressive"


def test_aggressive_exposure_alignment_skips_when_target_exposure_reached():
    decision = resolve_aggressive_exposure_alignment(
        **_base_kwargs(portfolio_snapshot={
            "cash": 375_000_000,
            "total_asset": 500_000_000,
            "stock_value": 125_000_000,
            "current_exposure_pct": 25.0,
        })
    )

    assert decision.applied is False
    assert decision.reason == "target_exposure_reached"
