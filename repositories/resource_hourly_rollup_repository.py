from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.resource_hourly_rollup import ResourceHourlyRollup
from repositories.async_base_repository import AsyncBaseRepository


class ResourceHourlyRollupRepository(AsyncBaseRepository[ResourceHourlyRollup]):
    def __init__(self, db: AsyncSession):
        super().__init__(ResourceHourlyRollup, db)

    async def list_recent(self, limit: int = 100) -> list[ResourceHourlyRollup]:
        result = await self.db.execute(
            select(ResourceHourlyRollup)
            .order_by(ResourceHourlyRollup.bucket_start.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
