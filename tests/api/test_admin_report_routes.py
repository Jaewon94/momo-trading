from datetime import date, datetime
from types import SimpleNamespace

import pytest


def _build_report(report_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        id="r-1",
        report_date=report_date,
        total_cycles=3,
        total_analyses=442,
        total_recommendations=18,
        total_orders=7,
        buy_count=0,
        sell_count=0,
        win_count=0,
        loss_count=0,
        total_pnl=0.0,
        unrealized_pnl=0.0,
        open_position_count=0,
        market_summary="",
        performance_review="",
        lessons_learned="",
        next_day_plan="",
        top_picks="[]",
        strategy_stats="{}",
        created_at=datetime(2026, 4, 3, 15, 30),
    )


@pytest.mark.asyncio
async def test_admin_report_by_date_applies_trade_metrics_fallback(client, monkeypatch):
    report = _build_report(date(2026, 4, 3))
    opened = [SimpleNamespace(stock_symbol="011930"), SimpleNamespace(stock_symbol="003280")]
    completed = [SimpleNamespace(is_win=True, pnl=12000.0), SimpleNamespace(is_win=False, pnl=-3000.0)]
    all_open = [SimpleNamespace(stock_symbol="011930"), SimpleNamespace(stock_symbol="003280")]

    class FakeDailyReportRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_date(self, d):
            assert d == date(2026, 4, 3)
            return report

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_opened_by_date(self, _d):
            return opened

        async def get_completed_by_date(self, _d):
            return completed

        async def get_all_open(self):
            return all_open

    monkeypatch.setattr("api.routes.admin.DailyReportRepository", FakeDailyReportRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)

    response = await client.get("/api/v1/admin/reports/2026-04-03")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["buy_count"] == 2
    assert payload["sell_count"] == 2
    assert payload["win_count"] == 1
    assert payload["loss_count"] == 1
    assert payload["total_pnl"] == 9000.0
    assert payload["open_position_count"] == 2


@pytest.mark.asyncio
async def test_admin_reports_list_applies_trade_metrics_fallback(client, monkeypatch):
    report = _build_report(date(2026, 4, 2))
    opened = [SimpleNamespace(stock_symbol="215790")]
    completed = []
    all_open = [SimpleNamespace(stock_symbol="215790"), SimpleNamespace(stock_symbol="011930")]

    class FakeDailyReportRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_reports(self, limit):
            assert limit == 30
            return [report]

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_opened_by_date(self, _d):
            return opened

        async def get_completed_by_date(self, _d):
            return completed

        async def get_all_open(self):
            return all_open

    monkeypatch.setattr("api.routes.admin.DailyReportRepository", FakeDailyReportRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)

    response = await client.get("/api/v1/admin/reports")
    assert response.status_code == 200
    payload = response.json()["data"][0]
    assert payload["buy_count"] == 1
    assert payload["sell_count"] == 0
    assert payload["open_position_count"] == 2
