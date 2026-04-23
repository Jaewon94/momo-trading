from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, select

from core.config import settings
from core.database import AsyncSessionLocal
from models.decision_event import DecisionEvent
from models.decision_forward_return import DecisionForwardReturn
from util.time_util import now_kst


@dataclass(frozen=True)
class DecisionBenchmarkPoint:
    symbol: str
    final_action: str
    decision_stage: str
    provider: str
    risk_gate_result: str
    return_pct: float


class DecisionBenchmarkService:
    async def build_report(
        self,
        session_factory=AsyncSessionLocal,
        *,
        days: int = 30,
        horizon: str = "close",
        min_sample_size: int | None = None,
    ) -> dict:
        normalized_horizon = str(horizon or "close").strip().lower()
        window_days = max(int(days), 1)
        minimum = max(
            int(min_sample_size)
            if min_sample_size is not None
            else int(getattr(settings, "NEWS_ROLLOUT_MIN_SAMPLE_SIZE", 12) or 12),
            1,
        )
        to_dt = now_kst().replace(tzinfo=None)
        from_dt = to_dt - timedelta(days=window_days)

        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(DecisionEvent, DecisionForwardReturn)
                    .join(
                        DecisionForwardReturn,
                        DecisionForwardReturn.decision_event_id == DecisionEvent.id,
                    )
                    .where(
                        and_(
                            DecisionEvent.created_at >= from_dt,
                            DecisionEvent.created_at <= to_dt,
                            DecisionForwardReturn.horizon == normalized_horizon,
                            DecisionForwardReturn.label_status == "LABELED",
                            DecisionForwardReturn.return_pct.is_not(None),
                        )
                    )
                    .order_by(DecisionEvent.created_at.asc())
                )
            ).all()

        points = [
            DecisionBenchmarkPoint(
                symbol=str(event.symbol or ""),
                final_action=str(event.final_action or "UNKNOWN").upper(),
                decision_stage=str(event.decision_stage or "UNKNOWN").upper(),
                provider=str(event.provider or "UNKNOWN").upper(),
                risk_gate_result=str(event.risk_gate_result or "UNKNOWN").upper(),
                return_pct=float(label.return_pct or 0.0),
            )
            for event, label in rows
        ]

        overall = self._metrics(points)
        return {
            "window": {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "days": window_days,
                "horizon": normalized_horizon,
            },
            "sample_status": "READY" if overall["event_count"] >= minimum else "INSUFFICIENT_SAMPLE",
            "minimum_sample_size": minimum,
            "overall": overall,
            "by_final_action": self._group(points, lambda item: item.final_action),
            "by_decision_stage": self._group(points, lambda item: item.decision_stage),
            "by_provider": self._group(points, lambda item: item.provider),
            "by_risk_gate": self._group(points, lambda item: item.risk_gate_result),
            "controls": self._control_groups(points),
        }

    def _control_groups(self, points: list[DecisionBenchmarkPoint]) -> dict:
        return {
            "actual_buy": self._metrics([item for item in points if item.final_action == "BUY"]),
            "non_buy_candidates": self._metrics([item for item in points if item.final_action != "BUY"]),
            "blocked_or_skipped": self._metrics([
                item
                for item in points
                if item.final_action == "SKIP" or item.risk_gate_result == "BLOCKED"
            ]),
        }

    def _group(self, points: list[DecisionBenchmarkPoint], key_fn) -> dict:
        grouped: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)
        for item in points:
            grouped[str(key_fn(item) or "UNKNOWN")].append(item)
        return {key: self._metrics(items) for key, items in sorted(grouped.items())}

    @staticmethod
    def _metrics(points: list[DecisionBenchmarkPoint]) -> dict:
        count = len(points)
        if count == 0:
            return {
                "event_count": 0,
                "avg_return_pct": 0.0,
                "positive_rate": 0.0,
                "best_return_pct": 0.0,
                "worst_return_pct": 0.0,
            }
        returns = [item.return_pct for item in points]
        return {
            "event_count": count,
            "avg_return_pct": round(sum(returns) / count, 4),
            "positive_rate": round(sum(1 for value in returns if value > 0) / count, 4),
            "best_return_pct": round(max(returns), 4),
            "worst_return_pct": round(min(returns), 4),
        }


decision_benchmark_service = DecisionBenchmarkService()
