from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.execution_metric import ExecutionMetric
from repositories.async_base_repository import AsyncBaseRepository


class ExecutionMetricRepository(AsyncBaseRepository[ExecutionMetric]):
    def __init__(self, db: AsyncSession):
        super().__init__(ExecutionMetric, db)

    async def list_recent(self, limit: int = 100) -> list[ExecutionMetric]:
        result = await self.db.execute(
            select(ExecutionMetric)
            .order_by(ExecutionMetric.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
