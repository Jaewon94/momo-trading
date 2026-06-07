from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_


_FIXTURE_REASON_PATTERNS = (
    "%ORDER_SUBMISSION_MODE=READ_ONLY%",
    "%ORDER_SUBMISSION_MODE=SELL_ONLY%",
    "%ORD-PENDING%",
    "%주문 수량이 유효하지 않습니다%",
    "%주문 접수 응답%",
    "%매매불가 종목%",
)

_FIXTURE_METADATA_PATTERNS = (
    "%ORD-1%",
    "%ORD-PENDING%",
    "%analysis-123%",
    "%cycle-read-only%",
    "%cycle-sell-only%",
    "%cycle-zero%",
    "%cycle-pending-buy%",
    "%cycle-empty-order-id%",
    "%cycle-blocklist%",
    "%cycle-rec%",
)


def is_probable_fixture_cycle_id(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text.startswith("cycle-"):
        return False
    try:
        UUID(text)
    except ValueError:
        return True
    return False


def probable_fixture_decision_event_filter(model):
    """SQLAlchemy filter for synthetic unit-test decision events in runtime DB.

    Real cycle ids are UUID-like. The contaminated rows observed in production DB
    came from test cycle ids such as ``cycle-read-only`` and ``cycle-pending-buy``
    with UNKNOWN provider/model and fixture order ids.
    """
    reason_match = or_(*[
        model.reason.like(pattern)
        for pattern in _FIXTURE_REASON_PATTERNS
    ])
    metadata_match = or_(*[
        model.metadata_json.like(pattern)
        for pattern in _FIXTURE_METADATA_PATTERNS
    ])
    return and_(
        model.source == "decision_maker",
        model.provider == "UNKNOWN",
        model.model == "UNKNOWN",
        model.stock_name == model.symbol,
        model.cycle_id.like("cycle-%"),
        or_(
            reason_match,
            metadata_match,
            model.confidence == 0,
        ),
    )
