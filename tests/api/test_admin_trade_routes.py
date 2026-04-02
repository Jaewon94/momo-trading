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
