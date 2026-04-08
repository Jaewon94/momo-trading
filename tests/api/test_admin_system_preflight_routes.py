import pytest
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_system_preflight_route_returns_combined_snapshot(client, monkeypatch):
    async def fake_build_snapshot(_db):
        return {
            "overall": "WARN",
            "probe_symbol": "005930",
            "checks": {
                "broker": {"status": "OK", "ok": True},
                "news": {"status": "WARN", "ok": False, "alerts": ["최근 24시간 신규 적재 0건"]},
                "ollama": {"status": "OK", "ok": True},
            },
            "actions": ["최근 24시간 신규 적재 0건"],
        }

    monkeypatch.setattr(
        "api.routes.admin.system_preflight_service.build_snapshot",
        fake_build_snapshot,
    )

    response = await client.get("/api/v1/admin/system/preflight")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["overall"] == "WARN"
    assert payload["probe_symbol"] == "005930"
    assert payload["checks"]["broker"]["status"] == "OK"
    assert payload["checks"]["news"]["status"] == "WARN"
    assert payload["actions"] == ["최근 24시간 신규 적재 0건"]
