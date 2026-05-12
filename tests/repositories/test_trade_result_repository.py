from datetime import date, datetime

import pytest

from models.trade_result import TradeResult
from repositories.trade_result_repository import TradeResultRepository
from tests.conftest import TestAsyncSessionLocal


def _trade(symbol: str, *, status: str = "CONFIRMED") -> TradeResult:
    return TradeResult(
        stock_symbol=symbol,
        stock_name="삼성전자",
        side="BUY",
        strategy_type="STABLE_SHORT",
        entry_price=70_000.0,
        exit_price=0.0,
        quantity=2,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        ai_recommendation="BUY",
        ai_confidence=0.72,
        market="KRX",
        market_regime="THEME",
        entry_at=datetime(2026, 4, 24, 9, 5),
        status=status,
    )


@pytest.mark.asyncio
async def test_trade_result_repository_normalizes_prefixed_symbol_for_open_buy():
    async with TestAsyncSessionLocal() as session:
        session.add(_trade("005930"))
        await session.commit()

        repo = TradeResultRepository(session)

        result = await repo.get_open_buy("A005930")
        assert result is not None
        assert result.stock_symbol == "005930"

        all_open = await repo.get_all_open_buys("A005930")
        assert [item.stock_symbol for item in all_open] == ["005930"]


@pytest.mark.asyncio
async def test_trade_result_repository_normalizes_prefixed_symbol_for_history_lookup():
    async with TestAsyncSessionLocal() as session:
        session.add(_trade("005930"))
        await session.commit()

        repo = TradeResultRepository(session)

        rows = await repo.get_by_symbol("A005930")
        assert len(rows) == 1
        assert rows[0].stock_symbol == "005930"


@pytest.mark.asyncio
async def test_completed_by_date_excludes_neutral_reconciliation_closes():
    completed_at = datetime(2026, 4, 24, 10, 30)
    realized = _trade("005930")
    realized.exit_at = completed_at
    realized.exit_price = 71_000.0
    realized.pnl = 2_000.0
    realized.return_pct = 1.4
    realized.exit_reason = "TAKE_PROFIT"

    reconciled = _trade("003280")
    reconciled.exit_at = completed_at
    reconciled.exit_price = reconciled.entry_price
    reconciled.pnl = 0.0
    reconciled.return_pct = 0.0
    reconciled.exit_reason = "BROKER_HOLDING_MISSING"
    reconciled.notes = "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"
    applied = _trade("452430")
    applied.exit_at = completed_at
    applied.exit_price = 50_900.0
    applied.pnl = 1_457_450.0
    applied.return_pct = 11.2568
    applied.exit_reason = "SELL_RECONCILIATION"
    applied.notes = (
        "CLOSE_RECONCILIATION_APPLY: sell_id=sell-2 | "
        "previous=HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"
    )

    async with TestAsyncSessionLocal() as session:
        session.add_all([realized, reconciled, applied])
        await session.commit()

        repo = TradeResultRepository(session)
        rows = await repo.get_completed_by_date(date(2026, 4, 24))

    assert [row.stock_symbol for row in rows] == ["005930", "452430"]


@pytest.mark.asyncio
async def test_opened_by_date_excludes_neutral_reconciliation_closes():
    opened_at = datetime(2026, 4, 24, 9, 5)
    open_trade = _trade("005930")
    open_trade.entry_at = opened_at

    reconciled = _trade("003280")
    reconciled.entry_at = opened_at
    reconciled.exit_at = datetime(2026, 4, 24, 10, 30)
    reconciled.exit_reason = "BROKER_HOLDING_MISSING"
    reconciled.notes = "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"

    async with TestAsyncSessionLocal() as session:
        session.add_all([open_trade, reconciled])
        await session.commit()

        repo = TradeResultRepository(session)
        rows = await repo.get_opened_by_date(date(2026, 4, 24))

    assert [row.stock_symbol for row in rows] == ["005930"]
