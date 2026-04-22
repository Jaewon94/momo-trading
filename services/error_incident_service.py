"""운영 incident 상태 변경 서비스."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.error_incident_repository import ErrorIncidentRepository


class ErrorIncidentService:
    _VALID_STATUSES = {"OPEN", "RESOLVED", "MUTED"}

    async def update_incident(
        self,
        session: AsyncSession,
        *,
        fingerprint: str,
        status: str | None = None,
        owner_note: str | None = None,
    ) -> dict | None:
        repo = ErrorIncidentRepository(session)
        incident = await repo.get_by_fingerprint(fingerprint)
        if incident is None:
            return None

        if status is not None:
            incident.status = self._normalize_status(status)
        if owner_note is not None:
            incident.owner_note = str(owner_note).strip() or None

        await repo.update(incident)
        await session.commit()
        return self.serialize_incident(incident)

    def _normalize_status(self, status: str | None) -> str:
        normalized = str(status or "").upper().strip()
        if normalized not in self._VALID_STATUSES:
            raise ValueError(f"invalid incident status: {status}")
        return normalized

    @staticmethod
    def serialize_incident(incident) -> dict:
        return {
            "fingerprint": incident.fingerprint,
            "title": incident.title,
            "component": incident.component,
            "operation": incident.operation,
            "severity": incident.severity,
            "status": incident.status,
            "occurrence_count": int(incident.occurrence_count or 0),
            "exception_type": incident.exception_type,
            "last_message": incident.last_message,
            "last_seen_at": incident.last_seen_at.isoformat() if incident.last_seen_at else None,
            "owner_note": incident.owner_note,
        }


error_incident_service = ErrorIncidentService()
