from __future__ import annotations

import asyncio
import time as _time

from fastapi import HTTPException

from core.config import settings
from trading.enums import ActivityPhase, ActivityType


class RuntimeReconfigurationService:
    def __init__(
        self,
        *,
        settings_service=None,
        scheduler=None,
        trading_agent=None,
        llm_runtime=None,
        activity_logger_instance=None,
        settings_obj=settings,
        idle_timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.1,
    ):
        self._settings_service = settings_service
        self._scheduler = scheduler
        self._trading_agent = trading_agent
        self._llm_runtime = llm_runtime
        self._activity_logger = activity_logger_instance
        self._settings_obj = settings_obj
        self._idle_timeout_sec = idle_timeout_sec
        self._poll_interval_sec = poll_interval_sec
        self._lock = asyncio.Lock()
        self._active = False

    def is_reconfiguring(self) -> bool:
        return self._active

    def _resolve_settings_service(self):
        if self._settings_service is not None:
            return self._settings_service
        from services.runtime_settings_service import runtime_settings_service

        return runtime_settings_service

    def _resolve_scheduler(self):
        if self._scheduler is not None:
            return self._scheduler
        from scheduler.scheduler import trading_scheduler

        return trading_scheduler

    def _resolve_trading_agent(self):
        if self._trading_agent is not None:
            return self._trading_agent
        from agent.trading_agent import trading_agent

        return trading_agent

    def _resolve_llm_runtime(self):
        if self._llm_runtime is not None:
            return self._llm_runtime
        from analysis.llm.llm_factory import llm_factory

        return llm_factory

    def _resolve_activity_logger(self):
        if self._activity_logger is not None:
            return self._activity_logger
        from services.activity_logger import activity_logger

        return activity_logger

    async def _wait_for_agent_idle(self, trading_agent) -> bool:
        wait = getattr(trading_agent, "wait_until_idle", None)
        if wait is None:
            return True
        return bool(
            await wait(
                timeout_sec=self._idle_timeout_sec,
                poll_interval_sec=self._poll_interval_sec,
            )
        )

    async def _wait_for_scheduler_idle(self, scheduler) -> bool:
        wait = getattr(scheduler, "wait_until_idle", None)
        if wait is None:
            return True
        return bool(
            await wait(
                timeout_sec=self._idle_timeout_sec,
                poll_interval_sec=self._poll_interval_sec,
            )
        )

    async def apply_settings(self, updates: dict):
        if self._lock.locked():
            raise HTTPException(status_code=409, detail="runtime_reconfiguration_in_progress")

        settings_service = self._resolve_settings_service()
        scheduler = self._resolve_scheduler()
        trading_agent = self._resolve_trading_agent()
        llm_runtime = self._resolve_llm_runtime()
        activity_logger = self._resolve_activity_logger()

        async with self._lock:
            self._active = True
            try:
                started_at = _time.perf_counter()
                scheduler_was_running = bool(getattr(scheduler, "is_running", False))

                await activity_logger.log(
                    ActivityType.EVENT,
                    ActivityPhase.PROGRESS,
                    "⚙️ 설정 적용 시작: 새 작업을 멈추고 현재 작업 종료를 대기합니다.",
                    detail={"updates": sorted(updates.keys())},
                )

                if scheduler_was_running:
                    await scheduler.stop()

                agent_idle = await self._wait_for_agent_idle(trading_agent)
                scheduler_idle = await self._wait_for_scheduler_idle(scheduler)
                changed = await settings_service.update_settings(updates)

                reset_runtime = getattr(llm_runtime, "reset_runtime_state", None)
                if callable(reset_runtime):
                    reset_runtime()
                else:
                    end_session = getattr(llm_runtime, "end_session", None)
                    if callable(end_session):
                        end_session()

                scheduler_should_run = bool(
                    getattr(self._settings_obj, "SCHEDULER_ENABLED", False)
                    or getattr(self._settings_obj, "NEWS_POLL_ENABLED", False)
                )
                scheduler_restarted = False
                if scheduler_should_run:
                    await scheduler.start()
                    scheduler_restarted = True

                elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
                result = {
                    "changed": changed,
                    "reconfiguration": {
                        "scheduler_was_running": scheduler_was_running,
                        "scheduler_restarted": scheduler_restarted,
                        "agent_idle": agent_idle,
                        "scheduler_idle": scheduler_idle,
                        "elapsed_ms": elapsed_ms,
                    },
                }

                await activity_logger.log(
                    ActivityType.EVENT,
                    ActivityPhase.COMPLETE,
                    f"⚙️ 설정 적용 완료: {len(changed)}개 변경",
                    detail=result,
                    execution_time_ms=elapsed_ms,
                )
                return result
            finally:
                self._active = False


runtime_reconfiguration_service = RuntimeReconfigurationService()
