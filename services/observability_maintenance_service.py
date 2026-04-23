"""운영 메트릭 롤업/정리 서비스."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import AsyncSessionLocal
from models.execution_metric import ExecutionMetric
from models.execution_metric_hourly_rollup import ExecutionMetricHourlyRollup
from models.resource_hourly_rollup import ResourceHourlyRollup
from models.resource_snapshot import ResourceSnapshot
from util.time_util import ensure_kst, now_kst


def _bucket_start(dt: datetime) -> datetime:
    kst = ensure_kst(dt)
    return kst.replace(minute=0, second=0, microsecond=0)


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _percentile(values: list[int | float], ratio: float) -> float | None:
    ordered = sorted(float(value) for value in values if value is not None)
    if not ordered:
        return None
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return round(ordered[index], 1)


def _normalize_rollup_dimension(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized else "UNKNOWN"


class ObservabilityMaintenanceService:
    async def run_maintenance(self, *, now: datetime | None = None) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                return await self.run_maintenance_for_session(session, now=now)

    async def run_maintenance_for_session(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current_time = ensure_kst(now or now_kst())
        current_bucket = _bucket_start(current_time)
        lookback_hours = max(int(settings.METRICS_ROLLUP_LOOKBACK_HOURS or 72), 1)
        raw_retention_days = max(int(settings.METRICS_RAW_RETENTION_DAYS or 30), 1)
        rollup_retention_days = max(int(settings.METRICS_ROLLUP_RETENTION_DAYS or 365), 1)
        rollup_start = current_bucket - timedelta(hours=lookback_hours)

        resource_rows = await self._fetch_resource_snapshots(
            session,
            start_at=rollup_start,
            end_at=current_bucket,
        )
        execution_rows = await self._fetch_execution_metrics(
            session,
            start_at=rollup_start,
            end_at=current_bucket,
        )

        resource_rollups = self._build_resource_rollups(resource_rows)
        execution_rollups = self._build_execution_rollups(execution_rows)

        deleted_existing_resource = await self._delete_rollup_window(
            session,
            model=ResourceHourlyRollup,
            start_at=rollup_start,
            end_at=current_bucket,
        )
        deleted_existing_execution = await self._delete_rollup_window(
            session,
            model=ExecutionMetricHourlyRollup,
            start_at=rollup_start,
            end_at=current_bucket,
        )

        if resource_rollups:
            session.add_all(resource_rollups)
            await session.flush()
        if execution_rollups:
            session.add_all(execution_rollups)
            await session.flush()

        raw_cutoff = current_time - timedelta(days=raw_retention_days)
        rollup_cutoff = current_time - timedelta(days=rollup_retention_days)

        deleted_resource_rows = await self._delete_older_than(session, ResourceSnapshot, raw_cutoff)
        deleted_execution_rows = await self._delete_older_than(session, ExecutionMetric, raw_cutoff)
        deleted_resource_rollups = await self._delete_older_than(session, ResourceHourlyRollup, rollup_cutoff, field_name="bucket_start")
        deleted_execution_rollups = await self._delete_older_than(session, ExecutionMetricHourlyRollup, rollup_cutoff, field_name="bucket_start")

        return {
            "bucket_end": current_bucket.isoformat(),
            "rollup_window_start": rollup_start.isoformat(),
            "resource_rollups_created": len(resource_rollups),
            "execution_rollups_created": len(execution_rollups),
            "resource_rollups_replaced": deleted_existing_resource,
            "execution_rollups_replaced": deleted_existing_execution,
            "deleted_resource_rows": deleted_resource_rows,
            "deleted_execution_rows": deleted_execution_rows,
            "deleted_resource_rollups": deleted_resource_rollups,
            "deleted_execution_rollups": deleted_execution_rollups,
            "raw_retention_days": raw_retention_days,
            "rollup_retention_days": rollup_retention_days,
        }

    async def _fetch_resource_snapshots(
        self,
        session: AsyncSession,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[ResourceSnapshot]:
        stmt = (
            select(ResourceSnapshot)
            .where(ResourceSnapshot.created_at >= start_at)
            .where(ResourceSnapshot.created_at < end_at)
            .order_by(ResourceSnapshot.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _fetch_execution_metrics(
        self,
        session: AsyncSession,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[ExecutionMetric]:
        stmt = (
            select(ExecutionMetric)
            .where(ExecutionMetric.created_at >= start_at)
            .where(ExecutionMetric.created_at < end_at)
            .order_by(ExecutionMetric.created_at.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def _delete_rollup_window(
        self,
        session: AsyncSession,
        *,
        model,
        start_at: datetime,
        end_at: datetime,
    ) -> int:
        stmt = (
            delete(model)
            .where(model.bucket_start >= start_at)
            .where(model.bucket_start < end_at)
        )
        result = await session.execute(stmt)
        await session.flush()
        return int(result.rowcount or 0)

    async def _delete_older_than(
        self,
        session: AsyncSession,
        model,
        cutoff: datetime,
        *,
        field_name: str = "created_at",
    ) -> int:
        field = getattr(model, field_name)
        result = await session.execute(
            delete(model)
            .where(field < cutoff)
            .execution_options(synchronize_session=False)
        )
        await session.flush()
        return int(result.rowcount or 0)

    def _build_resource_rollups(self, rows: list[ResourceSnapshot]) -> list[ResourceHourlyRollup]:
        grouped: dict[tuple[Any, ...], list[ResourceSnapshot]] = defaultdict(list)
        for row in rows:
            key = (
                _bucket_start(row.created_at),
                row.scope,
                row.host,
                row.app_name,
                row.environment,
            )
            grouped[key].append(row)

        rollups: list[ResourceHourlyRollup] = []
        for (bucket, scope, host, app_name, environment), bucket_rows in sorted(grouped.items(), key=lambda item: item[0]):
            cpu_values = [float(row.cpu_load_ratio_1m) for row in bucket_rows if row.cpu_load_ratio_1m is not None]
            memory_values = [float(row.memory_percent) for row in bucket_rows if row.memory_percent is not None]
            app_rss_values = [float(row.app_rss_mb) for row in bucket_rows if row.app_rss_mb is not None]
            ollama_rss_values = [float(row.ollama_rss_mb) for row in bucket_rows if row.ollama_rss_mb is not None]
            disk_values = [float(row.disk_used_percent) for row in bucket_rows if row.disk_used_percent is not None]
            running_samples = [1.0 for row in bucket_rows if bool(row.ollama_running)]
            rollups.append(
                ResourceHourlyRollup(
                    bucket_start=bucket,
                    scope=scope,
                    host=host,
                    app_name=app_name,
                    environment=environment,
                    sample_count=len(bucket_rows),
                    avg_cpu_load_ratio_1m=_round_or_none(sum(cpu_values) / len(cpu_values), 3) if cpu_values else None,
                    peak_cpu_load_ratio_1m=_round_or_none(max(cpu_values), 3) if cpu_values else None,
                    avg_memory_percent=_round_or_none(sum(memory_values) / len(memory_values), 2) if memory_values else None,
                    peak_memory_percent=_round_or_none(max(memory_values), 2) if memory_values else None,
                    avg_app_rss_mb=_round_or_none(sum(app_rss_values) / len(app_rss_values), 2) if app_rss_values else None,
                    peak_app_rss_mb=_round_or_none(max(app_rss_values), 2) if app_rss_values else None,
                    avg_ollama_rss_mb=_round_or_none(sum(ollama_rss_values) / len(ollama_rss_values), 2) if ollama_rss_values else None,
                    peak_ollama_rss_mb=_round_or_none(max(ollama_rss_values), 2) if ollama_rss_values else None,
                    avg_disk_used_percent=_round_or_none(sum(disk_values) / len(disk_values), 2) if disk_values else None,
                    peak_disk_used_percent=_round_or_none(max(disk_values), 2) if disk_values else None,
                    ollama_running_rate=_round_or_none((sum(running_samples) / len(bucket_rows)) * 100.0, 1) if bucket_rows else None,
                )
            )
        return rollups

    def _build_execution_rollups(self, rows: list[ExecutionMetric]) -> list[ExecutionMetricHourlyRollup]:
        grouped: dict[tuple[Any, ...], list[ExecutionMetric]] = defaultdict(list)
        for row in rows:
            key = (
                _bucket_start(row.created_at),
                _normalize_rollup_dimension(row.metric_type),
                _normalize_rollup_dimension(row.metric_name),
                _normalize_rollup_dimension(row.provider),
                _normalize_rollup_dimension(row.model),
            )
            grouped[key].append(row)

        rollups: list[ExecutionMetricHourlyRollup] = []
        for (bucket, metric_type, metric_name, provider, model), bucket_rows in sorted(grouped.items(), key=lambda item: item[0]):
            elapsed_values = [int(row.elapsed_ms) for row in bucket_rows if row.elapsed_ms is not None]
            status_counts = defaultdict(int)
            for row in bucket_rows:
                status_counts[str(row.status or "UNKNOWN").upper()] += 1
            rollups.append(
                ExecutionMetricHourlyRollup(
                    bucket_start=bucket,
                    metric_type=metric_type,
                    metric_name=metric_name,
                    provider=provider,
                    model=model,
                    sample_count=len(bucket_rows),
                    success_count=status_counts["SUCCESS"],
                    partial_error_count=status_counts["PARTIAL_ERROR"],
                    error_count=sum(
                        count
                        for status, count in status_counts.items()
                        if status not in {"SUCCESS", "PARTIAL_ERROR", "SKIPPED"}
                    ),
                    skipped_count=status_counts["SKIPPED"],
                    fallback_count=sum(1 for row in bucket_rows if bool(row.fallback_used)),
                    item_total=sum(int(row.item_count or 0) for row in bucket_rows),
                    success_total=sum(int(row.success_count or 0) for row in bucket_rows),
                    error_total=sum(int(row.error_count or 0) for row in bucket_rows),
                    retry_total=sum(int(row.retry_count or 0) for row in bucket_rows),
                    avg_elapsed_ms=_round_or_none(sum(elapsed_values) / len(elapsed_values), 1) if elapsed_values else None,
                    p95_elapsed_ms=_percentile(elapsed_values, 0.95),
                )
            )
        return rollups

    async def summarize_storage(self, session: AsyncSession, *, hours: int) -> dict[str, Any]:
        since = now_kst() - timedelta(hours=max(int(hours or 24), 1))
        resource_rollup_count = await session.scalar(
            select(func.count()).select_from(ResourceHourlyRollup).where(ResourceHourlyRollup.bucket_start >= since)
        )
        execution_rollup_count = await session.scalar(
            select(func.count()).select_from(ExecutionMetricHourlyRollup).where(ExecutionMetricHourlyRollup.bucket_start >= since)
        )
        latest_resource_bucket = await session.scalar(
            select(ResourceHourlyRollup.bucket_start).order_by(ResourceHourlyRollup.bucket_start.desc()).limit(1)
        )
        latest_execution_bucket = await session.scalar(
            select(ExecutionMetricHourlyRollup.bucket_start).order_by(ExecutionMetricHourlyRollup.bucket_start.desc()).limit(1)
        )
        return {
            "raw_retention_days": int(settings.METRICS_RAW_RETENTION_DAYS or 30),
            "rollup_retention_days": int(settings.METRICS_ROLLUP_RETENTION_DAYS or 365),
            "rollup_lookback_hours": int(settings.METRICS_ROLLUP_LOOKBACK_HOURS or 72),
            "resource_rollup_buckets": int(resource_rollup_count or 0),
            "execution_rollup_buckets": int(execution_rollup_count or 0),
            "latest_resource_bucket_at": ensure_kst(latest_resource_bucket).isoformat() if latest_resource_bucket else None,
            "latest_execution_bucket_at": ensure_kst(latest_execution_bucket).isoformat() if latest_execution_bucket else None,
        }


observability_maintenance_service = ObservabilityMaintenanceService()
