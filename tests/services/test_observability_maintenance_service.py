from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from models.execution_metric import ExecutionMetric
from models.execution_metric_hourly_rollup import ExecutionMetricHourlyRollup
from models.resource_hourly_rollup import ResourceHourlyRollup
from models.resource_snapshot import ResourceSnapshot
from services.observability_maintenance_service import ObservabilityMaintenanceService
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_observability_maintenance_service_builds_rollups_and_cleans_old_rows(monkeypatch):
    current_time = now_kst().replace(minute=25, second=0, microsecond=0)
    completed_bucket = (current_time - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr("services.observability_maintenance_service.settings.METRICS_ROLLUP_LOOKBACK_HOURS", 6)
    monkeypatch.setattr("services.observability_maintenance_service.settings.METRICS_RAW_RETENTION_DAYS", 7)
    monkeypatch.setattr("services.observability_maintenance_service.settings.METRICS_ROLLUP_RETENTION_DAYS", 60)

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetricHourlyRollup))
        await session.execute(delete(ResourceHourlyRollup))
        await session.execute(delete(ExecutionMetric))
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            session.add_all([
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    cpu_load_ratio_1m=0.7,
                    memory_percent=60.0,
                    app_rss_mb=200.0,
                    ollama_rss_mb=4096.0,
                    ollama_running=True,
                    disk_used_percent=58.0,
                    created_at=completed_bucket + timedelta(minutes=5),
                ),
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    cpu_load_ratio_1m=0.9,
                    memory_percent=64.0,
                    app_rss_mb=240.0,
                    ollama_rss_mb=4200.0,
                    ollama_running=False,
                    disk_used_percent=59.0,
                    created_at=completed_bucket + timedelta(minutes=15),
                ),
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    cpu_load_ratio_1m=0.4,
                    memory_percent=52.0,
                    created_at=current_time - timedelta(days=10),
                ),
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="SUCCESS",
                    provider="OLLAMA",
                    model="ollama:qwen3:14b",
                    elapsed_ms=1800,
                    fallback_used=False,
                    created_at=completed_bucket + timedelta(minutes=2),
                ),
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="ERROR",
                    provider="OLLAMA",
                    model="ollama:qwen3:14b",
                    elapsed_ms=2600,
                    fallback_used=True,
                    created_at=completed_bucket + timedelta(minutes=20),
                ),
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="NEWS_POLL",
                    status="PARTIAL_ERROR",
                    elapsed_ms=5200,
                    item_count=12,
                    success_count=5,
                    error_count=2,
                    retry_count=1,
                    created_at=completed_bucket + timedelta(minutes=12),
                ),
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="NEWS_POLL",
                    status="SUCCESS",
                    elapsed_ms=4500,
                    item_count=8,
                    success_count=3,
                    error_count=0,
                    retry_count=0,
                    created_at=current_time - timedelta(days=9),
                ),
            ])

        service = ObservabilityMaintenanceService()
        async with session.begin():
            summary = await service.run_maintenance_for_session(session, now=current_time)

    assert summary["resource_rollups_created"] == 1
    assert summary["execution_rollups_created"] == 2
    assert summary["deleted_resource_rows"] == 1
    assert summary["deleted_execution_rows"] == 1

    async with TestAsyncSessionLocal() as session:
        resource_rollups = (await session.execute(
            select(ResourceHourlyRollup).order_by(ResourceHourlyRollup.bucket_start.asc())
        )).scalars().all()
        execution_rollups = (await session.execute(
            select(ExecutionMetricHourlyRollup).order_by(ExecutionMetricHourlyRollup.bucket_start.asc())
        )).scalars().all()

    assert len(resource_rollups) == 1
    assert resource_rollups[0].sample_count == 2
    assert resource_rollups[0].avg_memory_percent == pytest.approx(62.0)
    assert resource_rollups[0].peak_app_rss_mb == pytest.approx(240.0)
    assert resource_rollups[0].ollama_running_rate == pytest.approx(50.0)

    assert len(execution_rollups) == 2
    llm_rollup = next(row for row in execution_rollups if row.metric_type == "LLM_CALL")
    news_rollup = next(row for row in execution_rollups if row.metric_type == "JOB")
    assert llm_rollup.sample_count == 2
    assert llm_rollup.success_count == 1
    assert llm_rollup.error_count == 1
    assert llm_rollup.fallback_count == 1
    assert llm_rollup.p95_elapsed_ms == pytest.approx(2600.0)
    assert news_rollup.partial_error_count == 1
    assert news_rollup.item_total == 12
    assert news_rollup.retry_total == 1


@pytest.mark.asyncio
async def test_observability_maintenance_service_rebuilds_existing_bucket(monkeypatch):
    current_time = now_kst().replace(minute=40, second=0, microsecond=0)
    bucket = (current_time - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr("services.observability_maintenance_service.settings.METRICS_ROLLUP_LOOKBACK_HOURS", 4)

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetricHourlyRollup))
        await session.execute(delete(ResourceHourlyRollup))
        await session.execute(delete(ExecutionMetric))
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                ResourceHourlyRollup(
                    bucket_start=bucket,
                    scope="LOCAL_RUNTIME",
                    host="mac-local",
                    app_name="momo-trading",
                    environment="local",
                    sample_count=99,
                )
            )
            session.add(
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    memory_percent=55.0,
                    created_at=bucket + timedelta(minutes=10),
                )
            )

        service = ObservabilityMaintenanceService()
        async with session.begin():
            summary = await service.run_maintenance_for_session(session, now=current_time)

    assert summary["resource_rollups_replaced"] == 1

    async with TestAsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ResourceHourlyRollup).order_by(ResourceHourlyRollup.bucket_start.asc())
        )).scalars().all()

    assert len(rows) == 1
    assert rows[0].sample_count == 1


@pytest.mark.asyncio
async def test_observability_maintenance_service_normalizes_missing_provider_model(monkeypatch):
    current_time = now_kst().replace(minute=35, second=0, microsecond=0)
    completed_bucket = (current_time - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr("services.observability_maintenance_service.settings.METRICS_ROLLUP_LOOKBACK_HOURS", 4)

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetricHourlyRollup))
        await session.execute(delete(ResourceHourlyRollup))
        await session.execute(delete(ExecutionMetric))
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            session.add_all([
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="SUCCESS",
                    provider=None,
                    model=None,
                    elapsed_ms=1100,
                    created_at=completed_bucket + timedelta(minutes=3),
                ),
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="ERROR",
                    provider="CODEX",
                    model="gpt-5.4",
                    elapsed_ms=2100,
                    created_at=completed_bucket + timedelta(minutes=13),
                ),
            ])

        service = ObservabilityMaintenanceService()
        async with session.begin():
            summary = await service.run_maintenance_for_session(session, now=current_time)

    assert summary["execution_rollups_created"] == 2

    async with TestAsyncSessionLocal() as session:
        rows = (await session.execute(
            select(ExecutionMetricHourlyRollup).order_by(
                ExecutionMetricHourlyRollup.provider.asc(),
                ExecutionMetricHourlyRollup.model.asc(),
            )
        )).scalars().all()

    assert {(row.provider, row.model) for row in rows} == {
        ("CODEX", "gpt-5.4"),
        ("UNKNOWN", "UNKNOWN"),
    }
