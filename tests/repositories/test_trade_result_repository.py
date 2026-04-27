from datetime import datetime

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
