"""Metrics for deterministic AI call avoidance."""
from __future__ import annotations

from typing import Any

from services.observability_service import observability_service


class AiSkipMetricService:
    async def record(
        self,
        *,
        stage: str,
        reason_code: str,
        skipped_tier: str,
        cycle_id: str | None = None,
        symbol: str | None = None,
        detail: dict[str, Any] | None = None,
    ):
        merged_detail = {
            "stage": str(stage or "").upper(),
            "reason_code": str(reason_code or "").upper(),
            "skipped_tier": str(skipped_tier or "").upper(),
        }
        if detail:
            merged_detail.update(detail)
        return await observability_service.record_execution_metric(
            metric_type="AI_SKIPPED",
            metric_name=merged_detail["stage"],
            status="SKIPPED",
            cycle_id=cycle_id,
            symbol=symbol,
            item_count=1,
            success_count=1,
            error_count=0,
            detail=merged_detail,
        )


ai_skip_metric_service = AiSkipMetricService()
