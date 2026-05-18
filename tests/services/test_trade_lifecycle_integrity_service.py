from datetime import datetime, timedelta

import pytest

from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from models.trade_result import TradeResult
from services.trade_lifecycle_integrity_service import TradeLifecycleIntegrityService


def _trade(
    *,
    symbol: str,
    side: str,
    status: str = "CONFIRMED",
    quantity: int = 10,
    entry_price: float = 10_000,
    exit_price: float = 0,
    pnl: float = 0,
    entry_at: datetime,
    exit_at: datetime | None = None,
    notes: str | None = None,
) -> TradeResult:
    return TradeResult(
        stock_symbol=symbol,
        stock_name=symbol,
        side=side,
        strategy_type="STABLE_SHORT",
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        pnl=pnl,
        return_pct=0.0,
        is_win=pnl > 0,
        hold_days=0,
        exit_reason="SIGNAL" if exit_at else "",
        ai_recommendation="BUY",
        ai_confidence=0.7,
        market="KRX",
        market_regime="NORMAL",
        status=status,
        entry_at=entry_at,
        exit_at=exit_at,
        notes=notes,
    )


def _seed_account_readiness(session, *, now: datetime) -> None:
    session.add(AccountDayBaseline(
        trading_date=now.date(),
        baseline_at=now,
        baseline_total_asset=500_000_000,
        baseline_cash=500_000_000,
        baseline_stock_value=0,
        baseline_total_unrealized_pnl=0,
        baseline_holding_count=0,
        baseline_pending_order_count=0,
        baseline_source="RESET_BASELINE",
    ))
    session.add(AccountEquitySnapshot(
        trading_date=now.date(),
        captured_at=now,
        session_phase="RESET_BASELINE",
        total_asset=500_000_000,
        cash=500_000_000,
        stock_value=0,
        total_unrealized_pnl=0,
        total_unrealized_pnl_rate=0,
        holding_count=0,
        pending_order_count=0,
    ))


@pytest.mark.asyncio
async def test_lifecycle_integrity_reports_ok_for_fresh_reset_state():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(session, days=7)

    assert report["status"] == "OK"
    assert report["summary"]["open_buy_count"] == 0
    assert report["summary"]["pending_confirm_count"] == 0
    assert report["summary"]["account_baseline_count"] == 1
    assert report["summary"]["account_equity_snapshot_count"] == 1
    assert report["summary"]["performance_trade_count"] == 0
    assert report["summary"]["unpaired_sell_count"] == 0
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["account_baseline_seeded"]["status"] == "OK"
    assert checks["account_snapshot_seeded"]["status"] == "OK"


@pytest.mark.asyncio
async def test_lifecycle_integrity_warns_when_reset_readiness_missing():
    from tests.conftest import TestAsyncSessionLocal

    async with TestAsyncSessionLocal() as session:
        report = await TradeLifecycleIntegrityService().build_report(session, days=7)

    assert report["status"] == "WARN"
    assert report["summary"]["account_baseline_count"] == 0
    assert report["summary"]["account_equity_snapshot_count"] == 0
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["account_baseline_seeded"]["status"] == "WARN"
    assert checks["account_snapshot_seeded"]["status"] == "WARN"


@pytest.mark.asyncio
async def test_lifecycle_integrity_treats_confirm_failed_as_terminal_history():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        session.add(_trade(
            symbol="005930",
            side="BUY",
            status="CONFIRM_FAILED",
            quantity=100,
            entry_price=70_000,
            entry_at=now - timedelta(minutes=30),
            notes="CONFIRM_FAILED: 체결수량 0 (주문 취소됨)",
        ))
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(session, days=1)

    assert report["status"] == "OK"
    assert report["summary"]["confirm_failed_count"] == 1
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["confirm_failed"]["status"] == "OK"
    assert "종료 상태" in checks["confirm_failed"]["note"]


