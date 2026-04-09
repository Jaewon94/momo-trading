from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_equity_snapshot import AccountEquitySnapshot
from repositories.async_base_repository import AsyncBaseRepository


class AccountEquitySnapshotRepository(AsyncBaseRepository[AccountEquitySnapshot]):
    def __init__(self, db: AsyncSession):
        super().__init__(AccountEquitySnapshot, db)

    async def list_recent(self, limit: int = 50) -> list[AccountEquitySnapshot]:
        result = await self.db.execute(
            select(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_by_trading_date(self, trading_date: date) -> AccountEquitySnapshot | None:
        result = await self.db.execute(
            select(AccountEquitySnapshot)
            .where(AccountEquitySnapshot.trading_date == trading_date)
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_asset_range_for_date(self, trading_date: date) -> tuple[float | None, float | None]:
        result = await self.db.execute(
            select(
                func.max(AccountEquitySnapshot.total_asset),
                func.min(AccountEquitySnapshot.total_asset),
            )
            .where(AccountEquitySnapshot.trading_date == trading_date)
        )
        high, low = result.one()
        return high, low
