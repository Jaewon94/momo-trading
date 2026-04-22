from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.resource_snapshot import ResourceSnapshot
from repositories.async_base_repository import AsyncBaseRepository


class ResourceSnapshotRepository(AsyncBaseRepository[ResourceSnapshot]):
    def __init__(self, db: AsyncSession):
        super().__init__(ResourceSnapshot, db)

    async def list_recent(self, limit: int = 50) -> list[ResourceSnapshot]:
        result = await self.db.execute(
            select(ResourceSnapshot)
            .order_by(ResourceSnapshot.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
