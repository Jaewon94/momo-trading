import pandas as pd

from analysis.chart_analyzer import ChartAnalysisResult
from services.pre_analysis_gate_service import PreAnalysisGateService


def test_pre_analysis_gate_blocks_non_holding_when_cash_is_insufficient() -> None:
    service = PreAnalysisGateService()

    decision = service.evaluate(
        symbol="005930",
        current_price=70_000,
        daily_df=pd.DataFrame([{"close": 70_000}]),
        chart_result=ChartAnalysisResult(),
        portfolio_snapshot={"cash": 50_000, "holding_symbols": []},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert decision.approved is False
    assert decision.code == "INSUFFICIENT_CASH"
    assert decision.detail["min_buy_cost"] == 70_000


def test_pre_analysis_gate_blocks_when_price_and_daily_data_are_missing() -> None:
    service = PreAnalysisGateService()

    decision = service.evaluate(
        symbol="005930",
        current_price=0,
        daily_df=pd.DataFrame(),
        chart_result=ChartAnalysisResult(),
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": []},
        dynamic_limits=None,
    )

    assert decision.approved is False
    assert decision.code == "MISSING_CORE_MARKET_DATA"


def test_pre_analysis_gate_blocks_non_holding_on_strong_bearish_chart_signal() -> None:
    service = PreAnalysisGateService()

    decision = service.evaluate(
        symbol="005930",
        current_price=70_000,
        daily_df=pd.DataFrame([{"close": 70_000}]),
        chart_result=ChartAnalysisResult(
            signal_summary={"direction": "BEARISH", "confidence": 0.8}
        ),
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": []},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert decision.approved is False
    assert decision.code == "BEARISH_PRE_GATE"


def test_pre_analysis_gate_allows_holding_even_on_bearish_chart_signal() -> None:
    service = PreAnalysisGateService()

    decision = service.evaluate(
        symbol="005930",
        current_price=70_000,
        daily_df=pd.DataFrame([{"close": 70_000}]),
        chart_result=ChartAnalysisResult(
            signal_summary={"direction": "BEARISH", "confidence": 0.8}
        ),
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": ["005930"]},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert decision.approved is True
    assert decision.code == "APPROVED"


def test_pre_analysis_gate_blocks_invalid_bollinger_order_for_new_buy() -> None:
    service = PreAnalysisGateService()

    decision = service.evaluate(
        symbol="005930",
        current_price=70_000,
        daily_df=pd.DataFrame([{"close": 70_000}]),
        chart_result=ChartAnalysisResult(
            indicators={"bb_upper": 68_000, "bb_middle": 70_000, "bb_lower": 72_000}
        ),
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": []},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert decision.approved is False
    assert decision.code == "INVALID_INDICATOR_DATA"
