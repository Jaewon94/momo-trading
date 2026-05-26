from analysis.llm.prompts.overnight_hold import OVERNIGHT_HOLD_SYSTEM, build_overnight_prompt


def test_overnight_hold_prompt_supports_extension_decision() -> None:
    prompt = build_overnight_prompt(
        [
            {
                "symbol": "005930",
                "stock_name": "삼성전자",
                "avg_price": 70_000,
                "current_price": 73_000,
                "pnl_rate": 4.2,
                "quantity": 2,
                "hold_days": 15,
                "max_hold_days": 15,
                "trade_horizon": "MID",
                "hold_extension_count": 0,
                "hold_extension_until_days": None,
                "hold_extension_total_cap_days": 60,
                "confidence": 0.82,
                "target_price": 80_000,
                "stop_loss_price": 66_000,
                "strategy_type": "STABLE_SHORT",
            }
        ],
        "BULL",
    )

    assert "HOLD/SELL/EXTEND" in prompt
    assert '"action": "HOLD 또는 SELL 또는 EXTEND"' in prompt
    assert "호라이즌: MID" in prompt
    assert "연장심사: 필요" in prompt
    assert "총상한 60일" in prompt
    assert "EXTEND" in OVERNIGHT_HOLD_SYSTEM
    assert "자동 SELL이 아니라" in OVERNIGHT_HOLD_SYSTEM
