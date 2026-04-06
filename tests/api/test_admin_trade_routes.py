from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_admin_trades_route_includes_pending_confirms(client, monkeypatch):
    target_date = __import__("datetime").date(2026, 4, 2)
    opened_trade = SimpleNamespace(id="o1", stock_symbol="005930", stock_name="삼성전자", side="BUY", strategy_type="STABLE_SHORT", entry_price=71000.0, exit_price=0.0, quantity=2, pnl=0.0, return_pct=0.0, is_win=False, hold_days=0, exit_reason="", ai_recommendation="BUY", ai_confidence=0.82, ai_target_price=None, ai_stop_loss_price=None, entry_rsi=None, entry_pattern=None, market_regime="", status="CONFIRMED", entry_at=__import__("datetime").datetime(2026, 4, 2, 9, 5), exit_at=None, created_at=__import__("datetime").datetime(2026, 4, 2, 9, 5))
    pending_trade = SimpleNamespace(id="p1", stock_symbol="003280", stock_name="흥아해운", side="BUY", strategy_type="SCALP", entry_price=1895.0, exit_price=0.0, quantity=7800, pnl=0.0, return_pct=0.0, is_win=False, hold_days=0, exit_reason="", ai_recommendation="BUY", ai_confidence=0.71, ai_target_price=None, ai_stop_loss_price=None, entry_rsi=None, entry_pattern=None, market_regime="", status="PENDING_CONFIRM", entry_at=__import__("datetime").datetime(2026, 4, 2, 9, 9), exit_at=None, created_at=__import__("datetime").datetime(2026, 4, 2, 9, 9))

    class FakeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_opened_by_date(self, d):
            assert d == target_date
            return [opened_trade]

        async def get_completed_by_date(self, d):
            assert d == target_date
            return []

        async def get_all_open(self):
            return []

        async def get_pending_confirms_by_date(self, d):
            assert d == target_date
            return [pending_trade]

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeRepo, raising=False)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))

    response = await client.get("/api/v1/admin/trades")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["opened"][0]["stock_symbol"] == "005930"
    assert payload["pending_confirms"][0]["stock_symbol"] == "003280"
    assert payload["pending_confirms"][0]["status"] == "PENDING_CONFIRM"


@pytest.mark.asyncio
async def test_admin_reconcile_pending_trades_route_returns_summary(client, monkeypatch):
    captured = {}

    async def fake_recover_pending_confirms():
        captured["called"] = True
        return {
            "provider": "KIWOOM",
            "pending_total": 2,
            "recovered": 1,
            "failed": 0,
            "skipped": 1,
        }

    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._recover_pending_confirms",
        fake_recover_pending_confirms,
    )

    response = await client.post("/api/v1/admin/trades/reconcile-pending")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["provider"] == "KIWOOM"
    assert payload["data"]["recovered"] == 1
    assert payload["data"]["skipped"] == 1
    assert captured["called"] is True


@pytest.mark.asyncio
async def test_admin_reconcile_holdings_trades_route_returns_summary(client, monkeypatch):
    captured = {}

    async def fake_backfill():
        captured["backfill"] = True
        return {
            "provider": "KIWOOM",
            "backfilled": 2,
            "skipped": 1,
        }

    async def fake_repair():
        captured["repair"] = True
        return {
            "provider": "KIWOOM",
            "candidates": 2,
            "repaired": 1,
            "skipped": 1,
        }

    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._repair_confirmed_zero_entry_prices",
        fake_repair,
    )

    response = await client.post("/api/v1/admin/trades/reconcile-holdings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["backfill"]["backfilled"] == 2
    assert payload["data"]["repair"]["repaired"] == 1
    assert captured == {"backfill": True, "repair": True}


@pytest.mark.asyncio
async def test_admin_reset_operational_baseline_route_returns_summary(client, monkeypatch):
    class FakeResult:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

        async def execute(self, statement):
            table = statement.table.name
            counts = {
                "recommendations": 1,
                "analysis_results": 2,
                "orders": 3,
                "trade_results": 4,
                "daily_reports": 5,
                "agent_activity_logs": 6,
                "news_items": 7,
            }
            return FakeResult(counts[table])

    observed = {"reset": 0}

    async def fake_backfill():
        return {"provider": "KIWOOM", "backfilled": 2, "skipped": 0}

    async def fake_repair():
        return {"provider": "KIWOOM", "candidates": 0, "repaired": 0, "skipped": 0}

    async def fake_log(*args, **kwargs):
        observed["logged"] = True

    monkeypatch.setattr("api.routes.admin.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._repair_confirmed_zero_entry_prices",
        fake_repair,
    )
    monkeypatch.setattr("api.routes.admin.account_manager.invalidate_cache", lambda: observed.__setitem__("account_cache", True))
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: SimpleNamespace(invalidate_cache=lambda: observed.__setitem__("broker_cache", True)))
    monkeypatch.setattr("api.routes.admin.news_runtime_service.reset", lambda: observed.__setitem__("reset", observed["reset"] + 1))
    monkeypatch.setattr("api.routes.admin.activity_logger.log", fake_log)

    response = await client.post("/api/v1/admin/system/reset-operational-baseline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["deleted"]["trade_results"] == 4
    assert payload["data"]["deleted"]["news_items"] == 7
    assert payload["data"]["backfill"]["backfilled"] == 2
    assert payload["data"]["preserved"]["runtime_settings"] is True
    assert observed["reset"] == 1
    assert observed["account_cache"] is True
    assert observed["broker_cache"] is True
