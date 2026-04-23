import pytest
from sqlalchemy import delete

from models.execution_metric import ExecutionMetric
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_system_preflight_service_captures_broker_probe_failure(monkeypatch):
    from services.system_preflight_service import SystemPreflightService

    captured = {}

    class DummyAdapter:
        async def get_holdings(self):
            return []

    async def fake_run_broker_smoke_test(**_kwargs):
        raise RuntimeError("broker smoke failed")

    async def fake_capture_exception(**kwargs):
        captured.update(kwargs)
        return {"fingerprint": "preflight-broker"}

    async def fake_build_overview(_db, **_kwargs):
        return {
            "health": {"status": "OK", "alerts": []},
            "runtime": {"overall": {"last_message": "ok", "last_status": "SUCCESS", "last_run_at": None}},
        }

    async def fake_ollama_check():
        return {"status": "OK", "label": "Ollama 준비", "message": "ok", "ok": True}

    monkeypatch.setattr("services.system_preflight_service.get_broker_adapter", lambda: DummyAdapter())
    monkeypatch.setattr("services.system_preflight_service.run_broker_smoke_test", fake_run_broker_smoke_test)
    monkeypatch.setattr("services.system_preflight_service.news_reporting_service.build_overview", fake_build_overview)
    monkeypatch.setattr("services.system_preflight_service.error_capture_service.capture_exception", fake_capture_exception)
    monkeypatch.setattr(SystemPreflightService, "_build_ollama_check", staticmethod(fake_ollama_check))

    service = SystemPreflightService()
    snapshot = await service.build_snapshot(db=None)

    assert snapshot["overall"] == "ERROR"
    assert snapshot["checks"]["broker"]["status"] == "ERROR"
    assert snapshot["checks"]["broker"]["ok"] is False
    assert captured["component"] == "preflight"
    assert captured["operation"] == "broker_check"


@pytest.mark.asyncio
async def test_system_preflight_service_warns_on_recent_observability_maintenance_failure(monkeypatch):
    from services.system_preflight_service import SystemPreflightService

    class DummyAdapter:
        async def get_holdings(self):
            return []

    async def fake_run_broker_smoke_test(**_kwargs):
        return {"checks": {"balance": {"ok": True}, "holdings": {"ok": True}}}

    async def fake_build_overview(_db, **_kwargs):
        return {
            "health": {"status": "OK", "alerts": []},
            "runtime": {"overall": {"last_message": "ok", "last_status": "SUCCESS", "last_run_at": None}},
        }

    async def fake_ollama_check():
        return {"status": "OK", "label": "Ollama 준비", "message": "ok", "ok": True}

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(ExecutionMetric))
        await session.commit()

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                ExecutionMetric(
                    metric_type="JOB",
                    metric_name="OBSERVABILITY_MAINTENANCE",
                    status="ERROR",
                    elapsed_ms=1200,
                    detail='{"error": "rollup failed"}',
                    created_at=now_kst(),
                )
            )

        monkeypatch.setattr("services.system_preflight_service.get_broker_adapter", lambda: DummyAdapter())
        monkeypatch.setattr("services.system_preflight_service.run_broker_smoke_test", fake_run_broker_smoke_test)
        monkeypatch.setattr("services.system_preflight_service.news_reporting_service.build_overview", fake_build_overview)
        monkeypatch.setattr(SystemPreflightService, "_build_ollama_check", staticmethod(fake_ollama_check))

        service = SystemPreflightService()
        snapshot = await service.build_snapshot(db=session)

    assert snapshot["overall"] == "WARN"
    assert snapshot["checks"]["observability"]["status"] == "WARN"
    assert snapshot["checks"]["observability"]["ok"] is False
    assert "rollup failed" in snapshot["checks"]["observability"]["message"]
    assert "관측성 유지보수" in snapshot["actions"][-1]
