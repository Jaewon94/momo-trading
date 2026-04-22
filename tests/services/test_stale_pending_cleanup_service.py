from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from models.trade_result import TradeResult
from services.stale_pending_cleanup_service import StalePendingCleanupService
from tests.conftest import TestAsyncSessionLocal
from trading.enums import OrderConfirmStatus
from trading.models import PendingOrderInfo


def _pending_trade(
    *,
    trade_id: str,
    order_id: str,
    symbol: str,
    created_at: datetime,
) -> TradeResult:
    return TradeResult(
        id=trade_id,
        order_id=order_id,
        stock_symbol=symbol,
        stock_name=f"{symbol} db",
        side="BUY",
        strategy_type="SCALP",
        entry_price=1000.0,
        quantity=10,
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
        notes="PENDING_CONFIRM",
        entry_at=created_at,
        created_at=created_at,
    )


def _broker_pending(order_id: str, symbol: str) -> PendingOrderInfo:
    return PendingOrderInfo(
        order_id=order_id,
        symbol=symbol,
        name=f"{symbol} broker",
        side="매수",
        order_qty=10,
        filled_qty=0,
        remaining_qty=10,
        order_price=1000.0,
        order_time="091500",
    )


@pytest.mark.asyncio
async def test_stale_pending_cleanup_dry_run_does_not_mutate_db() -> None:
    now = datetime(2026, 4, 22, 10, 0)
    service = StalePendingCleanupService(stale_after=timedelta(minutes=30))

    async with TestAsyncSessionLocal() as session:
        stale = _pending_trade(
            trade_id="stale-db",
            order_id="STALE",
            symbol="003280",
            created_at=datetime(2026, 4, 22, 8, 0),
        )
        active = _pending_trade(
            trade_id="active-db",
            order_id="ACTIVE",
            symbol="005930",
            created_at=datetime(2026, 4, 22, 9, 45),
        )
        session.add_all([stale, active])
        await session.commit()

        result = await service.cleanup(
            session,
            broker_pending_orders=[_broker_pending("ACTIVE", "005930")],
            dry_run=True,
            now=now,
        )

        await session.refresh(stale)
        await session.refresh(active)

    assert result["mode"] == "dry_run"
    assert result["summary"]["eligible_count"] == 1
    assert result["summary"]["updated_count"] == 0
    assert result["candidates"][0]["trade_id"] == "stale-db"
    assert stale.status == OrderConfirmStatus.PENDING_CONFIRM.value
    assert active.status == OrderConfirmStatus.PENDING_CONFIRM.value


@pytest.mark.asyncio
async def test_stale_pending_cleanup_apply_marks_only_eligible_rows_failed() -> None:
    now = datetime(2026, 4, 22, 10, 0)
    service = StalePendingCleanupService(stale_after=timedelta(minutes=30))

    async with TestAsyncSessionLocal() as session:
        stale = _pending_trade(
            trade_id="stale-db",
            order_id="STALE",
            symbol="003280",
            created_at=datetime(2026, 4, 22, 8, 0),
        )
        active = _pending_trade(
            trade_id="active-db",
            order_id="ACTIVE",
            symbol="005930",
            created_at=datetime(2026, 4, 22, 9, 45),
        )
        session.add_all([stale, active])
        await session.commit()

        result = await service.cleanup(
            session,
            broker_pending_orders=[_broker_pending("ACTIVE", "005930")],
            dry_run=False,
            now=now,
        )
        await session.commit()

        rows = {
            row.id: row
            for row in (
                await session.execute(select(TradeResult).where(TradeResult.id.in_(["stale-db", "active-db"])))
            ).scalars()
        }

    assert result["mode"] == "apply"
    assert result["summary"]["eligible_count"] == 1
    assert result["summary"]["updated_count"] == 1
    assert rows["stale-db"].status == OrderConfirmStatus.CONFIRM_FAILED.value
    assert "stale pending reconciliation cleanup" in (rows["stale-db"].notes or "")
    assert rows["active-db"].status == OrderConfirmStatus.PENDING_CONFIRM.value
