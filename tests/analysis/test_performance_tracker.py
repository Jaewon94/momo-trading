from datetime import datetime

import pytest

from analysis.feedback.performance_tracker import PerformanceTracker
from models.trade_result import TradeResult
from tests.conftest import TestAsyncSessionLocal


def _closed_trade(
    trade_id: str,
    *,
    pnl: float,
    is_win: bool,
    exit_reason: str = "SIGNAL",
    exit_at: datetime | None = None,
) -> TradeResult:
    return TradeResult(
        id=trade_id,
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="STABLE_SHORT",
        entry_price=70000.0,
        exit_price=70100.0,
        quantity=1,
        pnl=pnl,
        return_pct=0.14 if pnl > 0 else -0.14,
        is_win=is_win,
        hold_days=1,
        exit_reason=exit_reason,
        status="CONFIRMED",
        entry_at=datetime(2026, 4, 27, 9, 0),
        exit_at=exit_at or datetime(2026, 4, 27, 10, 0),
    )


@pytest.mark.asyncio
async def test_performance_tracker_excludes_broker_holding_missing_reconciliation_from_losses() -> None:
    async with TestAsyncSessionLocal() as session:
        session.add_all([
            _closed_trade(
                "reconciled-1",
                pnl=0.0,
                is_win=False,
                exit_reason="BROKER_HOLDING_MISSING",
                exit_at=datetime(2026, 4, 27, 10, 3),
            ),
            _closed_trade(
                "loss-1",
                pnl=-1000.0,
                is_win=False,
                exit_reason="SIGNAL",
                exit_at=datetime(2026, 4, 27, 10, 2),
            ),
            _closed_trade(
                "win-1",
                pnl=1000.0,
                is_win=True,
                exit_reason="SIGNAL",
                exit_at=datetime(2026, 4, 27, 10, 1),
            ),
        ])
        await session.commit()

        tracker = PerformanceTracker(session)

        assert await tracker.get_consecutive_losses() == 1
        recent_losses = await tracker.get_recent_losses(limit=10)
        assert [trade.id for trade in recent_losses] == ["loss-1"]

        stats = await tracker.get_strategy_stats("STABLE_SHORT")
        assert stats.total_trades == 2
        assert stats.wins == 1
        assert stats.losses == 1
