from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import not_, select

from core.database import AsyncSessionLocal
from models.decision_event import DecisionEvent
from models.decision_forward_return import DecisionForwardReturn
from models.market_data import MarketDataDaily, MarketSnapshot
from models.stock import Stock
from repositories.decision_forward_return_repository import DecisionForwardReturnRepository
from services.decision_event_quality import probable_fixture_decision_event_filter


DEFAULT_INTRADAY_HORIZONS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "60m": timedelta(minutes=60),
}


@dataclass(frozen=True)
class ResolvedForwardPrice:
    price: float
    source: str


class DecisionForwardReturnService:
    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        *,
        intraday_horizons: dict[str, timedelta] | None = None,
        include_close: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._intraday_horizons = (
            dict(DEFAULT_INTRADAY_HORIZONS) if intraday_horizons is None else dict(intraday_horizons)
        )
        self._include_close = include_close

    async def label_due_events(self, *, now: datetime, limit: int = 500) -> dict[str, int]:
        now = self._without_timezone(now)
        summary = {
            "events_scanned": 0,
            "labels_considered": 0,
            "labeled": 0,
            "waiting_data": 0,
            "skipped": 0,
        }
        async with self._session_factory() as session:
            async with session.begin():
                events = list(
                    (
                        await session.execute(
                            select(DecisionEvent)
                            .where(
                                DecisionEvent.reference_price.is_not(None),
                                DecisionEvent.reference_price > 0,
                                DecisionEvent.created_at <= now,
                                not_(probable_fixture_decision_event_filter(DecisionEvent)),
                            )
                            .order_by(DecisionEvent.created_at.desc())
                            .limit(limit)
                        )
                    )
                    .scalars()
                    .all()
                )
                summary["events_scanned"] = len(events)
                repo = DecisionForwardReturnRepository(session)

                for event in events:
                    for horizon, target_at in self._target_times(event).items():
                        if now < target_at:
                            summary["skipped"] += 1
                            continue
                        summary["labels_considered"] += 1
                        label = await repo.get_by_event_horizon(
                            decision_event_id=event.id,
                            horizon=horizon,
                        )
                        if label and label.label_status == "LABELED":
                            summary["skipped"] += 1
                            continue

                        resolved = await self._resolve_price(
                            session,
                            event=event,
                            horizon=horizon,
                            target_at=target_at,
                        )
                        if resolved is None:
                            label = await self._upsert_label(
                                repo,
                                label=label,
                                event=event,
                                horizon=horizon,
                                target_at=target_at,
                                status="WAITING_DATA",
                                target_price=None,
                                return_pct=None,
                                price_source=None,
                                reason="target price data is not available yet",
                            )
                            summary["waiting_data"] += 1
                            continue

                        return_pct = self._return_pct(
                            reference_price=float(event.reference_price),
                            target_price=resolved.price,
                        )
                        await self._upsert_label(
                            repo,
                            label=label,
                            event=event,
                            horizon=horizon,
                            target_at=target_at,
                            status="LABELED",
                            target_price=resolved.price,
                            return_pct=return_pct,
                            price_source=resolved.source,
                            reason=None,
                        )
                        summary["labeled"] += 1
        return summary

    def _target_times(self, event: DecisionEvent) -> dict[str, datetime]:
        event_created_at = self._without_timezone(event.created_at)
        targets = {
            horizon: event_created_at + delta
            for horizon, delta in self._intraday_horizons.items()
        }
        if self._include_close:
            targets["close"] = datetime.combine(event_created_at.date(), time(15, 30))
        return targets

    async def _resolve_price(
        self,
        session,
        *,
        event: DecisionEvent,
        horizon: str,
        target_at: datetime,
    ) -> ResolvedForwardPrice | None:
        stock = (
            await session.execute(select(Stock).where(Stock.symbol == event.symbol))
        ).scalars().first()
        if not stock:
            return None

        if horizon == "close":
            daily = (
                await session.execute(
                    select(MarketDataDaily)
                    .where(
                        MarketDataDaily.stock_id == stock.id,
                        MarketDataDaily.trade_date >= self._without_timezone(event.created_at).date(),
                    )
                    .order_by(MarketDataDaily.trade_date.asc())
                )
            ).scalars().first()
            if daily:
                return ResolvedForwardPrice(price=float(daily.close), source="market_data_daily.close")

        snapshot = (
            await session.execute(
                select(MarketSnapshot).where(MarketSnapshot.stock_id == stock.id)
            )
        ).scalars().first()
        if not snapshot:
            return None
        data_at = self._without_timezone(snapshot.updated_at or snapshot.created_at)
        if data_at is None or data_at < target_at:
            return None
        price = float(snapshot.current_price or 0)
        if price <= 0:
            return None
        source = (
            "market_snapshot.current_price_after_close"
            if horizon == "close"
            else "market_snapshot.current_price"
        )
        return ResolvedForwardPrice(price=price, source=source)

    async def _upsert_label(
        self,
        repo: DecisionForwardReturnRepository,
        *,
        label: DecisionForwardReturn | None,
        event: DecisionEvent,
        horizon: str,
        target_at: datetime,
        status: str,
        target_price: float | None,
        return_pct: float | None,
        price_source: str | None,
        reason: str | None,
    ) -> DecisionForwardReturn:
        if label is None:
            label = DecisionForwardReturn(
                decision_event_id=event.id,
                symbol=event.symbol,
                horizon=horizon,
                target_at=target_at,
                reference_price=float(event.reference_price),
                label_status=status,
            )
        label.symbol = event.symbol
        label.target_at = target_at
        label.reference_price = float(event.reference_price)
        label.target_price = target_price
        label.return_pct = return_pct
        label.label_status = status
        label.price_source = price_source
        label.reason = reason
        return await repo.update(label)

    @staticmethod
    def _return_pct(*, reference_price: float, target_price: float) -> float:
        if reference_price <= 0:
            return 0.0
        return round(((target_price - reference_price) / reference_price) * 100, 6)

    @staticmethod
    def _without_timezone(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value


decision_forward_return_service = DecisionForwardReturnService()
