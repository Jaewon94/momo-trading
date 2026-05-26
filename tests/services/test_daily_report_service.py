import json
from types import SimpleNamespace

from services.daily_report_service import DailyReportService


def test_needs_snapshot_fallback_when_broker_reports_zero_pnl_with_open_positions():
    assert DailyReportService._needs_snapshot_fallback(
        unrealized_pnl=0.0,
        open_position_count=3,
        total_asset=479_000_000.0,
    ) is True


def test_needs_snapshot_fallback_when_broker_response_empty():
    assert DailyReportService._needs_snapshot_fallback(
        unrealized_pnl=0.0,
        open_position_count=0,
        total_asset=0.0,
    ) is True


def test_needs_snapshot_fallback_skips_when_broker_reports_nonzero_pnl():
    assert DailyReportService._needs_snapshot_fallback(
        unrealized_pnl=-12_345.0,
        open_position_count=2,
        total_asset=479_000_000.0,
    ) is False


def test_needs_snapshot_fallback_skips_when_no_holdings_and_total_asset_known():
    assert DailyReportService._needs_snapshot_fallback(
        unrealized_pnl=0.0,
        open_position_count=0,
        total_asset=479_000_000.0,
    ) is False


def test_apply_snapshot_fallback_populates_pnl_from_snapshot():
    snapshot = SimpleNamespace(
        total_unrealized_pnl=-926_642.0,
        total_asset=478_375_000.0,
        cash=425_950_000.0,
        stock_value=52_425_000.0,
        holding_count=8,
    )
    result = DailyReportService._apply_snapshot_fallback(
        unrealized_pnl=0.0,
        total_asset=479_000_000.0,
        cash=420_000_000.0,
        stock_value=59_000_000.0,
        open_position_count=8,
        snapshot=snapshot,
    )
    assert result == (-926_642.0, 479_000_000.0, 420_000_000.0, 59_000_000.0, 8)


def test_apply_snapshot_fallback_fills_total_asset_when_zero():
    snapshot = SimpleNamespace(
        total_unrealized_pnl=-12_345.0,
        total_asset=479_000_000.0,
        cash=420_000_000.0,
        stock_value=59_000_000.0,
        holding_count=4,
    )
    result = DailyReportService._apply_snapshot_fallback(
        unrealized_pnl=0.0,
        total_asset=0.0,
        cash=0.0,
        stock_value=0.0,
        open_position_count=0,
        snapshot=snapshot,
    )
    assert result == (-12_345.0, 479_000_000.0, 420_000_000.0, 59_000_000.0, 4)


def test_apply_snapshot_fallback_noop_when_unrealized_already_nonzero():
    snapshot = SimpleNamespace(
        total_unrealized_pnl=-100.0,
        total_asset=1.0, cash=1.0, stock_value=1.0, holding_count=1,
    )
    result = DailyReportService._apply_snapshot_fallback(
        unrealized_pnl=-999.0,
        total_asset=0.0,
        cash=0.0,
        stock_value=0.0,
        open_position_count=0,
        snapshot=snapshot,
    )
    # snapshot should be ignored because broker already reported nonzero pnl
    assert result == (-999.0, 0.0, 0.0, 0.0, 0)


def test_apply_snapshot_fallback_noop_when_no_snapshot():
    result = DailyReportService._apply_snapshot_fallback(
        unrealized_pnl=0.0,
        total_asset=0.0,
        cash=0.0,
        stock_value=0.0,
        open_position_count=0,
        snapshot=None,
    )
    assert result == (0.0, 0.0, 0.0, 0.0, 0)


def test_daily_report_strategy_stats_separates_activity_counts_and_metric_contract():
    from services.daily_report_service import DailyReportService

    payload = DailyReportService()._build_strategy_stats_payload(
        activity_counts={"CYCLE": 4, "DECISION": 3},
        buy_count=2,
        sell_order_count=1,
        completed_position_count=1,
        win_count=1,
        loss_count=0,
        open_position_count=2,
    )

    assert payload["CYCLE"] == 4
    assert payload["activity_counts"] == {"CYCLE": 4, "DECISION": 3}

    contract = payload["metric_contract"]
    assert contract["total_orders"]["value"] == 3
    assert contract["total_orders"]["formula"] == "buy_count + sell_order_count"
    assert contract["buy_count"]["source"] == "trade_results BUY rows by entry_at"
    assert contract["sell_count"]["source"] == "trade_results SELL rows by exit_at"
    assert contract["win_loss"]["completed_position_count"] == 1
    assert contract["open_position_count"]["source"] == "broker holdings, fallback open BUY symbols"

    encoded = json.dumps(payload, ensure_ascii=False)
    assert "metric_contract" in encoded
