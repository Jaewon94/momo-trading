from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.decision_forward_return import DecisionForwardReturn
from repositories.async_base_repository import AsyncBaseRepository


class DecisionForwardReturnRepository(AsyncBaseRepository[DecisionForwardReturn]):
    def __init__(self, db: AsyncSession):
        super().__init__(DecisionForwardReturn, db)

    async def get_by_event_horizon(
        self,
        *,
        decision_event_id: str,
        horizon: str,
    ) -> DecisionForwardReturn | None:
        result = await self.db.execute(
            select(DecisionForwardReturn).where(
                DecisionForwardReturn.decision_event_id == decision_event_id,
                DecisionForwardReturn.horizon == horizon,
            )
        )
        return result.scalars().first()
