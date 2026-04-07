from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.error_incident import ErrorIncident
from repositories.async_base_repository import AsyncBaseRepository


class ErrorIncidentRepository(AsyncBaseRepository[ErrorIncident]):
    def __init__(self, db: AsyncSession):
        super().__init__(ErrorIncident, db)

    async def list_recent(self, limit: int = 50) -> list[ErrorIncident]:
        result = await self.db.execute(
            select(ErrorIncident)
            .order_by(desc(ErrorIncident.last_seen_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_fingerprint(self, fingerprint: str) -> ErrorIncident | None:
        result = await self.db.execute(
            select(ErrorIncident).where(ErrorIncident.fingerprint == fingerprint).limit(1)
        )
        return result.scalars().first()
