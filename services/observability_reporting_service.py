"""운영 메트릭 조회/집계 서비스."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.execution_metric import ExecutionMetric
from models.execution_metric_hourly_rollup import ExecutionMetricHourlyRollup
from models.error_event import ErrorEvent
from models.error_incident import ErrorIncident
from models.resource_hourly_rollup import ResourceHourlyRollup
from models.resource_snapshot import ResourceSnapshot
from services.llm_runtime_recommendation_service import llm_runtime_recommendation_service
from services.observability_maintenance_service import observability_maintenance_service
from util.time_util import ensure_kst, now_kst


def _safe_json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _truncate_text(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


class ObservabilityReportingService:
    _RAW_RESOURCE_WINDOW_HOURS = 48

    async def build_overview(
        self,
        session: AsyncSession,
        *,
        hours: int = 24,
        points: int = 120,
    ) -> dict[str, Any]:
        window_hours = max(int(hours or 24), 1)
        point_limit = max(int(points or 120), 10)
        end_at = now_kst()
        start_at = end_at - timedelta(hours=window_hours)
        use_rollups = window_hours > self._RAW_RESOURCE_WINDOW_HOURS
        resource_series_payload, latest_snapshot, resource_summary = await self._build_resource_payload(
            session,
            start_at=start_at,
            limit=point_limit,
            use_rollups=use_rollups,
        )
        llm_rows = await self._fetch_execution_metrics(
            session,
            start_at=start_at,
            metric_type="LLM_CALL",
        )
        job_rows = await self._fetch_execution_metrics(
            session,
            start_at=start_at,
            metric_type="JOB",
        )

        news_poll_rows = [row for row in job_rows if str(row.metric_name or "").upper() == "NEWS_POLL"]
        maintenance_rows = [row for row in job_rows if str(row.metric_name or "").upper() == "OBSERVABILITY_MAINTENANCE"]
        llm_summary = self._build_llm_summary(llm_rows)
        news_poll_summary = self._build_news_poll_summary(news_poll_rows)
        llm_trend_rows, news_trend_rows = await self._build_execution_trend_payloads(
            session,
            start_at=start_at,
            use_rollups=use_rollups,
            llm_rows=llm_rows,
            news_poll_rows=news_poll_rows,
        )

        return {
            "recommendations": llm_runtime_recommendation_service.build_recommendations(
                latest_snapshot=self._serialize_resource_snapshot(latest_snapshot),
                resource_summary=resource_summary,
                llm_summary=llm_summary,
                news_poll_summary=news_poll_summary,
                window={
                    "hours": window_hours,
                    "resolution": "hourly_rollup" if use_rollups else "raw",
                },
            ),
            "window": {
                "hours": window_hours,
                "from": start_at.isoformat(),
                "to": end_at.isoformat(),
                "resolution": "hourly_rollup" if use_rollups else "raw",
            },
            "latest_snapshot": self._serialize_resource_snapshot(latest_snapshot),
            "resource_summary": resource_summary,
            "resource_series": resource_series_payload,
            "llm": llm_summary,
            "jobs": {
                "news_poll": news_poll_summary,
                "maintenance": self._build_maintenance_summary(maintenance_rows),
            },
            "trends": {
                "llm": llm_trend_rows,
                "news_poll": news_trend_rows,
            },
            "errors": {
                "recent": await self._build_recent_errors(session, start_at=start_at, limit=8),
                "incidents": await self._build_error_incidents(session, limit=8),
            },
            "storage": await observability_maintenance_service.summarize_storage(
                session,
                hours=window_hours,
            ),
        }

    async def _build_resource_payload(
        self,
        session: AsyncSession,
        *,
        start_at,
        limit: int,
        use_rollups: bool,
    ) -> tuple[list[dict[str, Any]], ResourceSnapshot | None, dict[str, Any]]:
        latest_snapshot = await self._fetch_latest_resource_snapshot(session)
        if use_rollups:
            rollup_rows = await self._fetch_recent_resource_rollups(session, start_at=start_at, limit=limit)
            return (
                [self._serialize_resource_rollup_point(row) for row in rollup_rows],
                latest_snapshot,
                self._build_resource_summary_from_rollups(rollup_rows),
            )
        resource_rows = await self._fetch_recent_resource_snapshots(session, start_at=start_at, limit=limit)
        latest = latest_snapshot or (resource_rows[-1] if resource_rows else None)
        return (
            [self._serialize_resource_point(row) for row in resource_rows],
            latest,
            self._build_resource_summary(resource_rows),
        )

    async def _fetch_recent_resource_snapshots(
        self,
        session: AsyncSession,
        *,
        start_at,
        limit: int,
    ) -> list[ResourceSnapshot]:
        stmt = (
            select(ResourceSnapshot)
            .where(ResourceSnapshot.created_at >= start_at)
            .order_by(ResourceSnapshot.created_at.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        rows.reverse()
        return rows

    async def _fetch_recent_resource_rollups(
        self,
        session: AsyncSession,
        *,
        start_at,
        limit: int,
    ) -> list[ResourceHourlyRollup]:
        stmt = (
            select(ResourceHourlyRollup)
            .where(ResourceHourlyRollup.bucket_start >= start_at)
            .order_by(ResourceHourlyRollup.bucket_start.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        rows.reverse()
        return rows

    async def _fetch_latest_resource_snapshot(self, session: AsyncSession) -> ResourceSnapshot | None:
        stmt = select(ResourceSnapshot).order_by(ResourceSnapshot.created_at.desc()).limit(1)
        return (await session.execute(stmt)).scalars().first()

    async def _fetch_execution_metrics(
        self,
        session: AsyncSession,
        *,
        start_at,
        metric_type: str,
    ) -> list[ExecutionMetric]:
        stmt = (
            select(ExecutionMetric)
            .where(and_(
                ExecutionMetric.created_at >= start_at,
                ExecutionMetric.metric_type == metric_type,
            ))
            .order_by(ExecutionMetric.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _fetch_execution_rollups(
        self,
        session: AsyncSession,
        *,
        start_at,
        metric_type: str,
        metric_name: str,
    ) -> list[ExecutionMetricHourlyRollup]:
        stmt = (
            select(ExecutionMetricHourlyRollup)
            .where(and_(
                ExecutionMetricHourlyRollup.bucket_start >= start_at,
                ExecutionMetricHourlyRollup.metric_type == metric_type,
                ExecutionMetricHourlyRollup.metric_name == metric_name,
            ))
            .order_by(ExecutionMetricHourlyRollup.bucket_start.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _build_execution_trend_payloads(
        self,
        session: AsyncSession,
        *,
        start_at,
        use_rollups: bool,
        llm_rows: list[ExecutionMetric],
        news_poll_rows: list[ExecutionMetric],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if use_rollups:
            llm_rollups = await self._fetch_execution_rollups(
                session,
                start_at=start_at,
                metric_type="LLM_CALL",
                metric_name="LLM_GENERATE",
            )
            news_rollups = await self._fetch_execution_rollups(
                session,
                start_at=start_at,
                metric_type="JOB",
                metric_name="NEWS_POLL",
            )
            return (
                [self._serialize_llm_rollup_point(row) for row in llm_rollups],
                [self._serialize_news_rollup_point(row) for row in news_rollups],
            )
        return (
            self._build_llm_trend_from_rows(llm_rows),
            self._build_news_poll_trend_from_rows(news_poll_rows),
        )

    async def _build_recent_errors(
        self,
        session: AsyncSession,
        *,
        start_at,
        limit: int,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ErrorEvent)
            .where(ErrorEvent.created_at >= start_at)
            .order_by(ErrorEvent.created_at.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "created_at": ensure_kst(row.created_at).isoformat(),
                "component": row.component,
                "operation": row.operation,
                "severity": row.severity,
                "exception_type": row.exception_type,
                "exception_message": _truncate_text(row.exception_message, 160),
                "symbol": row.symbol,
                "provider": row.provider,
                "fingerprint": row.fingerprint,
            }
            for row in rows
        ]

    async def _build_error_incidents(
        self,
        session: AsyncSession,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(ErrorIncident)
            .order_by(ErrorIncident.last_seen_at.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "fingerprint": row.fingerprint,
                "title": row.title,
                "component": row.component,
                "operation": row.operation,
                "severity": row.severity,
                "status": row.status,
                "occurrence_count": int(row.occurrence_count or 0),
                "last_seen_at": ensure_kst(row.last_seen_at).isoformat() if row.last_seen_at else None,
                "exception_type": row.exception_type,
                "last_message": _truncate_text(row.last_message, 160),
                "owner_note": _truncate_text(row.owner_note, 200),
            }
            for row in rows
        ]

    def _build_resource_summary(self, rows: list[ResourceSnapshot]) -> dict[str, Any]:
        latest = rows[-1] if rows else None
        memory_values = [float(row.memory_percent) for row in rows if row.memory_percent is not None]
        cpu_values = [float(row.cpu_load_ratio_1m) for row in rows if row.cpu_load_ratio_1m is not None]
        app_rss_values = [float(row.app_rss_mb) for row in rows if row.app_rss_mb is not None]
        ollama_rss_values = [float(row.ollama_rss_mb) for row in rows if row.ollama_rss_mb is not None]
        return {
            "snapshot_count": len(rows),
            "latest_collected_at": ensure_kst(latest.created_at).isoformat() if latest else None,
            "avg_memory_percent": _round_or_none(sum(memory_values) / len(memory_values), 2) if memory_values else None,
            "peak_memory_percent": _round_or_none(max(memory_values), 2) if memory_values else None,
            "avg_cpu_load_ratio_1m": _round_or_none(sum(cpu_values) / len(cpu_values), 3) if cpu_values else None,
            "peak_cpu_load_ratio_1m": _round_or_none(max(cpu_values), 3) if cpu_values else None,
            "peak_app_rss_mb": _round_or_none(max(app_rss_values), 2) if app_rss_values else None,
            "peak_ollama_rss_mb": _round_or_none(max(ollama_rss_values), 2) if ollama_rss_values else None,
        }

    def _build_resource_summary_from_rollups(self, rows: list[ResourceHourlyRollup]) -> dict[str, Any]:
        latest = rows[-1] if rows else None
        total_samples = sum(int(row.sample_count or 0) for row in rows)
        weighted_memory = sum(float(row.avg_memory_percent or 0.0) * int(row.sample_count or 0) for row in rows if row.avg_memory_percent is not None)
        weighted_cpu = sum(float(row.avg_cpu_load_ratio_1m or 0.0) * int(row.sample_count or 0) for row in rows if row.avg_cpu_load_ratio_1m is not None)
        peak_memory = [float(row.peak_memory_percent) for row in rows if row.peak_memory_percent is not None]
        peak_cpu = [float(row.peak_cpu_load_ratio_1m) for row in rows if row.peak_cpu_load_ratio_1m is not None]
        peak_app_rss = [float(row.peak_app_rss_mb) for row in rows if row.peak_app_rss_mb is not None]
        peak_ollama_rss = [float(row.peak_ollama_rss_mb) for row in rows if row.peak_ollama_rss_mb is not None]
        return {
            "snapshot_count": total_samples,
            "bucket_count": len(rows),
            "latest_collected_at": ensure_kst(latest.bucket_start).isoformat() if latest else None,
            "avg_memory_percent": _round_or_none(weighted_memory / total_samples, 2) if total_samples else None,
            "peak_memory_percent": _round_or_none(max(peak_memory), 2) if peak_memory else None,
            "avg_cpu_load_ratio_1m": _round_or_none(weighted_cpu / total_samples, 3) if total_samples else None,
            "peak_cpu_load_ratio_1m": _round_or_none(max(peak_cpu), 3) if peak_cpu else None,
            "peak_app_rss_mb": _round_or_none(max(peak_app_rss), 2) if peak_app_rss else None,
            "peak_ollama_rss_mb": _round_or_none(max(peak_ollama_rss), 2) if peak_ollama_rss else None,
        }

    def _build_llm_summary(self, rows: list[ExecutionMetric]) -> dict[str, Any]:
        total = len(rows)
        success_rows = [row for row in rows if str(row.status or "").upper() == "SUCCESS"]
        error_rows = [row for row in rows if str(row.status or "").upper() != "SUCCESS"]
        elapsed_values = [int(row.elapsed_ms) for row in rows if row.elapsed_ms is not None]
        fallback_count = sum(1 for row in rows if bool(row.fallback_used))
        provider_groups: dict[str, list[ExecutionMetric]] = defaultdict(list)
        for row in rows:
            provider_groups[str(row.provider or "UNKNOWN").upper()].append(row)
        provider_rows = []
        for provider, provider_metrics in sorted(provider_groups.items(), key=lambda item: (-len(item[1]), item[0])):
            provider_elapsed = [int(metric.elapsed_ms) for metric in provider_metrics if metric.elapsed_ms is not None]
            provider_success = sum(1 for metric in provider_metrics if str(metric.status or "").upper() == "SUCCESS")
            provider_rows.append({
                "provider": provider,
                "calls": len(provider_metrics),
                "success_rate": self._percent(provider_success, len(provider_metrics)),
                "avg_elapsed_ms": _round_or_none(sum(provider_elapsed) / len(provider_elapsed), 1) if provider_elapsed else None,
                "p95_elapsed_ms": self._percentile(provider_elapsed, 0.95),
                "fallback_rate": self._percent(sum(1 for metric in provider_metrics if bool(metric.fallback_used)), len(provider_metrics)),
            })

        return {
            "total_calls": total,
            "success_count": len(success_rows),
            "error_count": len(error_rows),
            "success_rate": self._percent(len(success_rows), total),
            "fallback_rate": self._percent(fallback_count, total),
            "avg_elapsed_ms": _round_or_none(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None,
            "p95_elapsed_ms": self._percentile(elapsed_values, 0.95),
            "provider_breakdown": provider_rows,
        }

    def _build_news_poll_summary(self, rows: list[ExecutionMetric]) -> dict[str, Any]:
        elapsed_values = [int(row.elapsed_ms) for row in rows if row.elapsed_ms is not None]
        status_counter = Counter(str(row.status or "UNKNOWN").upper() for row in rows)
        return {
            "runs": len(rows),
            "success_rate": self._percent(status_counter.get("SUCCESS", 0), len(rows)),
            "partial_error_runs": status_counter.get("PARTIAL_ERROR", 0),
            "error_runs": sum(count for status, count in status_counter.items() if status not in {"SUCCESS", "SKIPPED"}),
            "skipped_runs": status_counter.get("SKIPPED", 0),
            "avg_elapsed_ms": _round_or_none(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None,
            "p95_elapsed_ms": self._percentile(elapsed_values, 0.95),
            "received_total": sum(int(row.item_count or 0) for row in rows),
            "created_total": sum(int(row.success_count or 0) for row in rows),
            "source_error_total": sum(int(row.error_count or 0) for row in rows),
            "status_breakdown": [
                {"status": status, "count": count}
                for status, count in sorted(status_counter.items(), key=lambda item: (-item[1], item[0]))
            ],
        }

    def _build_maintenance_summary(self, rows: list[ExecutionMetric]) -> dict[str, Any]:
        latest = rows[-1] if rows else None
        detail = _safe_json_loads(latest.detail if latest else None)
        success_count = sum(1 for row in rows if str(row.status or "").upper() == "SUCCESS")
        return {
            "runs": len(rows),
            "success_rate": self._percent(success_count, len(rows)),
            "last_run_at": ensure_kst(latest.created_at).isoformat() if latest else None,
            "last_status": str(latest.status or "").upper() if latest else None,
            "last_elapsed_ms": int(latest.elapsed_ms) if latest and latest.elapsed_ms is not None else None,
            "last_resource_rollups_created": int(detail.get("resource_rollups_created") or 0),
            "last_execution_rollups_created": int(detail.get("execution_rollups_created") or 0),
            "last_deleted_resource_rows": int(detail.get("deleted_resource_rows") or 0),
            "last_deleted_execution_rows": int(detail.get("deleted_execution_rows") or 0),
        }

    def _build_llm_trend_from_rows(self, rows: list[ExecutionMetric]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ExecutionMetric]] = defaultdict(list)
        for row in rows:
            bucket = ensure_kst(row.created_at).replace(minute=0, second=0, microsecond=0).isoformat()
            grouped[bucket].append(row)
        points = []
        for bucket, bucket_rows in sorted(grouped.items()):
            elapsed_values = [int(row.elapsed_ms) for row in bucket_rows if row.elapsed_ms is not None]
            success_count = sum(1 for row in bucket_rows if str(row.status or "").upper() == "SUCCESS")
            points.append({
                "created_at": bucket,
                "calls": len(bucket_rows),
                "avg_elapsed_ms": _round_or_none(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None,
                "success_rate": self._percent(success_count, len(bucket_rows)),
            })
        return points

    def _build_news_poll_trend_from_rows(self, rows: list[ExecutionMetric]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ExecutionMetric]] = defaultdict(list)
        for row in rows:
            bucket = ensure_kst(row.created_at).replace(minute=0, second=0, microsecond=0).isoformat()
            grouped[bucket].append(row)
        points = []
        for bucket, bucket_rows in sorted(grouped.items()):
            elapsed_values = [int(row.elapsed_ms) for row in bucket_rows if row.elapsed_ms is not None]
            points.append({
                "created_at": bucket,
                "runs": len(bucket_rows),
                "avg_elapsed_ms": _round_or_none(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None,
                "created_total": sum(int(row.success_count or 0) for row in bucket_rows),
                "error_total": sum(int(row.error_count or 0) for row in bucket_rows),
            })
        return points

    @staticmethod
    def _serialize_resource_snapshot(row: ResourceSnapshot | None) -> dict[str, Any] | None:
        if row is None:
            return None
        detail = _safe_json_loads(row.detail)
        return {
            "created_at": ensure_kst(row.created_at).isoformat(),
            "host": row.host,
            "app_name": row.app_name,
            "environment": row.environment,
            "python_version": row.python_version,
            "platform_system": row.platform_system,
            "platform_release": row.platform_release,
            "platform_machine": row.platform_machine,
            "cpu_count": row.cpu_count,
            "app_pid": row.app_pid,
            "cpu_load_ratio_1m": row.cpu_load_ratio_1m,
            "memory_percent": row.memory_percent,
            "app_rss_mb": row.app_rss_mb,
            "ollama_rss_mb": row.ollama_rss_mb,
            "ollama_running": row.ollama_running,
            "disk_used_percent": row.disk_used_percent,
            "detail": detail,
        }

    @staticmethod
    def _serialize_resource_point(row: ResourceSnapshot) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.created_at).isoformat(),
            "cpu_load_ratio_1m": _round_or_none(row.cpu_load_ratio_1m, 3),
            "memory_percent": _round_or_none(row.memory_percent, 2),
            "app_rss_mb": _round_or_none(row.app_rss_mb, 2),
            "ollama_rss_mb": _round_or_none(row.ollama_rss_mb, 2),
            "ollama_running": bool(row.ollama_running),
        }

    @staticmethod
    def _serialize_resource_rollup_point(row: ResourceHourlyRollup) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.bucket_start).isoformat(),
            "cpu_load_ratio_1m": _round_or_none(row.avg_cpu_load_ratio_1m, 3),
            "memory_percent": _round_or_none(row.avg_memory_percent, 2),
            "app_rss_mb": _round_or_none(row.avg_app_rss_mb, 2),
            "ollama_rss_mb": _round_or_none(row.avg_ollama_rss_mb, 2),
            "ollama_running": bool((row.ollama_running_rate or 0.0) > 0.0),
            "sample_count": int(row.sample_count or 0),
        }

    @staticmethod
    def _serialize_llm_rollup_point(row: ExecutionMetricHourlyRollup) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.bucket_start).isoformat(),
            "calls": int(row.sample_count or 0),
            "avg_elapsed_ms": _round_or_none(row.avg_elapsed_ms, 1),
            "success_rate": ObservabilityReportingService._percent(int(row.success_count or 0), int(row.sample_count or 0)),
        }

    @staticmethod
    def _serialize_news_rollup_point(row: ExecutionMetricHourlyRollup) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.bucket_start).isoformat(),
            "runs": int(row.sample_count or 0),
            "avg_elapsed_ms": _round_or_none(row.avg_elapsed_ms, 1),
            "created_total": int(row.success_total or 0),
            "error_total": int(row.error_total or 0),
        }

    @staticmethod
    def _serialize_llm_rollup_point(row: ExecutionMetricHourlyRollup) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.bucket_start).isoformat(),
            "calls": int(row.sample_count or 0),
            "avg_elapsed_ms": _round_or_none(row.avg_elapsed_ms, 1),
            "success_rate": ObservabilityReportingService._percent(int(row.success_count or 0), int(row.sample_count or 0)),
        }

    @staticmethod
    def _serialize_news_rollup_point(row: ExecutionMetricHourlyRollup) -> dict[str, Any]:
        return {
            "created_at": ensure_kst(row.bucket_start).isoformat(),
            "runs": int(row.sample_count or 0),
            "avg_elapsed_ms": _round_or_none(row.avg_elapsed_ms, 1),
            "created_total": int(row.success_total or 0),
            "error_total": int(row.error_total or 0),
        }

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100.0, 1)

    @staticmethod
    def _percentile(values: list[int], ratio: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * ratio) - 1)
        return float(ordered[index])


observability_reporting_service = ObservabilityReportingService()
