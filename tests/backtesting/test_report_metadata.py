from backtesting.metrics import BacktestMetrics
from backtesting.report import BacktestReport


def test_backtest_report_promotes_execution_fee_and_fill_metadata() -> None:
    report = BacktestReport.generate(
        symbol="005930",
        strategy_type="STABLE_SHORT",
        metrics=BacktestMetrics(initial_capital=1_000_000, final_capital=1_000_000),
        trades=[],
        config={
            "execution_timing": "NEXT_OPEN",
            "model_family": "RULE_BASED_TECHNICAL_PROXY",
            "fee_model": {
                "name": "KOREA_STOCK_FEE_MODEL",
                "commission_rate_pct": 0.015,
                "sell_tax_rate_pct": 0.15,
            },
            "fill_model": {
                "name": "LIMIT_GUARDED_NEXT_BAR_OHLC",
                "slippage_rate_pct": 0.05,
                "guards": ["HALTED_OR_ZERO_VOLUME", "UPPER_LIMIT_LOCKED", "LOWER_LIMIT_LOCKED"],
            },
        },
    )

    assert report["metadata"]["model_family"] == "RULE_BASED_TECHNICAL_PROXY"
    assert report["metadata"]["execution_policy"] == "NEXT_OPEN"
    assert report["metadata"]["fee_model"]["name"] == "KOREA_STOCK_FEE_MODEL"
    assert report["metadata"]["fill_model"]["name"] == "LIMIT_GUARDED_NEXT_BAR_OHLC"
