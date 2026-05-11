from types import SimpleNamespace

import pytest
from sqlalchemy import select
from trading.models import PendingOrderInfo


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

        async def get_sell_executions_by_date(self, d):
            assert d == target_date
            return []

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
    assert payload["sell_executions"] == []
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
async def test_admin_trade_reconciliation_route_returns_read_only_report(client, monkeypatch):
    db_pending = [
        SimpleNamespace(
            id="db-stale",
            order_id="DB-1",
            stock_symbol="003280",
            stock_name="흥아해운",
            side="BUY",
            quantity=7,
            status="PENDING_CONFIRM",
            created_at=__import__("datetime").datetime(2026, 4, 22, 8, 0),
            entry_at=__import__("datetime").datetime(2026, 4, 22, 8, 0),
        )
    ]
    broker_pending = [
        PendingOrderInfo(
            order_id="BR-1",
            symbol="005930",
            name="삼성전자",
            side="매수",
            order_qty=3,
            filled_qty=0,
            remaining_qty=3,
            order_price=71000.0,
            order_time="091500",
        )
    ]

    class FakeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_pending_confirms(self):
            return db_pending

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeRepo, raising=False)
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: SimpleNamespace(get_pending_orders=lambda: __import__("asyncio").sleep(0, result=broker_pending)),
    )

    response = await client.get("/api/v1/admin/trades/reconciliation")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["broker_pending_count"] == 1
    assert payload["summary"]["db_pending_count"] == 1
    assert payload["broker_only"][0]["order_id"] == "BR-1"
    assert payload["db_only_stale"][0]["trade_id"] == "db-stale"


@pytest.mark.asyncio
async def test_admin_trade_close_reconciliation_route_returns_dry_run_report(client, monkeypatch):
    captured = {}

    async def fake_build_dry_run(_db, *, days: int):
        captured["days"] = days
        return {
            "mode": "DRY_RUN",
            "summary": {
                "sell_execution_count": 15,
                "matched_sell_count": 12,
                "estimated_pnl": -12345.0,
            },
            "matches": [],
            "unmatched_sells": [],
        }

    monkeypatch.setattr(
        "api.routes.admin.trade_close_reconciliation_service.build_dry_run",
        fake_build_dry_run,
    )

    response = await client.get("/api/v1/admin/trades/close-reconciliation?days=7")

    assert response.status_code == 200
    payload = response.json()
    assert captured["days"] == 7
    assert payload["data"]["mode"] == "DRY_RUN"
    assert payload["data"]["summary"]["sell_execution_count"] == 15
    assert payload["message"] == "청산 대사 dry-run 리포트 조회 완료"


@pytest.mark.asyncio
async def test_admin_trade_lifecycle_integrity_route_returns_report(client, monkeypatch):
    captured = {}

    async def fake_build_report(_db, *, days: int, broker_position_snapshot=None):
        captured["days"] = days
        captured["broker_position_snapshot"] = broker_position_snapshot
        return {
            "status": "OK",
            "summary": {
                "open_buy_count": 0,
                "pending_confirm_count": 0,
                "unpaired_sell_count": 0,
            },
            "checks": [],
        }

    monkeypatch.setattr(
        "api.routes.admin.trade_lifecycle_integrity_service.build_report",
        fake_build_report,
    )
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: SimpleNamespace(
            provider=SimpleNamespace(value="KIWOOM"),
            get_holdings=lambda: __import__("asyncio").sleep(0, result=[]),
            get_pending_orders=lambda: __import__("asyncio").sleep(0, result=[]),
        ),
    )

    response = await client.get("/api/v1/admin/trades/lifecycle-integrity?days=3")

    assert response.status_code == 200
    payload = response.json()
    assert captured["days"] == 3
    assert captured["broker_position_snapshot"]["provider"] == "KIWOOM"
    assert payload["data"]["status"] == "OK"
    assert payload["message"] == "거래 라이프사이클 무결성 점검 완료"


@pytest.mark.asyncio
async def test_admin_trade_close_reconciliation_apply_always_requires_confirmation(client, monkeypatch):
    async def fake_apply_reconciliation(_db, *, days: int):
        return {"mode": "APPLY", "summary": {"applied_sell_count": 1, "updated_buy_lot_count": 1, "applied_pnl": 1000}}

    monkeypatch.setattr(
        "api.routes.admin.trade_close_reconciliation_service.apply_reconciliation",
        fake_apply_reconciliation,
    )
    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", False, raising=False)

    response = await client.post("/api/v1/admin/trades/close-reconciliation/apply?days=7")

    assert response.status_code == 428
    assert response.json()["detail"]["action"] == "APPLY_TRADE_CLOSE_RECONCILIATION"


