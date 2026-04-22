from datetime import datetime, timedelta
from types import SimpleNamespace

from services.order_reconciliation_service import OrderReconciliationService
from trading.models import PendingOrderInfo


def _broker_order(
    order_id: str,
    symbol: str,
    *,
    side: str = "매수",
    order_qty: int = 10,
    filled_qty: int = 0,
    remaining_qty: int | None = None,
) -> PendingOrderInfo:
    return PendingOrderInfo(
        order_id=order_id,
        symbol=symbol,
        name=f"{symbol} name",
        side=side,
        order_qty=order_qty,
        filled_qty=filled_qty,
        remaining_qty=order_qty - filled_qty if remaining_qty is None else remaining_qty,
        order_price=1000.0,
        order_time="091500",
    )


def _db_trade(
    trade_id: str,
    symbol: str,
    *,
    order_id: str | None,
    side: str = "BUY",
    quantity: int = 10,
    created_at: datetime | None = None,
):
    return SimpleNamespace(
        id=trade_id,
        order_id=order_id,
        stock_symbol=symbol,
        stock_name=f"{symbol} db",
        side=side,
        quantity=quantity,
        status="PENDING_CONFIRM",
        created_at=created_at or datetime(2026, 4, 22, 9, 0),
        entry_at=created_at or datetime(2026, 4, 22, 9, 0),
    )


def test_order_reconciliation_classifies_broker_and_db_pending_drift():
    service = OrderReconciliationService(stale_after=timedelta(minutes=30))
    report = service.build_report(
        broker_pending_orders=[
            _broker_order("B-ONLY", "005930", order_qty=3),
            _broker_order("MATCH", "000660", order_qty=10),
            _broker_order("QTY", "035420", order_qty=8),
            _broker_order("PARTIAL", "051910", order_qty=10, filled_qty=4, remaining_qty=6),
        ],
        db_pending_confirms=[
            _db_trade("db-match", "000660", order_id="MATCH", quantity=10),
            _db_trade("db-stale", "003280", order_id="DB-ONLY", quantity=7, created_at=datetime(2026, 4, 22, 8, 0)),
            _db_trade("db-qty", "035420", order_id="QTY", quantity=5),
            _db_trade("db-partial", "051910", order_id="PARTIAL", quantity=10),
        ],
        now=datetime(2026, 4, 22, 10, 0),
    )

    assert report["summary"] == {
        "broker_pending_count": 4,
        "db_pending_count": 4,
        "matched_count": 1,
        "broker_only_count": 1,
        "db_only_stale_count": 1,
        "quantity_mismatch_count": 1,
        "partial_fill_pending_count": 1,
    }
    assert report["broker_only"][0]["order_id"] == "B-ONLY"
    assert report["db_only_stale"][0]["trade_id"] == "db-stale"
    assert report["quantity_mismatch"][0]["order_id"] == "QTY"
    assert report["quantity_mismatch"][0]["broker_order_qty"] == 8
    assert report["quantity_mismatch"][0]["db_quantity"] == 5
    assert report["partial_fill_pending"][0]["order_id"] == "PARTIAL"
    assert report["partial_fill_pending"][0]["filled_qty"] == 4
    assert report["matched"][0]["order_id"] == "MATCH"
