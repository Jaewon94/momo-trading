import json


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
