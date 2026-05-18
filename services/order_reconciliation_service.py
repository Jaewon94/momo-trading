"""Read-only broker/DB pending order reconciliation."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from trading.symbols import normalize_krx_symbol


class OrderReconciliationService:
    """Compare broker pending orders with DB PENDING_CONFIRM records."""

    def __init__(self, *, stale_after: timedelta = timedelta(minutes=30)) -> None:
        self.stale_after = stale_after

    def build_report(
        self,
        *,
        broker_pending_orders: list[Any],
        db_pending_confirms: list[Any],
        db_order_linked_trades: list[Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current_time = now or datetime.now()
        broker_by_order_id = {
            str(getattr(order, "order_id", "") or ""): order
            for order in broker_pending_orders
            if str(getattr(order, "order_id", "") or "")
        }
        db_by_order_id = {
            str(getattr(trade, "order_id", "") or ""): trade
            for trade in db_pending_confirms
            if str(getattr(trade, "order_id", "") or "")
        }
        linked_non_pending_by_order_id = {
            str(getattr(trade, "order_id", "") or ""): trade
            for trade in (db_order_linked_trades or [])
            if str(getattr(trade, "order_id", "") or "")
            and str(getattr(trade, "status", "") or "") != "PENDING_CONFIRM"
        }

        matched: list[dict[str, Any]] = []
        broker_only: list[dict[str, Any]] = []
        broker_linked_non_pending: list[dict[str, Any]] = []
        db_only_stale: list[dict[str, Any]] = []
        quantity_mismatch: list[dict[str, Any]] = []
        partial_fill_pending: list[dict[str, Any]] = []

        matched_order_ids = set(broker_by_order_id).intersection(db_by_order_id)
        for order_id in sorted(matched_order_ids):
            broker_order = broker_by_order_id[order_id]
            db_trade = db_by_order_id[order_id]
            broker_qty = int(getattr(broker_order, "order_qty", 0) or 0)
            db_qty = int(getattr(db_trade, "quantity", 0) or 0)
            filled_qty = int(getattr(broker_order, "filled_qty", 0) or 0)
            remaining_qty = int(getattr(broker_order, "remaining_qty", 0) or 0)

            if broker_qty != db_qty:
                quantity_mismatch.append({
                    **self._serialize_pair(order_id, broker_order, db_trade),
                    "broker_order_qty": broker_qty,
                    "db_quantity": db_qty,
                })
            elif filled_qty > 0 and remaining_qty > 0:
                partial_fill_pending.append({
                    **self._serialize_pair(order_id, broker_order, db_trade),
                    "filled_qty": filled_qty,
                    "remaining_qty": remaining_qty,
                })
            else:
                matched.append(self._serialize_pair(order_id, broker_order, db_trade))

        for order_id, broker_order in sorted(broker_by_order_id.items()):
            if order_id not in db_by_order_id:
                linked_trade = linked_non_pending_by_order_id.get(order_id)
                if linked_trade is not None:
                    broker_linked_non_pending.append({
                        **self._serialize_pair(order_id, broker_order, linked_trade),
                        "reason": "broker_pending_order_linked_to_non_pending_db_trade",
                        "db_status": str(getattr(linked_trade, "status", "") or ""),
                    })
                    continue
                broker_only.append(self._serialize_broker_order(broker_order))

        for order_id, db_trade in sorted(db_by_order_id.items()):
            if order_id not in broker_by_order_id and self._is_stale(db_trade, current_time):
                db_only_stale.append(self._serialize_db_trade(db_trade))

        return {
            "summary": {
                "broker_pending_count": len(broker_pending_orders),
                "db_pending_count": len(db_pending_confirms),
                "matched_count": len(matched),
                "broker_only_count": len(broker_only),
                "broker_linked_non_pending_count": len(broker_linked_non_pending),
                "db_only_stale_count": len(db_only_stale),
                "quantity_mismatch_count": len(quantity_mismatch),
                "partial_fill_pending_count": len(partial_fill_pending),
            },
            "matched": matched,
            "broker_only": broker_only,
            "broker_linked_non_pending": broker_linked_non_pending,
            "db_only_stale": db_only_stale,
            "quantity_mismatch": quantity_mismatch,
            "partial_fill_pending": partial_fill_pending,
            "mode": "read_only",
        }

    def _is_stale(self, trade: Any, now: datetime) -> bool:
        created_at = getattr(trade, "created_at", None) or getattr(trade, "entry_at", None)
        if not isinstance(created_at, datetime):
            return True
        comparable_now = now
        if created_at.tzinfo is not None and comparable_now.tzinfo is None:
            comparable_now = comparable_now.replace(tzinfo=created_at.tzinfo)
        if created_at.tzinfo is None and comparable_now.tzinfo is not None:
            comparable_now = comparable_now.replace(tzinfo=None)
        return comparable_now - created_at >= self.stale_after

    def _serialize_pair(self, order_id: str, broker_order: Any, db_trade: Any) -> dict[str, Any]:
        return {
            "order_id": order_id,
            "symbol": normalize_krx_symbol(getattr(broker_order, "symbol", "") or getattr(db_trade, "stock_symbol", "")),
            "broker": self._serialize_broker_order(broker_order),
            "db": self._serialize_db_trade(db_trade),
        }

    def _serialize_broker_order(self, order: Any) -> dict[str, Any]:
        return {
            "order_id": str(getattr(order, "order_id", "") or ""),
            "symbol": normalize_krx_symbol(getattr(order, "symbol", "") or ""),
            "name": str(getattr(order, "name", "") or ""),
            "side": str(getattr(order, "side", "") or ""),
            "order_qty": int(getattr(order, "order_qty", 0) or 0),
            "filled_qty": int(getattr(order, "filled_qty", 0) or 0),
            "remaining_qty": int(getattr(order, "remaining_qty", 0) or 0),
            "order_price": float(getattr(order, "order_price", 0.0) or 0.0),
            "order_time": str(getattr(order, "order_time", "") or ""),
        }

    def _serialize_db_trade(self, trade: Any) -> dict[str, Any]:
        return {
            "trade_id": str(getattr(trade, "id", "") or ""),
            "order_id": str(getattr(trade, "order_id", "") or ""),
            "symbol": normalize_krx_symbol(getattr(trade, "stock_symbol", "") or ""),
            "name": str(getattr(trade, "stock_name", "") or ""),
            "side": str(getattr(trade, "side", "") or ""),
            "quantity": int(getattr(trade, "quantity", 0) or 0),
            "status": str(getattr(trade, "status", "") or ""),
            "created_at": self._iso_or_none(getattr(trade, "created_at", None)),
            "entry_at": self._iso_or_none(getattr(trade, "entry_at", None)),
        }

    def _iso_or_none(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return None


order_reconciliation_service = OrderReconciliationService()
