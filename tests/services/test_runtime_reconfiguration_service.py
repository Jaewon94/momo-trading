import asyncio
from types import SimpleNamespace
from time import perf_counter

import pytest

from services.runtime_reconfiguration_service import RuntimeReconfigurationService


@pytest.mark.asyncio
async def test_runtime_reconfiguration_service_drains_runtime_before_applying_and_restarts_scheduler():
    settings_obj = SimpleNamespace(SCHEDULER_ENABLED=True, NEWS_POLL_ENABLED=False)
    call_order: list[str] = []

    class FakeSettingsService:
        async def update_settings(self, updates):
            call_order.append("settings.apply")
            settings_obj.LLM_TIER1_CONCURRENCY = int(updates["LLM_TIER1_CONCURRENCY"])
            return {
                "LLM_TIER1_CONCURRENCY": {
                    "old": 2,
                    "new": settings_obj.LLM_TIER1_CONCURRENCY,
                }
            }

    class FakeScheduler:
        def __init__(self):
            self.is_running = True

        async def stop(self):
            call_order.append("scheduler.stop")
            self.is_running = False

        async def start(self):
            call_order.append("scheduler.start")
            self.is_running = True

        async def wait_until_idle(self, **_kwargs):
            call_order.append("scheduler.wait")
            return True

    class FakeAgent:
        async def wait_until_idle(self, **_kwargs):
            call_order.append("agent.wait")
            return True

    class FakeLLMRuntime:
        def reset_runtime_state(self):
            call_order.append("llm.reset")

    class FakeActivityLogger:
        async def log(self, *_args, **_kwargs):
            call_order.append("activity.log")

    service = RuntimeReconfigurationService(
        settings_service=FakeSettingsService(),
        scheduler=FakeScheduler(),
        trading_agent=FakeAgent(),
        llm_runtime=FakeLLMRuntime(),
        activity_logger_instance=FakeActivityLogger(),
        settings_obj=settings_obj,
        idle_timeout_sec=0.1,
        poll_interval_sec=0.01,
    )

    result = await service.apply_settings({"LLM_TIER1_CONCURRENCY": 3})

    assert result["changed"]["LLM_TIER1_CONCURRENCY"]["new"] == 3
    assert result["reconfiguration"]["scheduler_restarted"] is True
    assert result["reconfiguration"]["agent_idle"] is True
    assert result["reconfiguration"]["scheduler_idle"] is True
    assert service.is_reconfiguring() is False
    assert call_order == [
        "activity.log",
        "scheduler.stop",
        "agent.wait",
        "scheduler.wait",
        "settings.apply",
        "llm.reset",
        "scheduler.start",
        "activity.log",
    ]


@pytest.mark.asyncio
async def test_runtime_reconfiguration_service_waits_for_agent_and_scheduler_concurrently():
    settings_obj = SimpleNamespace(SCHEDULER_ENABLED=False, NEWS_POLL_ENABLED=False)

    class FakeSettingsService:
        async def update_settings(self, updates):
            return updates

    class FakeScheduler:
        def __init__(self):
            self.is_running = True

        async def stop(self):
            self.is_running = False

        async def start(self):
            self.is_running = True

        async def wait_until_idle(self, **_kwargs):
            await asyncio.sleep(0.05)
            return True

    class FakeAgent:
        async def wait_until_idle(self, **_kwargs):
            await asyncio.sleep(0.05)
            return True

    class FakeLLMRuntime:
        def reset_runtime_state(self):
            return None

    class FakeActivityLogger:
        async def log(self, *_args, **_kwargs):
            return None

    service = RuntimeReconfigurationService(
        settings_service=FakeSettingsService(),
        scheduler=FakeScheduler(),
        trading_agent=FakeAgent(),
        llm_runtime=FakeLLMRuntime(),
        activity_logger_instance=FakeActivityLogger(),
        settings_obj=settings_obj,
        idle_timeout_sec=0.2,
        poll_interval_sec=0.01,
    )

    started_at = perf_counter()
    result = await service.apply_settings({"LLM_TIER1_CONCURRENCY": 3})
    elapsed = perf_counter() - started_at

    assert result["reconfiguration"]["agent_idle"] is True
    assert result["reconfiguration"]["scheduler_idle"] is True
    assert elapsed < 0.09


@pytest.mark.asyncio
async def test_runtime_reconfiguration_service_keeps_scheduler_stopped_when_disabled_by_new_settings():
    settings_obj = SimpleNamespace(SCHEDULER_ENABLED=True, NEWS_POLL_ENABLED=False)
    call_order: list[str] = []

    class FakeSettingsService:
        async def update_settings(self, updates):
            call_order.append("settings.apply")
            settings_obj.SCHEDULER_ENABLED = bool(updates["SCHEDULER_ENABLED"])
            return {
                "SCHEDULER_ENABLED": {
                    "old": True,
                    "new": settings_obj.SCHEDULER_ENABLED,
                }
            }

    class FakeScheduler:
        def __init__(self):
            self.is_running = True

        async def stop(self):
            call_order.append("scheduler.stop")
            self.is_running = False

        async def start(self):
            call_order.append("scheduler.start")
            self.is_running = True

        async def wait_until_idle(self, **_kwargs):
            call_order.append("scheduler.wait")
            return True

    class FakeAgent:
        async def wait_until_idle(self, **_kwargs):
            call_order.append("agent.wait")
            return True

    class FakeLLMRuntime:
        def reset_runtime_state(self):
            call_order.append("llm.reset")

    class FakeActivityLogger:
        async def log(self, *_args, **_kwargs):
            return None

    service = RuntimeReconfigurationService(
        settings_service=FakeSettingsService(),
        scheduler=FakeScheduler(),
        trading_agent=FakeAgent(),
        llm_runtime=FakeLLMRuntime(),
        activity_logger_instance=FakeActivityLogger(),
        settings_obj=settings_obj,
        idle_timeout_sec=0.1,
        poll_interval_sec=0.01,
    )

    result = await service.apply_settings({"SCHEDULER_ENABLED": False})

    assert result["changed"]["SCHEDULER_ENABLED"]["new"] is False
    assert result["reconfiguration"]["scheduler_restarted"] is False
    assert "scheduler.start" not in call_order
