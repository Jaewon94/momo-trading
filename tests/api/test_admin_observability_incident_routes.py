from sqlalchemy import delete

from models.error_incident import ErrorIncident
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


async def test_admin_observability_incident_update_route_persists_status_and_note(client):
    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ErrorIncident))
        session.add(
            ErrorIncident(
                fingerprint="incident-1",
                title="scheduler · news_poll · RuntimeError",
                component="scheduler",
                operation="news_poll",
                severity="ERROR",
                status="OPEN",
                first_seen_at=now_kst(),
                last_seen_at=now_kst(),
                occurrence_count=1,
                exception_type="RuntimeError",
                last_message="poll failed",
            )
        )
        await session.commit()

    response = await client.patch(
        "/api/v1/admin/observability/incidents/incident-1",
        json={"status": "MUTED", "owner_note": "ignore until market close"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["fingerprint"] == "incident-1"
    assert payload["status"] == "MUTED"
    assert payload["owner_note"] == "ignore until market close"
