from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.execution_metric_hourly_rollup import ExecutionMetricHourlyRollup
from repositories.async_base_repository import AsyncBaseRepository


class ExecutionMetricHourlyRollupRepository(AsyncBaseRepository[ExecutionMetricHourlyRollup]):
    def __init__(self, db: AsyncSession):
        super().__init__(ExecutionMetricHourlyRollup, db)

    async def list_recent(self, limit: int = 100) -> list[ExecutionMetricHourlyRollup]:
        result = await self.db.execute(
            select(ExecutionMetricHourlyRollup)
            .order_by(ExecutionMetricHourlyRollup.bucket_start.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
