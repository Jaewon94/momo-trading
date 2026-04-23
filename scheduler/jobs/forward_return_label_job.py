from __future__ import annotations

from datetime import datetime, timedelta

from services.decision_forward_return_service import DecisionForwardReturnService
from util.time_util import now_kst


class ForwardReturnLabelJob:
    def __init__(
        self,
        session_factory=None,
        *,
        intraday_horizons: dict[str, timedelta] | None = None,
        include_close: bool = True,
    ) -> None:
        self._service = DecisionForwardReturnService(
            session_factory=session_factory,
            intraday_horizons=intraday_horizons,
            include_close=include_close,
        ) if session_factory is not None else DecisionForwardReturnService(
            intraday_horizons=intraday_horizons,
            include_close=include_close,
        )

    async def run_once(self, *, now: datetime | None = None, limit: int = 500) -> dict[str, int]:
        return await self._service.label_due_events(now=now or now_kst(), limit=limit)


forward_return_label_job = ForwardReturnLabelJob()
