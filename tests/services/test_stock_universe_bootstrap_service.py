from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from models.stock import Stock
from services.stock_universe_bootstrap_service import StockUniverseBootstrapService
from tests.conftest import TestAsyncSessionLocal


class FakeBroker:
    async def get_holdings(self):
        return [
            SimpleNamespace(symbol="A005930", name="삼성전자"),
            SimpleNamespace(symbol="000660", name="SK하이닉스"),
        ]

    async def get_pending_orders(self):
        return [
            SimpleNamespace(symbol="005930", name="삼성전자"),
            SimpleNamespace(symbol="035420", name="NAVER"),
        ]

    async def get_volume_rank(self):
        return [
            {"symbol": "042700", "name": "한미반도체", "category": "반도체"},
            {"code": "035420", "stock_name": "NAVER"},
        ]

    async def get_fluctuation_rank(self, sort: str):
        if sort == "top":
            return [{"symbol": "006400", "name": "삼성SDI", "sector": "2차전지"}]
        return [{"symbol": "005930", "name": "삼성전자"}]


@pytest.mark.asyncio
async def test_stock_universe_bootstrap_dry_run_does_not_write() -> None:
    service = StockUniverseBootstrapService()

    async with TestAsyncSessionLocal() as session:
        summary = await service.process(session, broker=FakeBroker(), apply=False)

        assert summary["status"] == "SUCCESS"
        assert summary["apply"] is False
        assert summary["candidate_count"] == 5
        assert summary["created_count"] == 5
        assert summary["updated_count"] == 0

        count = await session.scalar(select(func.count()).select_from(Stock))
        assert count == 0


@pytest.mark.asyncio
async def test_stock_universe_bootstrap_upserts_normalized_symbols() -> None:
    service = StockUniverseBootstrapService()

    async with TestAsyncSessionLocal() as session:
        session.add(Stock(symbol="035420", name="네이버", market="KRX", is_active=False))
        await session.flush()

        summary = await service.process(session, broker=FakeBroker(), apply=True)

        assert summary["status"] == "SUCCESS"
        assert summary["apply"] is True
        assert summary["candidate_count"] == 5
        assert summary["created_count"] == 4
        assert summary["updated_count"] == 1
        assert summary["source_counts"]["holdings"] == 2
        assert summary["source_counts"]["pending_orders"] == 2
        assert summary["source_counts"]["volume_rank"] == 2
        assert summary["source_counts"]["fluctuation_top"] == 1
        assert summary["source_counts"]["fluctuation_bottom"] == 1

        rows = (await session.execute(select(Stock).order_by(Stock.symbol))).scalars().all()
        assert [(row.symbol, row.name, row.market, row.category, row.is_active) for row in rows] == [
            ("000660", "SK하이닉스", "KRX", None, True),
            ("005930", "삼성전자", "KRX", None, True),
            ("006400", "삼성SDI", "KRX", "2차전지", True),
            ("035420", "NAVER", "KRX", None, True),
            ("042700", "한미반도체", "KRX", "반도체", True),
        ]
