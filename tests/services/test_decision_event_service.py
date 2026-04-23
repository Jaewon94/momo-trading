import json

import pytest
from sqlalchemy import delete, select

from models.decision_event import DecisionEvent
from services.decision_event_service import DecisionEventService
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_decision_event_service_records_canonical_event() -> None:
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(DecisionEvent))
        await session.commit()

    service = DecisionEventService(session_factory=TestAsyncSessionLocal)

    event = await service.record_event(
        cycle_id="cycle-1",
        symbol="005930",
        stock_name="삼성전자",
        market="KRX",
        decision_stage="FINAL",
        source="decision_maker",
        strategy_type="STABLE_SHORT",
        scanner_score=0.82,
        tier1_decision="BUY",
        tier2_decision="HOLD",
        risk_gate_result="PASS",
        final_action="BUY",
        confidence=0.76,
        reference_price=71_000,
        quantity=3,
        provider="CODEX",
        model="gpt-5.4",
        elapsed_ms=1234,
        status="RECORDED",
        reason="테스트 근거",
        metadata={"news_pressure": 0.2},
    )

    assert event.id

    async with TestAsyncSessionLocal() as session:
        rows = (await session.execute(select(DecisionEvent))).scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "005930"
    assert row.final_action == "BUY"
    assert row.provider == "CODEX"
    assert row.model == "gpt-5.4"
    assert row.elapsed_ms == 1234
    assert json.loads(row.metadata_json) == {"news_pressure": 0.2}


@pytest.mark.asyncio
async def test_decision_event_service_normalizes_empty_optional_fields() -> None:
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(DecisionEvent))
        await session.commit()

    service = DecisionEventService(session_factory=TestAsyncSessionLocal)

    event = await service.record_event(
        cycle_id=None,
        symbol="A005930",
        stock_name="",
        market="",
        decision_stage="",
        source="",
        final_action="skip",
    )

    assert event.symbol == "005930"
    assert event.stock_name == "005930"
    assert event.market == "KRX"
    assert event.decision_stage == "UNKNOWN"
    assert event.source == "UNKNOWN"
    assert event.final_action == "SKIP"
    assert event.provider == "UNKNOWN"
    assert event.model == "UNKNOWN"
