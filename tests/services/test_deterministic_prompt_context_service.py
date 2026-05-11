from analysis.chart_analyzer import ChartAnalysisResult
from services.deterministic_prompt_context_service import DeterministicPromptContextService


def test_deterministic_prompt_context_formats_tier1_precheck() -> None:
    service = DeterministicPromptContextService()

    context = service.build_tier1_context(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        current_price=70_000,
        chart_result=ChartAnalysisResult(signal_summary={"direction": "BULLISH", "confidence": 0.72}),
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": []},
        market_regime="SIDEWAYS",
        dynamic_limits={"min_buy_quantity": 2},
    )

    assert "deterministic_stage: TIER1_PRECHECK" in context
    assert "chart_signal: BULLISH / confidence 72%" in context
    assert "min_buy_cost: 140,000원" in context


def test_deterministic_prompt_context_formats_tier2_precheck_rr_ratio() -> None:
    service = DeterministicPromptContextService()

    context = service.build_tier2_context(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        current_price=70_000,
        tier1_analysis={
            "recommendation": "BUY",
            "confidence": 0.8,
            "target_price": 74_000,
            "stop_loss_price": 68_000,
        },
        portfolio_snapshot={"holding_symbols": ["005930"], "holding_quantities": {"005930": 75}},
        market_regime="SIDEWAYS",
        dynamic_limits={"min_buy_quantity": 1},
        active_rules={"validation_flags": {"require_stop_loss_logging": True}},
        buying_power={"success": True, "max_qty": 10},
    )

    assert "deterministic_stage: TIER2_PRECHECK" in context
    assert "is_holding: True" in context
    assert "holding_quantity: 75" in context
    assert "code_rr_ratio: 2.00" in context
    assert "stop_loss_required: True" in context
    assert "buying_power_max_qty: 10" in context
