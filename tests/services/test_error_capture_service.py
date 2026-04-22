import json

import pytest
from sqlalchemy import delete

from models.error_event import ErrorEvent
from models.error_incident import ErrorIncident
from repositories.error_event_repository import ErrorEventRepository
from repositories.error_incident_repository import ErrorIncidentRepository
from services.error_capture_service import ErrorCaptureService
from tests.conftest import TestAsyncSessionLocal


@pytest.fixture()
def override_error_capture_session(monkeypatch):
    import services.error_capture_service as error_capture_service_module

    monkeypatch.setattr(
        error_capture_service_module,
        "AsyncSessionLocal",
        TestAsyncSessionLocal,
    )


@pytest.mark.asyncio
async def test_error_capture_service_persists_event_and_incident(override_error_capture_session):
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ErrorEvent))
        await session.execute(delete(ErrorIncident))
        await session.commit()

    service = ErrorCaptureService()
    await service.capture_exception(
        component="news_polling",
        operation="poll_source:BLOOMBERG",
        exc=RuntimeError("source timeout"),
        symbol="AAPL",
        provider="OLLAMA",
        model="qwen3:8b",
        detail={"source_code": "BLOOMBERG"},
    )

    async with TestAsyncSessionLocal() as session:
        events = await ErrorEventRepository(session).list_recent(limit=5)
        incidents = await ErrorIncidentRepository(session).list_recent(limit=5)

    assert len(events) == 1
    assert events[0].component == "news_polling"
    assert events[0].exception_type == "RuntimeError"
    assert json.loads(events[0].detail)["source_code"] == "BLOOMBERG"
    assert len(incidents) == 1
    assert incidents[0].occurrence_count == 1
    assert incidents[0].first_seen_at is not None
    assert incidents[0].last_seen_at is not None


@pytest.mark.asyncio
async def test_error_capture_service_accumulates_same_fingerprint(override_error_capture_session):
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ErrorEvent))
        await session.execute(delete(ErrorIncident))
        await session.commit()

    service = ErrorCaptureService()
    await service.capture_exception(
        component="scheduler",
        operation="news_poll",
        exc=RuntimeError("poll failed"),
    )
    await service.capture_exception(
        component="scheduler",
        operation="news_poll",
        exc=RuntimeError("poll failed"),
    )

    async with TestAsyncSessionLocal() as session:
        incidents = await ErrorIncidentRepository(session).list_recent(limit=5)

    assert len(incidents) == 1
    assert incidents[0].occurrence_count == 2
    assert incidents[0].last_message == "poll failed"


@pytest.mark.asyncio
async def test_error_capture_service_reopens_resolved_incident_on_recurrence(override_error_capture_session):
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ErrorEvent))
        await session.execute(delete(ErrorIncident))
        await session.commit()

    service = ErrorCaptureService()
    await service.capture_exception(
        component="scheduler",
        operation="news_poll",
        exc=RuntimeError("poll failed"),
    )

    async with TestAsyncSessionLocal() as session:
        incident_repo = ErrorIncidentRepository(session)
        incident = (await incident_repo.list_recent(limit=1))[0]
        incident.status = "RESOLVED"
        incident.owner_note = "operator checked"
        await incident_repo.update(incident)
        await session.commit()

    await service.capture_exception(
        component="scheduler",
        operation="news_poll",
        exc=RuntimeError("poll failed"),
    )

    async with TestAsyncSessionLocal() as session:
        incidents = await ErrorIncidentRepository(session).list_recent(limit=5)

    assert len(incidents) == 1
    assert incidents[0].status == "OPEN"
    assert incidents[0].owner_note == "operator checked"
    assert incidents[0].occurrence_count == 2
