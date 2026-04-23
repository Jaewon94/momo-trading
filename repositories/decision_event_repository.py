from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.decision_event import DecisionEvent
from repositories.async_base_repository import AsyncBaseRepository


class DecisionEventRepository(AsyncBaseRepository[DecisionEvent]):
    def __init__(self, db: AsyncSession):
        super().__init__(DecisionEvent, db)

    async def list_recent(self, *, limit: int = 100, symbol: str | None = None) -> list[DecisionEvent]:
        stmt = select(DecisionEvent).order_by(DecisionEvent.created_at.desc()).limit(limit)
        if symbol:
            stmt = (
                select(DecisionEvent)
                .where(DecisionEvent.symbol == symbol)
                .order_by(DecisionEvent.created_at.desc())
                .limit(limit)
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
