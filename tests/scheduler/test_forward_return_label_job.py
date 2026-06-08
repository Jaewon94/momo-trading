from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from models.decision_event import DecisionEvent
from models.decision_forward_return import DecisionForwardReturn
from models.market_data import MarketDataDaily, MarketSnapshot
from models.stock import Stock
from scheduler.jobs.forward_return_label_job import ForwardReturnLabelJob
from tests.conftest import TestAsyncSessionLocal


@pytest.mark.asyncio
async def test_forward_return_label_job_labels_intraday_snapshot_return() -> None:
    event_at = datetime(2026, 4, 23, 9, 5)
    target_at = event_at + timedelta(minutes=5)

    async with TestAsyncSessionLocal() as session:
        stock = Stock(symbol="005930", name="삼성전자", market="KOSPI", is_active=True)
        session.add(stock)
        await session.flush()
        session.add(
            DecisionEvent(
                cycle_id="cycle-1",
                symbol="005930",
                stock_name="삼성전자",
                market="KRX",
                decision_stage="ORDER_GATE",
                source="decision_maker",
                final_action="BUY",
                reference_price=100_000,
                provider="CODEX",
                model="gpt-5.4",
                status="RECORDED",
                created_at=event_at,
            )
        )
        session.add(
            MarketSnapshot(
                stock_id=stock.id,
                current_price=101_500,
                updated_at=target_at + timedelta(seconds=3),
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={"5m": timedelta(minutes=5)},
    ).run_once(now=target_at + timedelta(seconds=5))

    async with TestAsyncSessionLocal() as session:
        labels = (await session.execute(select(DecisionForwardReturn))).scalars().all()

    assert summary["labeled"] == 1
    assert summary["waiting_data"] == 0
    assert len(labels) == 1
    assert labels[0].horizon == "5m"
    assert labels[0].label_status == "LABELED"
    assert labels[0].target_at == target_at
    assert labels[0].target_price == 101_500
    assert labels[0].return_pct == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_forward_return_label_job_waits_when_price_data_is_missing() -> None:
    event_at = datetime(2026, 4, 23, 9, 5)
    target_at = event_at + timedelta(minutes=5)

    async with TestAsyncSessionLocal() as session:
        session.add(
            DecisionEvent(
                cycle_id="cycle-1",
                symbol="005930",
                stock_name="삼성전자",
                market="KRX",
                decision_stage="ORDER_GATE",
                source="decision_maker",
                final_action="SKIP",
                reference_price=100_000,
                provider="UNKNOWN",
                model="UNKNOWN",
                status="RECORDED",
                created_at=event_at,
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={"5m": timedelta(minutes=5)},
    ).run_once(now=target_at + timedelta(minutes=1))

    async with TestAsyncSessionLocal() as session:
        labels = (await session.execute(select(DecisionForwardReturn))).scalars().all()

    assert summary["labeled"] == 0
    assert summary["waiting_data"] == 1
    assert len(labels) == 1
    assert labels[0].horizon == "5m"
    assert labels[0].label_status == "WAITING_DATA"
    assert labels[0].target_price is None
    assert labels[0].return_pct is None


@pytest.mark.asyncio
async def test_forward_return_label_job_skips_probable_fixture_decision_event() -> None:
    event_at = datetime(2026, 4, 23, 9, 5)
    target_at = event_at + timedelta(minutes=5)

    async with TestAsyncSessionLocal() as session:
        session.add(
            DecisionEvent(
                cycle_id="cycle-read-only",
                symbol="005930",
                stock_name="005930",
                market="KRX",
                decision_stage="ORDER_GATE",
                source="decision_maker",
                final_action="SKIP",
                confidence=0.0,
                reference_price=100_000,
                quantity=2,
                provider="UNKNOWN",
                model="UNKNOWN",
                status="SKIPPED",
                reason="주문 제출 차단: ORDER_SUBMISSION_MODE=READ_ONLY",
                created_at=event_at,
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={"5m": timedelta(minutes=5)},
    ).run_once(now=target_at + timedelta(minutes=1))

    async with TestAsyncSessionLocal() as session:
        labels = (await session.execute(select(DecisionForwardReturn))).scalars().all()

    assert summary["events_scanned"] == 0
    assert labels == []


@pytest.mark.asyncio
async def test_forward_return_label_job_labels_close_return_from_daily_data() -> None:
    event_at = datetime(2026, 4, 23, 13, 0)
    close_at = datetime(2026, 4, 23, 15, 30)

    async with TestAsyncSessionLocal() as session:
        stock = Stock(symbol="005930", name="삼성전자", market="KOSPI", is_active=True)
        session.add(stock)
        await session.flush()
        session.add(
            DecisionEvent(
                cycle_id="cycle-1",
                symbol="005930",
                stock_name="삼성전자",
                market="KRX",
                decision_stage="RECOMMENDATION",
                source="decision_maker",
                final_action="HOLD",
                reference_price=100_000,
                provider="CODEX",
                model="gpt-5.4",
                status="RECORDED",
                created_at=event_at,
            )
        )
        session.add(
            MarketDataDaily(
                stock_id=stock.id,
                trade_date=event_at.date(),
                open=99_000,
                high=104_000,
                low=98_000,
                close=103_000,
                volume=1_000_000,
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={},
        include_close=True,
    ).run_once(now=close_at + timedelta(minutes=15))

    async with TestAsyncSessionLocal() as session:
        label = (await session.execute(select(DecisionForwardReturn))).scalar_one()

    assert summary["labeled"] == 1
    assert label.horizon == "close"
    assert label.label_status == "LABELED"
    assert label.target_at == close_at
    assert label.target_price == 103_000
    assert label.return_pct == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_forward_return_label_job_prioritizes_recent_due_events() -> None:
    old_event_at = datetime(2026, 4, 20, 9, 5)
    recent_event_at = datetime(2026, 4, 23, 9, 5)
    recent_target_at = recent_event_at + timedelta(minutes=5)

    async with TestAsyncSessionLocal() as session:
        stock = Stock(symbol="005930", name="삼성전자", market="KOSPI", is_active=True)
        session.add(stock)
        await session.flush()
        session.add(
            DecisionEvent(
                cycle_id="cycle-old",
                symbol="000001",
                stock_name="오래된누락",
                market="KRX",
                decision_stage="ORDER_GATE",
                source="decision_maker",
                final_action="BUY",
                reference_price=10_000,
                provider="CODEX",
                model="gpt-5.4",
                status="RECORDED",
                created_at=old_event_at,
            )
        )
        session.add(
            DecisionEvent(
                cycle_id="cycle-recent",
                symbol="005930",
                stock_name="삼성전자",
                market="KRX",
                decision_stage="ORDER_GATE",
                source="decision_maker",
                final_action="BUY",
                reference_price=100_000,
                provider="CODEX",
                model="gpt-5.4",
                status="RECORDED",
                created_at=recent_event_at,
            )
        )
        session.add(
            MarketSnapshot(
                stock_id=stock.id,
                current_price=102_000,
                updated_at=recent_target_at + timedelta(seconds=3),
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={"5m": timedelta(minutes=5)},
        include_close=False,
    ).run_once(now=recent_target_at + timedelta(minutes=1), limit=1)

    async with TestAsyncSessionLocal() as session:
        labels = (await session.execute(select(DecisionForwardReturn))).scalars().all()

    assert summary["events_scanned"] == 1
    assert summary["labeled"] == 1
    assert len(labels) == 1
    assert labels[0].symbol == "005930"
    assert labels[0].label_status == "LABELED"


@pytest.mark.asyncio
async def test_forward_return_label_job_labels_close_return_from_snapshot_when_daily_missing() -> None:
    event_at = datetime(2026, 4, 23, 13, 0)
    close_at = datetime(2026, 4, 23, 15, 30)

    async with TestAsyncSessionLocal() as session:
        stock = Stock(symbol="005930", name="삼성전자", market="KOSPI", is_active=True)
        session.add(stock)
        await session.flush()
        session.add(
            DecisionEvent(
                cycle_id="cycle-1",
                symbol="005930",
                stock_name="삼성전자",
                market="KRX",
                decision_stage="RECOMMENDATION",
                source="decision_maker",
                final_action="HOLD",
                reference_price=100_000,
                provider="CODEX",
                model="gpt-5.4",
                status="RECORDED",
                created_at=event_at,
            )
        )
        session.add(
            MarketSnapshot(
                stock_id=stock.id,
                current_price=101_000,
                updated_at=close_at + timedelta(minutes=1),
            )
        )
        await session.commit()

    summary = await ForwardReturnLabelJob(
        session_factory=TestAsyncSessionLocal,
        intraday_horizons={},
        include_close=True,
    ).run_once(now=close_at + timedelta(minutes=15))

    async with TestAsyncSessionLocal() as session:
        label = (await session.execute(select(DecisionForwardReturn))).scalar_one()

    assert summary["labeled"] == 1
    assert label.horizon == "close"
    assert label.label_status == "LABELED"
    assert label.target_price == 101_000
    assert label.price_source == "market_snapshot.current_price_after_close"
