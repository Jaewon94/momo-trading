"""Rollout-mode policy for the buy-side news gate."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal
from services.performance_reporting_service import performance_reporting_service


NEWS_GATE_ROLLOUT_MODES = {"OFF", "POLL_ONLY", "SHADOW_ONLY", "BUY_BLOCK_GATE"}


@dataclass
class NewsGateRolloutDecision:
    requested_mode: str
    effective_mode: str
    evaluate_gate: bool
    block_buy: bool
    record_shadow: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


class NewsGateRolloutService:
    ROLLOUT_STATUS_TTL_SEC = 300

    def __init__(self) -> None:
        self._cached_rollout_status: dict | None = None
        self._cached_at: float = 0.0

    async def resolve(self) -> NewsGateRolloutDecision:
        requested = self._requested_mode()
        if requested:
            return await self._resolve_explicit_mode(requested)
        return self._resolve_legacy_mode()

    def should_record_shadow(self) -> bool:
        requested = self._requested_mode()
        if requested in {"SHADOW_ONLY", "BUY_BLOCK_GATE"}:
            return True
        if requested in {"OFF", "POLL_ONLY"}:
            return False
        return bool(getattr(settings, "NEWS_SHADOW_ENABLED", True))

    def clear_cache(self) -> None:
        self._cached_rollout_status = None
        self._cached_at = 0.0

    @staticmethod
    def _requested_mode() -> str:
        raw = str(getattr(settings, "NEWS_GATE_ROLLOUT_MODE", "") or "").strip().upper()
        return raw if raw in NEWS_GATE_ROLLOUT_MODES else ""

    def _resolve_legacy_mode(self) -> NewsGateRolloutDecision:
        gate_enabled = bool(getattr(settings, "NEWS_GATE_ENABLED", True))
        shadow_enabled = bool(getattr(settings, "NEWS_SHADOW_ENABLED", True))
        poll_enabled = bool(getattr(settings, "NEWS_POLL_ENABLED", True))
        if gate_enabled:
            effective = "BUY_BLOCK_GATE"
            return NewsGateRolloutDecision(
                requested_mode="LEGACY",
                effective_mode=effective,
                evaluate_gate=True,
                block_buy=True,
                record_shadow=shadow_enabled,
                reason="legacy NEWS_GATE_ENABLED=true",
            )
        if shadow_enabled:
            return NewsGateRolloutDecision(
                requested_mode="LEGACY",
                effective_mode="SHADOW_ONLY",
                evaluate_gate=True,
                block_buy=False,
                record_shadow=True,
                reason="legacy NEWS_SHADOW_ENABLED=true",
            )
        return NewsGateRolloutDecision(
            requested_mode="LEGACY",
            effective_mode="POLL_ONLY" if poll_enabled else "OFF",
            evaluate_gate=False,
            block_buy=False,
            record_shadow=False,
            reason="legacy news gate/shadow disabled",
        )

    async def _resolve_explicit_mode(self, requested: str) -> NewsGateRolloutDecision:
        if requested == "OFF":
            return NewsGateRolloutDecision(
                requested_mode=requested,
                effective_mode="OFF",
                evaluate_gate=False,
                block_buy=False,
                record_shadow=False,
                reason="뉴스 gate rollout mode OFF",
            )
        if requested == "POLL_ONLY":
            return NewsGateRolloutDecision(
                requested_mode=requested,
                effective_mode="POLL_ONLY",
                evaluate_gate=False,
                block_buy=False,
                record_shadow=False,
                reason="뉴스 gate rollout mode POLL_ONLY",
            )
        if requested == "SHADOW_ONLY":
            return NewsGateRolloutDecision(
                requested_mode=requested,
                effective_mode="SHADOW_ONLY",
                evaluate_gate=True,
                block_buy=False,
                record_shadow=True,
                reason="뉴스 gate shadow-only",
            )

        rollout = await self._get_rollout_status()
        status = str((rollout or {}).get("status") or "UNKNOWN").upper()
        if status == "PROMOTE":
            return NewsGateRolloutDecision(
                requested_mode=requested,
                effective_mode="BUY_BLOCK_GATE",
                evaluate_gate=True,
                block_buy=True,
                record_shadow=True,
                reason="rollout 조건 충족: BUY_BLOCK_GATE 허용",
                detail={"rollout_status": rollout},
            )
        return NewsGateRolloutDecision(
            requested_mode=requested,
            effective_mode="SHADOW_ONLY",
            evaluate_gate=True,
            block_buy=False,
            record_shadow=True,
            reason=f"rollout 조건 미충족({status})으로 shadow-only 적용",
            detail={"rollout_status": rollout},
        )

    async def _get_rollout_status(self) -> dict:
        now = time.monotonic()
        if self._cached_rollout_status and now - self._cached_at < self.ROLLOUT_STATUS_TTL_SEC:
            return self._cached_rollout_status
        try:
            async with AsyncSessionLocal() as session:
                report = await performance_reporting_service.build_summary(session, days=30)
            rollout = dict(report.get("rollout") or {})
        except Exception as exc:
            logger.warning("뉴스 gate rollout 상태 조회 실패: {}", str(exc))
            rollout = {"status": "UNKNOWN", "reason": f"rollout 상태 조회 실패: {str(exc)[:80]}"}
        self._cached_rollout_status = rollout
        self._cached_at = now
        return rollout


news_gate_rollout_service = NewsGateRolloutService()
