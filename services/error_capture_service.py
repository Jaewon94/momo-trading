"""운영 에러 이벤트/incident 캡처 서비스."""
from __future__ import annotations

import hashlib
import json
import traceback
from typing import Any

from loguru import logger

from core.database import AsyncSessionLocal
from models.error_event import ErrorEvent
from models.error_incident import ErrorIncident
from repositories.error_event_repository import ErrorEventRepository
from repositories.error_incident_repository import ErrorIncidentRepository
from util.time_util import now_kst


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


class ErrorCaptureService:
    async def capture_exception(
        self,
        *,
        component: str,
        operation: str,
        exc: Exception,
        severity: str = "ERROR",
        handled: bool = True,
        cycle_id: str | None = None,
        symbol: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        exception_type = exc.__class__.__name__
        exception_message = _truncate(str(exc), 1000) or exception_type
        fingerprint = self._build_fingerprint(
            component=component,
            operation=operation,
            exception_type=exception_type,
            exception_message=exception_message,
        )
        stacktrace = _truncate("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), 8000)
        detail_json = json.dumps(detail, ensure_ascii=False, default=str) if detail else None
        now = now_kst()

        event = ErrorEvent(
            fingerprint=fingerprint,
            severity=severity,
            component=component,
            operation=operation,
            handled=handled,
            exception_type=exception_type,
            exception_message=exception_message,
            stacktrace=stacktrace,
            cycle_id=cycle_id,
            symbol=symbol,
            provider=provider,
            model=model,
            detail=detail_json,
        )

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await ErrorEventRepository(session).create(event)
                    incident_repo = ErrorIncidentRepository(session)
                    incident = await incident_repo.get_by_fingerprint(fingerprint)
                    if incident is None:
                        incident = ErrorIncident(
                            fingerprint=fingerprint,
                            title=_truncate(f"{component} · {operation} · {exception_type}", 200) or component,
                            component=component,
                            operation=operation,
                            severity=severity,
                            status="OPEN",
                            first_seen_at=now,
                            last_seen_at=now,
                            occurrence_count=1,
                            exception_type=exception_type,
                            last_message=exception_message,
                            last_symbol=symbol,
                            last_provider=provider,
                        )
                        await incident_repo.create(incident)
                    else:
                        incident.severity = severity
                        incident.last_seen_at = now
                        incident.occurrence_count = int(incident.occurrence_count or 0) + 1
                        incident.exception_type = exception_type
                        incident.last_message = exception_message
                        incident.last_symbol = symbol
                        incident.last_provider = provider
                        await incident_repo.update(incident)
            return {
                "fingerprint": fingerprint,
                "exception_type": exception_type,
                "exception_message": exception_message,
            }
        except Exception as storage_exc:
            logger.error("에러 캡처 저장 실패: {}", str(storage_exc))
            return None

    @staticmethod
    def _build_fingerprint(
        *,
        component: str,
        operation: str,
        exception_type: str,
        exception_message: str,
    ) -> str:
        seed = "|".join([
            component.strip().lower(),
            operation.strip().lower(),
            exception_type.strip().lower(),
            exception_message.strip().lower()[:160],
        ])
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:32]


error_capture_service = ErrorCaptureService()
