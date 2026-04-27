from datetime import datetime
from types import SimpleNamespace

import pytest

from models.trade_result import TradeResult
from repositories.trade_result_repository import TradeResultRepository
from trading.models import AccountBalance, HoldingInfo, PendingOrderInfo
from util.time_util import KST


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 4, 9, hour, minute, second, tzinfo=KST)


def _balance(
    *,
    total_asset: float,
    cash: float = 0.0,
    stock_value: float = 0.0,
    total_pnl: float = 0.0,
    total_pnl_rate: float = 0.0,
) -> AccountBalance:
    return AccountBalance(
        total_asset=total_asset,
        cash=cash,
        stock_value=stock_value,
        total_pnl=total_pnl,
        total_pnl_rate=total_pnl_rate,
    )


@pytest.mark.asyncio
async def test_account_equity_service_creates_baseline_once_per_trading_day():
    from repositories.account_day_baseline_repository import AccountDayBaselineRepository
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(9, 5),
    )

    first = service.build_state(
        _balance(total_asset=1_000_000, cash=250_000, stock_value=750_000, total_pnl=120_000, total_pnl_rate=12.0),
        holdings=[HoldingInfo(symbol="005930", name="삼성전자", quantity=7, avg_buy_price=70_000, current_price=72_000, pnl=14_000, pnl_rate=2.86)],
        pending_orders=[PendingOrderInfo(order_id="1", symbol="005930", name="삼성전자", side="매수", order_qty=7, filled_qty=0, remaining_qty=7, order_price=71_000, order_time="090100")],
        captured_at=_dt(9, 5),
    )
    second = service.build_state(
        _balance(total_asset=1_050_000, cash=200_000, stock_value=850_000, total_pnl=170_000, total_pnl_rate=16.19),
        holdings=[],
        pending_orders=[],
        captured_at=_dt(10, 0),
    )

    baseline = await service.ensure_day_baseline(first, baseline_source="SCHEDULER")
    again = await service.ensure_day_baseline(second, baseline_source="ADMIN")

    async with TestAsyncSessionLocal() as session:
        rows = await AccountDayBaselineRepository(session).list_recent(limit=5)

    assert baseline.id == again.id
    assert len(rows) == 1
    assert rows[0].trading_date.isoformat() == "2026-04-09"
    assert rows[0].baseline_total_asset == pytest.approx(1_000_000)
    assert rows[0].baseline_holding_count == 1
    assert rows[0].baseline_pending_order_count == 1
    assert rows[0].baseline_source == "SCHEDULER"


@pytest.mark.asyncio
async def test_account_equity_service_builds_session_metrics_from_baseline_and_snapshots():
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(13, 30),
    )

    open_state = service.build_state(
        _balance(total_asset=980_000, cash=280_000, stock_value=700_000, total_pnl=95_000, total_pnl_rate=10.74),
        captured_at=_dt(9, 0),
    )
    await service.ensure_day_baseline(open_state, baseline_source="MARKET_OPEN")
    await service.record_snapshot(open_state, session_phase="OPENING")
    await service.record_snapshot(
        service.build_state(
            _balance(total_asset=1_015_000, cash=240_000, stock_value=775_000, total_pnl=130_000, total_pnl_rate=14.69),
            captured_at=_dt(10, 30),
        ),
        session_phase="INTRADAY",
    )
    await service.record_snapshot(
        service.build_state(
            _balance(total_asset=972_000, cash=210_000, stock_value=762_000, total_pnl=87_000, total_pnl_rate=9.83),
            captured_at=_dt(11, 15),
        ),
        session_phase="INTRADAY",
    )

    async with TestAsyncSessionLocal() as session:
        session.add(TradeResult(
            stock_symbol="005930",
            stock_name="삼성전자",
            side="BUY",
            strategy_type="STABLE_SHORT",
            entry_price=70_000,
            exit_price=73_000,
            quantity=10,
            pnl=25_000,
            return_pct=3.57,
            is_win=True,
            status="CONFIRMED",
            entry_at=_dt(9, 5),
            exit_at=_dt(12, 10),
        ))
        await session.commit()

    payload = await service.build_balance_payload(
        _balance(total_asset=1_000_000, cash=230_000, stock_value=770_000, total_pnl=120_000, total_pnl_rate=12.0),
        captured_at=_dt(13, 30),
    )

    assert payload["total_asset"] == pytest.approx(1_000_000)
    assert payload["session_metrics"]["available"] is True
    assert payload["session_metrics"]["baseline_total_asset"] == pytest.approx(980_000)
    assert payload["session_metrics"]["asset_delta"] == pytest.approx(20_000)
    assert payload["session_metrics"]["asset_delta_rate"] == pytest.approx(2.04, abs=0.01)
    assert payload["session_metrics"]["realized_today_pnl"] == pytest.approx(25_000)
    assert payload["session_metrics"]["broker_unrealized_pnl"] == pytest.approx(120_000)
    assert payload["session_metrics"]["daily_unrealized_delta"] == pytest.approx(-5_000)
    assert payload["session_metrics"]["cash_or_snapshot_delta"] == pytest.approx(-125_000)
    assert payload["session_metrics"]["current_exposure_krw"] == pytest.approx(770_000)
    assert payload["session_metrics"]["current_exposure_pct"] == pytest.approx(77.0)
    assert payload["session_metrics"]["market_exposure"] is True
    assert payload["session_metrics"]["risk_label"] == "EXPOSED_PROFIT"
    assert payload["session_metrics"]["intraday_high_asset"] == pytest.approx(1_015_000)
    assert payload["session_metrics"]["intraday_low_asset"] == pytest.approx(972_000)
    assert payload["session_metrics"]["snapshot_freshness_status"] == "STALE"
    assert payload["session_metrics"]["snapshot_stale_blocks_buy"] is True