@pytest.mark.asyncio
async def test_admin_trade_close_reconciliation_apply_accepts_confirmation_token(client, monkeypatch):
    captured = {}

    async def fake_apply_reconciliation(_db, *, days: int):
        captured["days"] = days
        return {
            "mode": "APPLY",
            "summary": {
                "applied_sell_count": 2,
                "updated_buy_lot_count": 4,
                "applied_pnl": 12345.0,
            },
            "applied": [],
            "skipped": [],
        }

    monkeypatch.setattr(
        "api.routes.admin.trade_close_reconciliation_service.apply_reconciliation",
        fake_apply_reconciliation,
    )
    challenge_response = await client.post(
        "/api/v1/admin/actions/confirmations",
        json={
            "action": "APPLY_TRADE_CLOSE_RECONCILIATION",
            "resource_id": "TRADE_CLOSE_RECONCILIATION",
            "quantity": "7D",
        },
    )
    token = challenge_response.json()["data"]["confirmation_token"]

    response = await client.post(
        "/api/v1/admin/trades/close-reconciliation/apply?days=7",
        json={"confirmation_token": token},
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["days"] == 7
    assert payload["data"]["mode"] == "APPLY"
    assert payload["data"]["summary"]["applied_sell_count"] == 2
    assert "청산 대사 적용 완료" in payload["message"]


@pytest.mark.asyncio
async def test_admin_trade_reconciliation_cleanup_defaults_to_dry_run(client, monkeypatch):
    db_pending = [
        SimpleNamespace(
            id="db-stale",
            order_id="DB-1",
            stock_symbol="003280",
            stock_name="흥아해운",
            side="BUY",
            quantity=7,
            status="PENDING_CONFIRM",
            notes="PENDING_CONFIRM",
            created_at=__import__("datetime").datetime(2026, 4, 22, 8, 0),
            entry_at=__import__("datetime").datetime(2026, 4, 22, 8, 0),
        )
    ]

    class FakeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_pending_confirms(self):
            return db_pending

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeRepo, raising=False)
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: SimpleNamespace(get_pending_orders=lambda: __import__("asyncio").sleep(0, result=[])),
    )

    response = await client.post("/api/v1/admin/trades/reconciliation/cleanup")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "dry_run"
    assert payload["summary"]["eligible_count"] == 1
    assert payload["summary"]["updated_count"] == 0
    assert db_pending[0].status == "PENDING_CONFIRM"


@pytest.mark.asyncio
async def test_admin_trade_reconciliation_cleanup_apply_requires_confirmation_when_enabled(client, monkeypatch):
    called = False

    class FakeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_pending_confirms(self):
            return []

    async def fake_cleanup(*args, **kwargs):
        nonlocal called
        called = True
        return {"mode": "apply", "summary": {"eligible_count": 0, "updated_count": 0}}

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeRepo, raising=False)
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: SimpleNamespace(get_pending_orders=lambda: __import__("asyncio").sleep(0, result=[])),
    )
    monkeypatch.setattr("api.routes.admin.stale_pending_cleanup_service.cleanup", fake_cleanup)

    response = await client.post("/api/v1/admin/trades/reconciliation/cleanup?apply=true")

    assert response.status_code == 428
    assert called is False


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

    async def fake_close_missing(*, dry_run: bool = True):
        captured["close_missing_dry_run"] = dry_run
        return {
            "summary": {
                "mode": "dry_run" if dry_run else "apply",
                "candidate_count": 3,
                "closed_count": 0 if dry_run else 3,
            },
            "candidates": [],
            "skipped": [],
        }

    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._repair_confirmed_zero_entry_prices",
        fake_repair,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._close_open_buys_missing_from_holdings",
        fake_close_missing,
    )

    response = await client.post("/api/v1/admin/trades/reconcile-holdings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["backfill"]["backfilled"] == 2
    assert payload["data"]["repair"]["repaired"] == 1
    assert payload["data"]["missing_closes"]["summary"]["mode"] == "dry_run"
    assert captured == {"backfill": True, "repair": True, "close_missing_dry_run": True}


@pytest.mark.asyncio
async def test_admin_reconcile_holdings_trades_apply_missing_requires_confirmation_when_enabled(client, monkeypatch):
    called = False

    async def fake_backfill():
        return {"provider": "KIWOOM", "backfilled": 0, "skipped": 0}

    async def fake_repair():
        return {"provider": "KIWOOM", "candidates": 0, "repaired": 0, "skipped": 0}

    async def fake_close_missing(*, dry_run: bool = True):
        nonlocal called
        called = True
        return {"summary": {"mode": "apply", "closed_count": 0}, "candidates": [], "skipped": []}

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._repair_confirmed_zero_entry_prices",
        fake_repair,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._close_open_buys_missing_from_holdings",
        fake_close_missing,
    )

    response = await client.post("/api/v1/admin/trades/reconcile-holdings?apply_missing_closes=true")

    assert response.status_code == 428
    assert called is False


