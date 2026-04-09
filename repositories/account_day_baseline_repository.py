from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_day_baseline import AccountDayBaseline
from repositories.async_base_repository import AsyncBaseRepository


class AccountDayBaselineRepository(AsyncBaseRepository[AccountDayBaseline]):
    def __init__(self, db: AsyncSession):
        super().__init__(AccountDayBaseline, db)

    async def get_by_trading_date(self, trading_date: date) -> AccountDayBaseline | None:
        return await self.filter_by_one(trading_date=trading_date)

    async def list_recent(self, limit: int = 30) -> list[AccountDayBaseline]:
        result = await self.db.execute(
            select(AccountDayBaseline)
            .order_by(AccountDayBaseline.trading_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