@pytest.mark.asyncio
async def test_account_equity_service_marks_off_session_stale_snapshot_without_buy_block():
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(17, 30),
    )

    open_state = service.build_state(
        _balance(total_asset=1_000_000, cash=1_000_000, stock_value=0),
        captured_at=_dt(9, 0),
    )
    await service.ensure_day_baseline(open_state, baseline_source="MARKET_OPEN")
    await service.record_snapshot(open_state, session_phase="OPENING")

    payload = await service.build_balance_payload(
        _balance(total_asset=1_000_000, cash=1_000_000, stock_value=0),
        captured_at=_dt(17, 30),
    )

    assert payload["session_metrics"]["is_stale"] is True
    assert payload["session_metrics"]["snapshot_freshness_status"] == "OFF_SESSION_STALE"
    assert payload["session_metrics"]["snapshot_stale_reason"] == "off_session_auto_trading_disabled"
    assert payload["session_metrics"]["snapshot_stale_blocks_buy"] is False


@pytest.mark.asyncio
async def test_account_equity_service_classifies_cash_snapshot_delta_without_exposure():
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(10, 30),
    )

    open_state = service.build_state(
        _balance(total_asset=1_000_000, cash=1_000_000, stock_value=0, total_pnl=0, total_pnl_rate=0),
        captured_at=_dt(9, 0),
    )
    await service.ensure_day_baseline(open_state, baseline_source="MARKET_OPEN")

    payload = await service.build_balance_payload(
        _balance(total_asset=995_000, cash=995_000, stock_value=0, total_pnl=0, total_pnl_rate=0),
        captured_at=_dt(10, 30),
    )

    assert payload["session_metrics"]["market_exposure"] is False
    assert payload["session_metrics"]["current_exposure_krw"] == pytest.approx(0)
    assert payload["session_metrics"]["cash_or_snapshot_delta"] == pytest.approx(-5_000)
    assert payload["session_metrics"]["risk_label"] == "CASH_OR_SNAPSHOT_VARIANCE"


@pytest.mark.asyncio
async def test_account_equity_service_returns_unavailable_metrics_without_baseline():
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(9, 45),
    )

    payload = await service.build_balance_payload(
        _balance(total_asset=1_000_000, cash=300_000, stock_value=700_000, total_pnl=50_000, total_pnl_rate=5.0),
        captured_at=_dt(9, 45),
    )

    assert payload["session_metrics"]["available"] is False
    assert payload["session_metrics"]["asset_delta"] == pytest.approx(0.0)
    assert payload["session_metrics"]["daily_unrealized_delta"] == pytest.approx(0.0)
    assert payload["session_metrics"]["current_exposure_krw"] == pytest.approx(700_000)
    assert payload["session_metrics"]["market_exposure"] is True
    assert payload["session_metrics"]["intraday_high_asset"] == pytest.approx(1_000_000)
    assert payload["session_metrics"]["intraday_low_asset"] == pytest.approx(1_000_000)


@pytest.mark.asyncio
async def test_account_equity_service_capture_and_record_current_snapshot(monkeypatch):
    from repositories.account_day_baseline_repository import AccountDayBaselineRepository
    from repositories.account_equity_snapshot_repository import AccountEquitySnapshotRepository
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    class FakeBrokerAdapter:
        async def get_balance(self) -> AccountBalance:
            return _balance(
                total_asset=1_250_000,
                cash=450_000,
                stock_value=800_000,
                total_pnl=140_000,
                total_pnl_rate=12.6,
            )

        async def get_holdings(self) -> list[HoldingInfo]:
            return [
                HoldingInfo(
                    symbol="005930",
                    name="삼성전자",
                    quantity=7,
                    avg_buy_price=70_000,
                    current_price=72_000,
                    pnl=14_000,
                    pnl_rate=2.86,
                )
            ]

        async def get_pending_orders(self) -> list[PendingOrderInfo]:
            return [
                PendingOrderInfo(
                    order_id="2001",
                    symbol="005930",
                    name="삼성전자",
                    side="매도",
                    order_qty=7,
                    filled_qty=0,
                    remaining_qty=7,
                    order_price=72_000,
                    order_time="101000",
                )
            ]

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(10, 10),
    )
    monkeypatch.setattr("services.account_equity_service.get_broker_adapter", lambda: FakeBrokerAdapter())

    snapshot = await service.capture_and_record_current(
        session_phase="INTRADAY",
        detail={"reason": "scheduler"},
    )

    async with TestAsyncSessionLocal() as session:
        baselines = await AccountDayBaselineRepository(session).list_recent(limit=5)
        snapshots = await AccountEquitySnapshotRepository(session).list_recent(limit=5)

    assert snapshot is not None
    assert len(baselines) == 1
    assert len(snapshots) == 1
    assert baselines[0].baseline_total_asset == pytest.approx(1_250_000)
    assert baselines[0].baseline_holding_count == 1
    assert snapshots[0].session_phase == "INTRADAY"
    assert snapshots[0].pending_order_count == 1
