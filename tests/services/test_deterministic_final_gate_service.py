from services.deterministic_final_gate_service import DeterministicFinalGateService


def test_deterministic_final_gate_blocks_buy_when_confidence_is_below_effective_threshold() -> None:
    service = DeterministicFinalGateService()

    decision = service.evaluate(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        analysis={"recommendation": "BUY", "confidence": 0.6},
        current_price=70_000,
        market_regime="BEAR",
        portfolio_snapshot={"holding_symbols": []},
        dynamic_limits=None,
        active_rules={"param_overrides": {"ALL": {"min_confidence": 0.6}}},
        buying_power={"success": True, "max_qty": 10},
    )

    assert decision.approved is False
    assert decision.code == "CONFIDENCE_GATE"
    assert decision.detail["effective_min_confidence"] == 0.63


def test_deterministic_final_gate_blocks_buy_when_rr_is_undefined() -> None:
    service = DeterministicFinalGateService()

    decision = service.evaluate(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        analysis={
            "recommendation": "BUY",
            "confidence": 0.8,
            "target_price": 72_000,
            "stop_loss_price": 70_000,
        },
        current_price=70_000,
        market_regime="SIDEWAYS",
        portfolio_snapshot={"holding_symbols": []},
        dynamic_limits=None,
        active_rules={"validation_flags": {"revalidate_rr_ratio": True}},
        buying_power={"success": True, "max_qty": 10},
    )

    assert decision.approved is False
    assert decision.code == "RR_UNDEFINED_GATE"


def test_deterministic_final_gate_allows_holding_sell_to_bypass_confidence_gate() -> None:
    service = DeterministicFinalGateService()

    decision = service.evaluate(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        analysis={"recommendation": "SELL", "confidence": 0.4},
        current_price=70_000,
        market_regime="BEAR",
        portfolio_snapshot={"holding_symbols": ["005930"]},
        dynamic_limits=None,
        active_rules={"param_overrides": {"ALL": {"min_confidence": 0.7}}},
        buying_power=None,
    )

    assert decision.approved is True
    assert decision.code == "APPROVED"
