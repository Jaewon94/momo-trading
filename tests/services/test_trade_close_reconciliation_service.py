from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from models.trade_result import TradeResult
from services.trade_close_reconciliation_service import TradeCloseReconciliationService


def _trade(
    *,
    order_id: str | None = None,
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    exit_price: float = 0.0,
    entry_at: datetime,
    exit_at: datetime | None = None,
    exit_reason: str | None = None,
    notes: str | None = None,
) -> TradeResult:
    return TradeResult(
        order_id=order_id,
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
        exit_reason=exit_reason if exit_reason is not None else ("HOLDINGS_CHECK" if side == "SELL" else ""),
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
async def test_close_reconciliation_ignores_sell_already_reflected_in_buy_lot():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    closed_at = now - timedelta(minutes=30)
    async with TestAsyncSessionLocal() as session:
        session.add(_trade(
            symbol="090710",
            side="BUY",
            quantity=160,
            entry_price=13_790,
            exit_price=14_160,
            entry_at=now - timedelta(hours=2),
            exit_at=closed_at,
            exit_reason="PARTIAL_TAKE_PROFIT",
        ))
        session.add(_trade(
            symbol="090710",
            side="SELL",
            quantity=160,
            entry_price=0,
            exit_price=14_160,
            entry_at=closed_at,
            exit_at=closed_at,
            exit_reason="PARTIAL_TAKE_PROFIT",
        ))
        await session.commit()

        report = await TradeCloseReconciliationService().build_dry_run(session, days=1)

    assert report["summary"]["raw_sell_execution_count"] == 1
    assert report["summary"]["sell_execution_count"] == 0
    assert report["summary"]["reflected_sell_count"] == 1
    assert report["summary"]["reflected_sell_quantity"] == 160
    assert report["summary"]["unmatched_sell_count"] == 0


@pytest.mark.asyncio
async def test_close_reconciliation_ignores_sell_reflected_by_repair_note():
    from tests.conftest import TestAsyncSessionLocal

    now = datetime.now()
    sell_at = now - timedelta(minutes=30)
    async with TestAsyncSessionLocal() as session:
        session.add(_trade(
            symbol="048770",
            side="BUY",
            quantity=450,
            entry_price=5_540,
            exit_price=6_930,
            entry_at=now - timedelta(days=1),
            exit_at=sell_at + timedelta(minutes=2),
            exit_reason="GAP_CHECK",
            notes="CLOSE_RECONCILIATION_APPLY: repaired from broker-confirmed sell order 0051955",
        ))
        session.add(_trade(
            symbol="048770",
            side="BUY",
            quantity=1710,
            entry_price=5_540,
            exit_price=6_930,
            entry_at=now - timedelta(days=1),
            exit_at=sell_at,
            exit_reason="GAP_CHECK",
        ))
        session.add(_trade(
            order_id="0051955",
            symbol="048770",
            side="SELL",
            quantity=2160,
            entry_price=0,
            exit_price=6_930,
            entry_at=sell_at,
            exit_at=sell_at,
            exit_reason="GAP_CHECK",
        ))
        await session.commit()

        report = await TradeCloseReconciliationService().build_dry_run(session, days=2)

    assert report["summary"]["raw_sell_execution_count"] == 1
    assert report["summary"]["sell_execution_count"] == 0
    assert report["summary"]["reflected_sell_count"] == 1
    assert report["summary"]["reflected_sell_quantity"] == 2160
    assert report["summary"]["unmatched_sell_count"] == 0


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