@pytest.mark.asyncio
async def test_admin_reset_operational_baseline_route_returns_summary(client, monkeypatch):
    from models.account_day_baseline import AccountDayBaseline
    from models.account_equity_snapshot import AccountEquitySnapshot
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

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
                "account_day_baselines": 6,
                "account_equity_snapshots": 7,
                "agent_activity_logs": 8,
                "news_items": 9,
            }
            return FakeResult(counts[table])

    observed = {"reset": 0}
    service = AccountEquityService(session_factory=TestAsyncSessionLocal)

    async def fake_backfill():
        return {"provider": "KIWOOM", "backfilled": 2, "skipped": 0}

    async def fake_repair():
        return {"provider": "KIWOOM", "candidates": 0, "repaired": 0, "skipped": 0}

    async def fake_log(*args, **kwargs):
        observed["logged"] = True

    monkeypatch.setattr("api.routes.admin.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        "api.routes.admin.runtime_backup_service.create_database_backup",
        lambda reason="manual": {
            "filename": f"app-{reason}-20260406-160000.db",
            "relative_path": f"runtime/backups/db/app-{reason}-20260406-160000.db",
        },
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._repair_confirmed_zero_entry_prices",
        fake_repair,
    )
    monkeypatch.setattr("api.routes.admin.account_equity_service", service)
    monkeypatch.setattr("api.routes.admin.account_manager.invalidate_cache", lambda: observed.__setitem__("account_cache", True))
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: SimpleNamespace(
            invalidate_cache=lambda: observed.__setitem__("broker_cache", True),
            get_balance=lambda: __import__("asyncio").sleep(0, result=SimpleNamespace(
                total_asset=527064565.0,
                cash=323359499.0,
                stock_value=203705066.0,
                total_pnl=-2704805.0,
            )),
            get_holdings=lambda: __import__("asyncio").sleep(0, result=[
                SimpleNamespace(symbol="001250"),
                SimpleNamespace(symbol="049080"),
            ]),
            get_pending_orders=lambda: __import__("asyncio").sleep(0, result=[SimpleNamespace(order_id="1")]),
        ),
    )
    monkeypatch.setattr("api.routes.admin.news_runtime_service.reset", lambda: observed.__setitem__("reset", observed["reset"] + 1))
    monkeypatch.setattr("api.routes.admin.activity_logger.log", fake_log)

    response = await client.post("/api/v1/admin/system/reset-operational-baseline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["backup"]["filename"] == "app-before-reset-20260406-160000.db"
    assert payload["data"]["deleted"]["trade_results"] == 4
    assert payload["data"]["deleted"]["account_day_baselines"] == 6
    assert payload["data"]["deleted"]["account_equity_snapshots"] == 7
    assert payload["data"]["deleted"]["news_items"] == 9
    assert payload["data"]["backfill"]["backfilled"] == 2
    assert payload["data"]["baseline_mode"] == "broker_snapshot"
    assert payload["data"]["broker_snapshot"]["synced"] is True
    assert payload["data"]["broker_snapshot"]["holdings_count"] == 2
    assert payload["data"]["broker_snapshot"]["pending_order_count"] == 1
    assert payload["data"]["broker_snapshot"]["baseline_seeded"] is True
    assert payload["data"]["limitations"]["historical_realized_pnl_restored"] is False
    assert payload["data"]["preserved"]["runtime_settings"] is True
    assert observed["reset"] == 1
    assert observed["account_cache"] is True
    assert observed["broker_cache"] is True

    async with TestAsyncSessionLocal() as session:
        baselines = (await session.execute(select(AccountDayBaseline))).scalars().all()
        snapshots = (await session.execute(select(AccountEquitySnapshot))).scalars().all()

    assert len(baselines) == 1
    assert baselines[0].baseline_total_asset == pytest.approx(527064565.0)
    assert baselines[0].baseline_holding_count == 2
    assert baselines[0].baseline_pending_order_count == 1
    assert baselines[0].baseline_source == "RESET_BASELINE"
    assert len(snapshots) == 1
    assert snapshots[0].session_phase == "RESET_BASELINE"
    assert snapshots[0].total_asset == pytest.approx(527064565.0)


@pytest.mark.asyncio
async def test_admin_reset_operational_baseline_requires_confirmation_when_enabled(client, monkeypatch):
    called = False

    def fake_backup(reason="manual"):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr("api.routes.admin.runtime_backup_service.create_database_backup", fake_backup)

    response = await client.post("/api/v1/admin/system/reset-operational-baseline")

    assert response.status_code == 428
    assert called is False


@pytest.mark.asyncio
async def test_admin_backup_operational_db_route_returns_backup_metadata(client, monkeypatch):
    observed = {}

    monkeypatch.setattr(
        "api.routes.admin.runtime_backup_service.create_database_backup",
        lambda reason="manual": observed.setdefault("backup", {
            "filename": f"app-{reason}-20260406-161500.db",
            "relative_path": f"runtime/backups/db/app-{reason}-20260406-161500.db",
        }),
    )

    async def fake_log(*args, **kwargs):
        observed["logged"] = True

    monkeypatch.setattr("api.routes.admin.activity_logger.log", fake_log)

    response = await client.post("/api/v1/admin/system/backup-operational-db")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["filename"] == "app-manual-20260406-161500.db"
    assert payload["data"]["relative_path"] == "runtime/backups/db/app-manual-20260406-161500.db"
    assert observed["logged"] is True
