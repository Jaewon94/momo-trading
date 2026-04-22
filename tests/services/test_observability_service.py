import json

import pytest
from sqlalchemy import delete


@pytest.fixture()
def override_observability_session(monkeypatch):
    import services.observability_service as observability_service_module
    from tests.conftest import TestAsyncSessionLocal

    monkeypatch.setattr(
        observability_service_module,
        "AsyncSessionLocal",
        TestAsyncSessionLocal,
    )


@pytest.mark.asyncio
async def test_observability_service_persists_execution_metric(override_observability_session):
    from models.execution_metric import ExecutionMetric
    from repositories.execution_metric_repository import ExecutionMetricRepository
    from services.observability_service import ObservabilityService
    from tests.conftest import TestAsyncSessionLocal

    service = ObservabilityService()

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetric))
        await session.commit()

    await service.record_execution_metric(
        metric_type="JOB",
        metric_name="NEWS_POLL",
        status="SUCCESS",
        elapsed_ms=1234,
        item_count=12,
        success_count=5,
        error_count=1,
        fallback_used=False,
        detail={"mode": "AUTO_TRADING"},
    )

    async with TestAsyncSessionLocal() as session:
        rows = await ExecutionMetricRepository(session).list_recent(limit=5)

    assert len(rows) == 1
    assert rows[0].metric_type == "JOB"
    assert rows[0].metric_name == "NEWS_POLL"
    assert rows[0].elapsed_ms == 1234
    assert json.loads(rows[0].detail)["mode"] == "AUTO_TRADING"


@pytest.mark.asyncio
async def test_observability_service_persists_resource_snapshot(override_observability_session):
    from models.resource_snapshot import ResourceSnapshot
    from repositories.resource_snapshot_repository import ResourceSnapshotRepository
    from services.observability_service import ObservabilityService
    from tests.conftest import TestAsyncSessionLocal

    service = ObservabilityService()

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ResourceSnapshot))
        await session.commit()

    await service.record_resource_snapshot({
        "scope": "LOCAL_RUNTIME",
        "host": "test-host",
        "app_name": "momo-trading",
        "environment": "local",
        "python_version": "3.13.12",
        "platform_system": "Darwin",
        "platform_release": "24.0.0",
        "platform_machine": "arm64",
        "cpu_count": 8,
        "app_pid": 12345,
        "cpu_load_1m": 1.5,
        "cpu_load_5m": 1.0,
        "cpu_load_15m": 0.8,
        "cpu_load_ratio_1m": 0.3,
        "cpu_load_ratio_5m": 0.2,
        "cpu_load_ratio_15m": 0.16,
        "process_cpu_time_sec": 42.0,
        "total_memory_mb": 32768.0,
        "memory_used_mb": 1024.0,
        "memory_available_mb": 2048.0,
        "memory_percent": 33.3,
        "swap_used_mb": 0.0,
        "disk_total_gb": 512.0,
        "disk_used_gb": 256.0,
        "disk_available_gb": 256.0,
        "disk_used_percent": 71.2,
        "app_rss_mb": 250.5,
        "ollama_rss_mb": 4096.0,
        "ollama_pid_count": 1,
        "ollama_running": True,
        "detail": {"collector": "test"},
    })

    async with TestAsyncSessionLocal() as session:
        rows = await ResourceSnapshotRepository(session).list_recent(limit=5)

    assert len(rows) == 1
    assert rows[0].host == "test-host"
    assert rows[0].app_name == "momo-trading"
    assert rows[0].environment == "local"
    assert rows[0].python_version == "3.13.12"
    assert rows[0].cpu_count == 8
    assert rows[0].total_memory_mb == pytest.approx(32768.0)
    assert rows[0].disk_total_gb == pytest.approx(512.0)
    assert rows[0].ollama_pid_count == 1
    assert rows[0].ollama_running is True
    assert rows[0].memory_percent == pytest.approx(33.3)
    assert json.loads(rows[0].detail)["collector"] == "test"
