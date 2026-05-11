from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from models.trade_result import TradeResult
from services.trade_close_reconciliation_service import TradeCloseReconciliationService


def _trade(
    *,
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    exit_price: float = 0.0,
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
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="HOLDINGS_CHECK" if side == "SELL" else "",
        ai_recommendation="BUY",
        ai_confidence=0.7,
        market="KRX",
        market_regime="NORMAL",
        status="CONFIRMED",
        entry_at=entry_at,
        exit_at=exit_at,
        notes=notes,
    )


@pytest.mark.asyncio
async def test_close_reconciliation_matches_prefixed_sell_to_neutral_closed_buy_fifo():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        session.add(_trade(
            symbol="006340",
            side="BUY",
            quantity=100,
            entry_price=8_000,
            entry_at=now - timedelta(hours=3),
            exit_at=now - timedelta(minutes=5),
            notes="HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        ))
        session.add(_trade(
            symbol="A006340",
            side="SELL",
            quantity=60,
            entry_price=0,
            exit_price=8_200,
            entry_at=now - timedelta(hours=1),
            exit_at=now - timedelta(hours=1),
        ))
        await session.commit()

        report = await TradeCloseReconciliationService().build_dry_run(session, days=1)

    assert report["summary"]["sell_execution_count"] == 1
    assert report["summary"]["buy_candidate_count"] == 1
    assert report["summary"]["matched_sell_count"] == 1
    assert report["summary"]["matched_quantity"] == 60
    assert report["summary"]["estimated_pnl"] == 12_000
    assert report["matches"][0]["sell_symbol_raw"] == "A006340"
    assert report["matches"][0]["sell_symbol"] == "006340"
    assert report["matches"][0]["matches"][0]["close_quantity"] == 60
    assert report["remaining_buy_candidates"][0]["remaining_quantity"] == 40


@pytest.mark.asyncio
async def test_close_reconciliation_reports_unmatched_sell_quantity():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        session.add(_trade(
            symbol="A047040",
            side="SELL",
            quantity=850,
            entry_price=0,
            exit_price=33_925,
            entry_at=now - timedelta(hours=1),
            exit_at=now - timedelta(hours=1),
        ))
        await session.commit()

        report = await TradeCloseReconciliationService().build_dry_run(session, days=1)

    assert report["summary"]["sell_execution_count"] == 1
    assert report["summary"]["matched_sell_count"] == 0
    assert report["summary"]["unmatched_sell_count"] == 1
    assert report["summary"]["unmatched_sell_quantity"] == 850
    assert report["unmatched_sells"][0]["sell_symbol"] == "047040"


@pytest.mark.asyncio
async def test_apply_reconciliation_splits_partial_buy_lot_and_updates_pnl():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        buy = _trade(
            symbol="006340",
            side="BUY",
            quantity=100,
            entry_price=8_000,
            entry_at=now - timedelta(hours=3),
            exit_at=now - timedelta(minutes=5),
            notes="HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        )
        session.add(buy)
        session.add(_trade(
            symbol="A006340",
            side="SELL",
            quantity=60,
            entry_price=0,
            exit_price=8_200,
            entry_at=now - timedelta(hours=1),
            exit_at=now - timedelta(hours=1),
        ))
        await session.commit()

        result = await TradeCloseReconciliationService().apply_reconciliation(session, days=1)
        await session.commit()

        rows = list((await session.execute(
            select(TradeResult).where(TradeResult.stock_symbol == "006340").order_by(TradeResult.quantity.asc())
        )).scalars().all())

    assert result["summary"]["applied_sell_count"] == 1
    assert result["summary"]["updated_buy_lot_count"] == 1
    assert result["summary"]["created_buy_lot_count"] == 1
    assert result["summary"]["applied_pnl"] == 12_000
    assert [row.quantity for row in rows] == [40, 60]
    closed = rows[1]
    assert closed.exit_price == 8_200
    assert closed.pnl == 12_000
    assert closed.return_pct == 2.5
    assert "CLOSE_RECONCILIATION_APPLY" in closed.notes


@pytest.mark.asyncio
async def test_apply_reconciliation_skips_sell_with_unmatched_quantity_by_default():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    async with TestAsyncSessionLocal() as session:
        session.add(_trade(
            symbol="006340",
            side="BUY",
            quantity=50,
            entry_price=8_000,
            entry_at=now - timedelta(hours=3),
            exit_at=now - timedelta(minutes=5),
            notes="HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        ))
        session.add(_trade(
            symbol="A006340",
            side="SELL",
            quantity=60,
            entry_price=0,
            exit_price=8_200,
            entry_at=now - timedelta(hours=1),
            exit_at=now - timedelta(hours=1),
        ))
        await session.commit()

        result = await TradeCloseReconciliationService().apply_reconciliation(session, days=1)

    assert result["summary"]["applied_sell_count"] == 0
    assert result["summary"]["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "sell_has_unmatched_quantity"
