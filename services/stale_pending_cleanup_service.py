"""Manual stale PENDING_CONFIRM cleanup built on reconciliation evidence."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.trade_result_repository import TradeResultRepository
from services.order_reconciliation_service import OrderReconciliationService
from trading.enums import OrderConfirmStatus


class StalePendingCleanupService:
    """Mark stale DB-only BUY pending confirms as failed, with dry-run by default."""

    def __init__(self, *, stale_after: timedelta = timedelta(minutes=30)) -> None:
        self._reconciliation = OrderReconciliationService(stale_after=stale_after)

    async def cleanup(
        self,
        db: AsyncSession,
        *,
        broker_pending_orders: list[Any],
        db_pending_confirms: list[Any] | None = None,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        pending_confirms = db_pending_confirms
        if pending_confirms is None:
            pending_confirms = await TradeResultRepository(db).get_pending_confirms()

        report = self._reconciliation.build_report(
            broker_pending_orders=broker_pending_orders,
            db_pending_confirms=pending_confirms,
            now=now,
        )
        stale_by_id = {
            str(item.get("trade_id") or ""): item
            for item in report["db_only_stale"]
            if str(item.get("trade_id") or "")
        }

        candidates: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        updated_count = 0

        for trade in pending_confirms:
            trade_id = str(getattr(trade, "id", "") or "")
            if trade_id not in stale_by_id:
                continue
            item = stale_by_id[trade_id]
            side = str(getattr(trade, "side", "") or "").upper()
            if side != "BUY":
                skipped.append({**item, "reason": "non_buy_pending_requires_holdings_reconciliation"})
                continue

            candidates.append(item)
            if dry_run:
                continue

            current_status = str(getattr(trade, "status", "") or "").upper()
            if current_status != OrderConfirmStatus.PENDING_CONFIRM.value:
                skipped.append({**item, "reason": "status_changed"})
                continue

            trade.status = OrderConfirmStatus.CONFIRM_FAILED.value
            trade.notes = self._build_failure_note(getattr(trade, "notes", None))
            updated_count += 1

        return {
            "mode": "dry_run" if dry_run else "apply",
            "summary": {
                "broker_pending_count": report["summary"]["broker_pending_count"],
                "db_pending_count": report["summary"]["db_pending_count"],
                "eligible_count": len(candidates),
                "updated_count": updated_count,
                "skipped_count": len(skipped),
            },
            "candidates": candidates,
            "skipped": skipped,
            "reconciliation": report,
        }

    def _build_failure_note(self, previous_note: Any) -> str:
        prefix = "CONFIRM_FAILED: stale pending reconciliation cleanup"
        previous = str(previous_note or "").strip()
        if not previous:
            return prefix
        if prefix in previous:
            return previous
        return f"{prefix} | previous={previous[:160]}"


stale_pending_cleanup_service = StalePendingCleanupService()
