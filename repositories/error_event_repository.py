from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.error_event import ErrorEvent
from repositories.async_base_repository import AsyncBaseRepository


class ErrorEventRepository(AsyncBaseRepository[ErrorEvent]):
    def __init__(self, db: AsyncSession):
        super().__init__(ErrorEvent, db)

    async def list_recent(self, limit: int = 100) -> list[ErrorEvent]:
        result = await self.db.execute(
            select(ErrorEvent)
            .order_by(desc(ErrorEvent.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