@pytest.mark.asyncio
async def test_lifecycle_integrity_flags_unpaired_sell_and_neutral_close():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        session.add(_trade(
            symbol="A005930",
            side="SELL",
            quantity=10,
            entry_price=0,
            exit_price=70_000,
            entry_at=now - timedelta(hours=1),
            exit_at=now - timedelta(hours=1),
        ))
        session.add(_trade(
            symbol="000660",
            side="BUY",
            quantity=5,
            entry_price=180_000,
            exit_price=180_000,
            pnl=0,
            entry_at=now - timedelta(hours=2),
            exit_at=now - timedelta(minutes=30),
            notes="HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        ))
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(session, days=1)

    assert report["status"] == "FAIL"
    assert report["summary"]["unpaired_sell_count"] == 1
    assert report["summary"]["unmatched_sell_quantity"] == 10
    assert report["summary"]["excluded_reconciliation_close_rows"] == 1
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["unpaired_sells"]["status"] == "FAIL"
    assert checks["neutral_closes"]["status"] == "OK"


@pytest.mark.asyncio
async def test_lifecycle_integrity_fails_when_db_open_buy_missing_from_broker():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        session.add(_trade(
            symbol="001780",
            side="BUY",
            quantity=4000,
            entry_price=3145,
            entry_at=now - timedelta(hours=1),
        ))
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(
            session,
            days=1,
            broker_position_snapshot={
                "provider": "KIWOOM",
                "holding_quantities": {},
                "pending_symbols": [],
            },
        )

    assert report["status"] == "FAIL"
    assert report["summary"]["open_buy_count"] == 1
    assert report["summary"]["broker_position_check_available"] is True
    assert report["summary"]["broker_missing_open_buy_count"] == 1
    assert report["summary"]["broker_missing_open_buy_quantity"] == 4000
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["broker_missing_open_buys"]["status"] == "FAIL"
    assert checks["broker_missing_open_buys"]["actual"] == 1
    assert checks["broker_missing_open_buys"]["details"][0]["stock_symbol"] == "001780"


@pytest.mark.asyncio
async def test_lifecycle_integrity_fails_when_broker_holding_exceeds_db_open_without_pending():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        session.add(_trade(
            symbol="066430",
            side="BUY",
            quantity=52,
            entry_price=3080,
            entry_at=now - timedelta(hours=1),
        ))
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(
            session,
            days=1,
            broker_position_snapshot={
                "provider": "KIWOOM",
                "holding_quantities": {"066430": 53},
                "pending_symbols": ["066430"],
            },
        )

    assert report["status"] == "FAIL"
    assert report["summary"]["broker_untracked_holding_count"] == 1
    assert report["summary"]["broker_untracked_holding_quantity"] == 1
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["broker_untracked_holdings"]["status"] == "FAIL"
    assert checks["broker_untracked_holdings"]["details"][0]["stock_symbol"] == "066430"
    assert checks["broker_untracked_holdings"]["details"][0]["extra_quantity"] == 1


@pytest.mark.asyncio
async def test_lifecycle_integrity_allows_broker_extra_holding_with_matching_db_pending():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        _seed_account_readiness(session, now=now)
        session.add(_trade(
            symbol="066430",
            side="BUY",
            quantity=52,
            entry_price=3080,
            entry_at=now - timedelta(hours=1),
        ))
        session.add(_trade(
            symbol="066430",
            side="BUY",
            status="PENDING_CONFIRM",
            quantity=3250,
            entry_price=3080,
            entry_at=now - timedelta(minutes=10),
        ))
        await session.commit()

        report = await TradeLifecycleIntegrityService().build_report(
            session,
            days=1,
            broker_position_snapshot={
                "provider": "KIWOOM",
                "holding_quantities": {"066430": 53},
                "pending_symbols": ["066430"],
            },
        )

    assert report["status"] == "WARN"
    assert report["summary"]["pending_confirm_count"] == 1
    assert report["summary"]["broker_untracked_holding_count"] == 0
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["pending_confirms"]["status"] == "WARN"
    assert checks["broker_untracked_holdings"]["status"] == "OK"
