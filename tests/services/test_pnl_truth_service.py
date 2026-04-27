from datetime import date, datetime

import pytest

from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from models.trade_result import TradeResult
from services.pnl_truth_service import PnlTruthService


@pytest.mark.asyncio
async def test_pnl_truth_service_separates_trade_pnl_broker_unrealized_and_asset_delta():
    from tests.conftest import TestAsyncSessionLocal

    trading_date = date(2026, 4, 22)
    async with TestAsyncSessionLocal() as session:
        session.add(AccountDayBaseline(
            trading_date=trading_date,
            baseline_at=datetime(2026, 4, 22, 9, 0),
            baseline_total_asset=520_000_000,
            baseline_cash=180_000_000,
            baseline_stock_value=340_000_000,
            baseline_total_unrealized_pnl=-1_500_000,
            baseline_holding_count=6,
            baseline_pending_order_count=2,
            baseline_source="PRE_MARKET",
        ))
        session.add(AccountEquitySnapshot(
            trading_date=trading_date,
            captured_at=datetime(2026, 4, 22, 13, 5),
            session_phase="INTRADAY",
            total_asset=527_064_565,
            cash=181_724_859,
            stock_value=341_909_010,
            total_unrealized_pnl=-2_704_805,
            total_unrealized_pnl_rate=-1.32,
            holding_count=6,
            pending_order_count=2,
        ))
        session.add(TradeResult(
            stock_symbol="001250",
            stock_name="GS글로벌",
            side="BUY",
            strategy_type="STABLE_SHORT",
            entry_price=3600,
            quantity=100,
            pnl=0.0,
            return_pct=0.0,
            status="CONFIRMED",
            entry_at=datetime(2026, 4, 22, 9, 10),
            exit_at=None,
        ))
        await session.commit()

        summary = await PnlTruthService().build_summary(session, trading_date=trading_date)

    assert summary == {
        "trading_date": "2026-04-22",
        "sample_status": "INSUFFICIENT_CLOSED_TRADE_SAMPLE",
        "account_pnl_sample_status": "UNRECONCILED_ACCOUNT_PNL",
        "realized_trade_pnl": 0.0,
        "closed_trade_count": 0,
        "unrealized_broker_pnl": -2_704_805.0,
        "unrealized_broker_pnl_rate": -1.32,
        "total_asset": 527_064_565.0,
        "baseline_total_asset": 520_000_000.0,
        "total_asset_delta": 7_064_565.0,
        "total_asset_delta_rate": 1.36,
        "cash_or_snapshot_delta": 9_769_370.0,
        "pnl_reconciliation_status": "UNEXPLAINED_ASSET_DELTA",
        "pnl_reconciliation_message": "총자산 변화 중 DB 실현손익/브로커 평가손익으로 설명되지 않는 차이가 있습니다.",
        "holding_count": 6,
        "pending_order_count": 2,
        "source": {
            "realized_trade_pnl": "trade_results.closed_buy",
            "unrealized_broker_pnl": "account_equity_snapshots.latest",
            "total_asset_delta": "account_day_baselines + account_equity_snapshots.latest",
            "cash_or_snapshot_delta": "total_asset_delta - realized_trade_pnl - unrealized_broker_pnl",
        },
    }
