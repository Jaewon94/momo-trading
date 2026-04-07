from datetime import timedelta

import pytest
from sqlalchemy import delete

from models.execution_metric import ExecutionMetric
from models.execution_metric_hourly_rollup import ExecutionMetricHourlyRollup
from models.resource_hourly_rollup import ResourceHourlyRollup
from models.resource_snapshot import ResourceSnapshot
from services.observability_reporting_service import ObservabilityReportingService
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_observability_reporting_service_builds_overview_from_recent_metrics():
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetricHourlyRollup))
        await session.execute(delete(ResourceHourlyRollup))
        await session.execute(delete(ExecutionMetric))
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            now = now_kst()
            session.add_all([
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    python_version="3.13.12",
                    platform_system="Darwin",
                    platform_release="25.3.0",
                    platform_machine="arm64",
                    cpu_count=10,
                    app_pid=111,
                    cpu_load_ratio_1m=0.7,
                    memory_percent=61.2,
                    app_rss_mb=220.0,
                    ollama_rss_mb=4096.0,
                    ollama_running=True,
                    disk_used_percent=58.1,
                    created_at=now - timedelta(minutes=20),
                ),
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    python_version="3.13.12",
                    platform_system="Darwin",
                    platform_release="25.3.0",
                    platform_machine="arm64",
                    cpu_count=10,
                    app_pid=111,
                    cpu_load_ratio_1m=0.9,
                    memory_percent=63.5,
                    app_rss_mb=240.0,
                    ollama_rss_mb=4200.0,
                    ollama_running=True,
                    disk_used_percent=58.4,
                    created_at=now - timedelta(minutes=5),
                ),
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="SUCCESS",
                    provider="OLLAMA",
                    model="ollama:qwen3:14b",
                    elapsed_ms=1500,
                    fallback_used=False,
                    created_at=now - timedelta(minutes=10),
                ),
                ExecutionMetric(
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    status="ERROR",
                    provider="OLLAMA",
                    model="ollama:qwen3:14b",
                    elapsed_ms=2200,
                    fallback_used=True,
                    created_at=now - timedelta(minutes=8),
                ),
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="NEWS_POLL",
                    status="SUCCESS",
                    elapsed_ms=4800,
                    item_count=12,
                    success_count=5,
                    error_count=0,
                    created_at=now - timedelta(minutes=12),
                ),
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="NEWS_POLL",
                    status="PARTIAL_ERROR",
                    elapsed_ms=6200,
                    item_count=8,
                    success_count=3,
                    error_count=2,
                    created_at=now - timedelta(minutes=6),
                ),
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="OBSERVABILITY_MAINTENANCE",
                    status="SUCCESS",
                    elapsed_ms=320,
                    detail='{"resource_rollups_created": 1, "execution_rollups_created": 2, "deleted_resource_rows": 4, "deleted_execution_rows": 1}',
                    created_at=now - timedelta(minutes=4),
                ),
            ])

        service = ObservabilityReportingService()
        payload = await service.build_overview(session, hours=24, points=120)

    assert payload["latest_snapshot"]["host"] == "mac-local"
    assert payload["latest_snapshot"]["memory_percent"] == pytest.approx(63.5)
    assert payload["resource_summary"]["snapshot_count"] == 2
    assert payload["resource_summary"]["peak_app_rss_mb"] == pytest.approx(240.0)
    assert payload["window"]["resolution"] == "raw"
    assert payload["llm"]["total_calls"] == 2
    assert payload["llm"]["success_rate"] == pytest.approx(50.0)
    assert payload["llm"]["fallback_rate"] == pytest.approx(50.0)
    assert payload["llm"]["provider_breakdown"][0]["provider"] == "OLLAMA"
    assert payload["jobs"]["news_poll"]["runs"] == 2
    assert payload["jobs"]["news_poll"]["created_total"] == 8
    assert payload["jobs"]["news_poll"]["source_error_total"] == 2
    assert payload["jobs"]["maintenance"]["last_status"] == "SUCCESS"
    assert payload["jobs"]["maintenance"]["last_deleted_resource_rows"] == 4
    assert payload["recommendations"]["news_translation"]["current"]["provider"] in {"CLAUDE_CODE", "OLLAMA", "CODEX"}
    assert len(payload["trends"]["llm"]) == 1
    assert payload["trends"]["llm"][0]["calls"] == 2
    assert sum(point["created_total"] for point in payload["trends"]["news_poll"]) == 8
    assert payload["storage"]["raw_retention_days"] >= 1


@pytest.mark.asyncio
async def test_observability_reporting_service_uses_hourly_rollups_for_long_windows():
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetricHourlyRollup))
        await session.execute(delete(ResourceHourlyRollup))
        await session.execute(delete(ExecutionMetric))
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            now = now_kst().replace(minute=0, second=0, microsecond=0)
            session.add(
                ResourceSnapshot(
                    host="mac-local",
                    scope="LOCAL_RUNTIME",
                    app_name="momo-trading",
                    environment="local",
                    memory_percent=63.5,
                    created_at=now - timedelta(minutes=5),
                )
            )
            session.add_all([
                ResourceHourlyRollup(
                    bucket_start=now - timedelta(days=6),
                    scope="LOCAL_RUNTIME",
                    host="mac-local",
                    app_name="momo-trading",
                    environment="local",
                    sample_count=12,
                    avg_cpu_load_ratio_1m=0.4,
                    peak_cpu_load_ratio_1m=0.8,
                    avg_memory_percent=55.0,
                    peak_memory_percent=61.0,
                    avg_app_rss_mb=180.0,
                    peak_app_rss_mb=210.0,
                    avg_ollama_rss_mb=2048.0,
                    peak_ollama_rss_mb=3072.0,
                ),
                ResourceHourlyRollup(
                    bucket_start=now - timedelta(days=1),
                    scope="LOCAL_RUNTIME",
                    host="mac-local",
                    app_name="momo-trading",
                    environment="local",
                    sample_count=10,
                    avg_cpu_load_ratio_1m=0.5,
                    peak_cpu_load_ratio_1m=0.9,
                    avg_memory_percent=58.0,
                    peak_memory_percent=64.0,
                    avg_app_rss_mb=190.0,
                    peak_app_rss_mb=220.0,
                    avg_ollama_rss_mb=2200.0,
                    peak_ollama_rss_mb=3200.0,
                ),
                ExecutionMetricHourlyRollup(
                    bucket_start=now - timedelta(days=6),
                    metric_type="LLM_CALL",
                    metric_name="LLM_GENERATE",
                    provider="OLLAMA",
                    model="ollama:qwen3:14b",
                    sample_count=3,
                    success_count=2,
                    avg_elapsed_ms=1700.0,
                    p95_elapsed_ms=2200.0,
                ),
                ExecutionMetricHourlyRollup(
                    bucket_start=now - timedelta(days=1),
                    metric_type="JOB",
                    metric_name="NEWS_POLL",
                    sample_count=4,
                    success_count=3,
                    partial_error_count=1,
                    item_total=18,
                    success_total=7,
                    error_total=2,
                    avg_elapsed_ms=5100.0,
                    p95_elapsed_ms=6200.0,
                ),
            ])

        service = ObservabilityReportingService()
        payload = await service.build_overview(session, hours=24 * 7, points=168)

    assert payload["window"]["resolution"] == "hourly_rollup"
    assert len(payload["resource_series"]) == 2
    assert payload["resource_summary"]["snapshot_count"] == 22
    assert payload["resource_series"][0]["sample_count"] == 12
    assert payload["trends"]["llm"][0]["calls"] == 3
    assert payload["trends"]["news_poll"][0]["created_total"] == 7
