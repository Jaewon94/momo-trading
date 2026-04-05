import json
from types import SimpleNamespace

from services.performance_reporting_service import PerformanceReportingService, _TradePoint


def test_calc_metrics_returns_expectancy_and_drawdown():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=100, return_pct=1.0, exit_at=__import__("datetime").datetime.now()),
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=-50, return_pct=-0.5, exit_at=__import__("datetime").datetime.now()),
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=200, return_pct=2.0, exit_at=__import__("datetime").datetime.now()),
    ]

    metrics = service._calc_metrics(trades)

    assert metrics["trade_count"] == 3
    assert metrics["win_rate"] == 0.6667
    assert metrics["expectancy"] > 0
    assert metrics["max_drawdown"] <= 0


def test_extract_horizon_prefers_notes_json():
    service = PerformanceReportingService()
    trade = SimpleNamespace(
        notes=json.dumps({"trade_horizon": "LONG"}, ensure_ascii=False),
        strategy_type="AGGRESSIVE_SHORT",
    )
    assert service._extract_horizon(trade) == "LONG"
