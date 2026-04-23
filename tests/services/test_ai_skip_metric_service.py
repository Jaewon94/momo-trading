import json

import pytest
from sqlalchemy import delete


@pytest.fixture()
def override_ai_skip_metric_session(monkeypatch):
    import services.observability_service as observability_service_module
    from tests.conftest import TestAsyncSessionLocal

    monkeypatch.setattr(
        observability_service_module,
        "AsyncSessionLocal",
        TestAsyncSessionLocal,
    )


@pytest.mark.asyncio
async def test_ai_skip_metric_service_records_execution_metric(override_ai_skip_metric_session):
    from models.execution_metric import ExecutionMetric
    from repositories.execution_metric_repository import ExecutionMetricRepository
    from services.ai_skip_metric_service import AiSkipMetricService
    from tests.conftest import TestAsyncSessionLocal

    service = AiSkipMetricService()

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetric))
        await session.commit()

    await service.record(
        stage="tier1_cache",
        reason_code="cache_hit",
        skipped_tier="TIER1",
        cycle_id="cycle-1",
        symbol="005930",
        detail={"recommendation": "HOLD"},
    )

    async with TestAsyncSessionLocal() as session:
        rows = await ExecutionMetricRepository(session).list_recent(limit=5)

    assert len(rows) == 1
    assert rows[0].metric_type == "AI_SKIPPED"
    assert rows[0].metric_name == "TIER1_CACHE"
    assert rows[0].status == "SKIPPED"
    assert rows[0].cycle_id == "cycle-1"
    assert rows[0].symbol == "005930"
    detail = json.loads(rows[0].detail)
    assert detail["reason_code"] == "CACHE_HIT"
    assert detail["skipped_tier"] == "TIER1"
    assert detail["recommendation"] == "HOLD"
