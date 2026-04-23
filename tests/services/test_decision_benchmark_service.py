from datetime import datetime, timedelta

import pytest

from models.decision_event import DecisionEvent
from models.decision_forward_return import DecisionForwardReturn
from services.decision_benchmark_service import DecisionBenchmarkService
from tests.conftest import TestAsyncSessionLocal


async def _add_labeled_decision(
    *,
    symbol: str,
    final_action: str,
    return_pct: float,
    provider: str = "CODEX",
    stage: str = "ORDER_SUBMISSION",
    risk_gate: str = "PASS",
    created_at: datetime,
) -> None:
    async with TestAsyncSessionLocal() as session:
        event = DecisionEvent(
            cycle_id=f"cycle-{symbol}-{final_action}",
            symbol=symbol,
            stock_name=symbol,
            market="KRX",
            decision_stage=stage,
            source="decision_maker",
            risk_gate_result=risk_gate,
            final_action=final_action,
            reference_price=100_000,
            provider=provider,
            model="gpt-5.4",
            status="RECORDED",
            created_at=created_at,
        )
        session.add(event)
        await session.flush()
        session.add(
            DecisionForwardReturn(
                decision_event_id=event.id,
                symbol=symbol,
                horizon="close",
                target_at=created_at.replace(hour=15, minute=30),
                reference_price=100_000,
                target_price=100_000 * (1 + return_pct / 100),
                return_pct=return_pct,
                label_status="LABELED",
                price_source="market_data_daily.close",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_decision_benchmark_service_groups_labeled_returns() -> None:
    created_at = datetime.now() - timedelta(days=1)
    await _add_labeled_decision(
        symbol="005930",
        final_action="BUY",
        return_pct=2.0,
        provider="CODEX",
        created_at=created_at,
    )
    await _add_labeled_decision(
        symbol="000660",
        final_action="SKIP",
        return_pct=-1.0,
        provider="CODEX",
        risk_gate="BLOCKED",
        created_at=created_at,
    )
    await _add_labeled_decision(
        symbol="035420",
        final_action="BUY",
        return_pct=0.5,
        provider="OLLAMA",
        stage="RECOMMENDATION",
        risk_gate="PENDING_APPROVAL",
        created_at=created_at,
    )

    report = await DecisionBenchmarkService().build_report(
        TestAsyncSessionLocal,
        days=7,
        horizon="close",
        min_sample_size=2,
    )

    assert report["sample_status"] == "READY"
    assert report["overall"]["event_count"] == 3
    assert report["overall"]["avg_return_pct"] == 0.5
    assert report["overall"]["positive_rate"] == 0.6667
    assert report["by_final_action"]["BUY"]["event_count"] == 2
    assert report["by_final_action"]["BUY"]["avg_return_pct"] == 1.25
    assert report["by_final_action"]["SKIP"]["avg_return_pct"] == -1.0
    assert report["by_provider"]["CODEX"]["event_count"] == 2
    assert report["by_provider"]["OLLAMA"]["avg_return_pct"] == 0.5
    assert report["by_risk_gate"]["BLOCKED"]["avg_return_pct"] == -1.0
    assert report["controls"]["actual_buy"]["event_count"] == 2
    assert report["controls"]["non_buy_candidates"]["event_count"] == 1
    assert report["controls"]["blocked_or_skipped"]["event_count"] == 1


@pytest.mark.asyncio
async def test_decision_benchmark_service_reports_insufficient_samples() -> None:
    await _add_labeled_decision(
        symbol="005930",
        final_action="BUY",
        return_pct=1.0,
        created_at=datetime.now() - timedelta(days=1),
    )

    report = await DecisionBenchmarkService().build_report(
        TestAsyncSessionLocal,
        days=7,
        horizon="close",
        min_sample_size=3,
    )

    assert report["sample_status"] == "INSUFFICIENT_SAMPLE"
    assert report["minimum_sample_size"] == 3
    assert report["overall"]["event_count"] == 1
