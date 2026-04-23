from __future__ import annotations

import json
import hashlib
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
    event_source: str
    scanner_score: float | None
    strategy_type: str
    tier1_decision: str
    tier2_decision: str
    provider: str
    risk_gate_result: str
    return_pct: float
    news_source_codes: tuple[str, ...]


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
                event_source=str(event.source or "UNKNOWN").upper(),
                scanner_score=float(event.scanner_score) if event.scanner_score is not None else None,
                strategy_type=str(event.strategy_type or "UNKNOWN").upper(),
                tier1_decision=str(event.tier1_decision or "UNKNOWN").upper(),
                tier2_decision=str(event.tier2_decision or "UNKNOWN").upper(),
                provider=str(event.provider or "UNKNOWN").upper(),
                risk_gate_result=str(event.risk_gate_result or "UNKNOWN").upper(),
                return_pct=float(label.return_pct or 0.0),
                news_source_codes=self._extract_news_source_codes(getattr(event, "metadata_json", None)),
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
            "by_event_source": self._group(points, lambda item: item.event_source),
            "by_strategy_type": self._group(points, lambda item: item.strategy_type),
            "by_tier1_decision": self._group(points, lambda item: item.tier1_decision),
            "by_tier2_decision": self._group(points, lambda item: item.tier2_decision),
            "by_provider": self._group(points, lambda item: item.provider),
            "by_risk_gate": self._group(points, lambda item: item.risk_gate_result),
            "by_news_source_attribution": self._group_news_source(points),
            "by_news_source_blocked": self._group_news_source_blocked(points),
            "by_news_source_blocked_comparison": self._group_news_source_blocked_comparison(points),
            "controls": self._control_groups(points),
        }

    def _control_groups(self, points: list[DecisionBenchmarkPoint]) -> dict:
        actual_buy = [item for item in points if item.final_action == "BUY"]
        sample_count = len(actual_buy)
        return {
            "actual_buy": self._metrics(actual_buy),
            "non_buy_candidates": self._metrics([item for item in points if item.final_action != "BUY"]),
            "blocked_or_skipped": self._metrics([
                item
                for item in points
                if item.final_action == "SKIP" or item.risk_gate_result == "BLOCKED"
            ]),
            "random_same_count": self._metrics(self._random_same_count(points, sample_count)),
            "scanner_top_same_count": self._metrics(self._scanner_top_same_count(points, sample_count)),
            "tier1_buy_only": self._metrics([item for item in points if item.tier1_decision == "BUY"]),
            "tier2_buy_only": self._metrics([item for item in points if item.tier2_decision == "BUY"]),
        }

    def _group(self, points: list[DecisionBenchmarkPoint], key_fn) -> dict:
        grouped: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)
        for item in points:
            grouped[str(key_fn(item) or "UNKNOWN")].append(item)
        return {key: self._metrics(items) for key, items in sorted(grouped.items())}

    def _group_news_source(self, points: list[DecisionBenchmarkPoint]) -> dict:
        grouped: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)
        for item in points:
            seen: set[str] = set()
            for code in item.news_source_codes:
                normalized = str(code or "").upper().strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                grouped[normalized].append(item)
        return {key: self._metrics(items) for key, items in sorted(grouped.items())}

    def _group_news_source_blocked(self, points: list[DecisionBenchmarkPoint]) -> dict:
        grouped: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)
        for item in points:
            if not self._is_blocked_candidate(item):
                continue
            seen: set[str] = set()
            for code in item.news_source_codes:
                normalized = str(code or "").upper().strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                grouped[normalized].append(item)
        return {key: self._metrics(items) for key, items in sorted(grouped.items())}

    def _group_news_source_blocked_comparison(self, points: list[DecisionBenchmarkPoint]) -> dict:
        blocked_by_source: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)
        buy_by_source: dict[str, list[DecisionBenchmarkPoint]] = defaultdict(list)

        for item in points:
            seen: set[str] = set()
            for code in item.news_source_codes:
                normalized = str(code or "").upper().strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                if self._is_blocked_candidate(item):
                    blocked_by_source[normalized].append(item)
                if item.final_action == "BUY":
                    buy_by_source[normalized].append(item)

        keys = sorted(set(blocked_by_source) | set(buy_by_source))
        report: dict[str, dict] = {}
        for key in keys:
            blocked_metrics = self._metrics(blocked_by_source.get(key, []))
            buy_metrics = self._metrics(buy_by_source.get(key, []))
            report[key] = {
                "blocked": blocked_metrics,
                "actual_buy": buy_metrics,
                "delta_avg_return_pct": round(
                    float(blocked_metrics.get("avg_return_pct") or 0.0)
                    - float(buy_metrics.get("avg_return_pct") or 0.0),
                    4,
                ),
            }
        return report

    def _random_same_count(
        self,
        points: list[DecisionBenchmarkPoint],
        sample_count: int,
    ) -> list[DecisionBenchmarkPoint]:
        if sample_count <= 0:
            return []
        decorated = sorted(
            points,
            key=lambda item: self._stable_rank_key(item),
        )
        return decorated[:sample_count]

    def _scanner_top_same_count(
        self,
        points: list[DecisionBenchmarkPoint],
        sample_count: int,
    ) -> list[DecisionBenchmarkPoint]:
        if sample_count <= 0:
            return []
        ranked = [item for item in points if item.scanner_score is not None]
        ranked.sort(
            key=lambda item: (
                -float(item.scanner_score or 0.0),
                item.symbol,
                item.final_action,
                item.decision_stage,
            )
        )
        return ranked[:sample_count]

    @staticmethod
    def _stable_rank_key(item: DecisionBenchmarkPoint) -> str:
        payload = "|".join([
            item.symbol,
            item.final_action,
            item.decision_stage,
            item.event_source,
            item.strategy_type,
            item.provider,
            item.risk_gate_result,
        ])
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_blocked_candidate(item: DecisionBenchmarkPoint) -> bool:
        return item.final_action == "SKIP" or item.risk_gate_result == "BLOCKED"

    @staticmethod
    def _extract_news_source_codes(metadata_json: str | None) -> tuple[str, ...]:
        if not metadata_json:
            return ()
        try:
            payload = json.loads(metadata_json)
        except (TypeError, ValueError):
            return ()
        if not isinstance(payload, dict):
            return ()

        codes: list[str] = []
        for root_key in ("signal_metadata", "analysis_context"):
            root = payload.get(root_key)
            if not isinstance(root, dict):
                continue
            contributors = root.get("news_top_contributors")
            if not isinstance(contributors, list):
                continue
            for contributor in contributors:
                if not isinstance(contributor, dict):
                    continue
                code = str(contributor.get("source_code") or "").upper().strip()
                if code:
                    codes.append(code)
        return tuple(codes)

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
