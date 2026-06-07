from datetime import datetime, timedelta
import json

import pytest

from models.decision_event import DecisionEvent
from models.decision_forward_return import DecisionForwardReturn
from models.execution_metric import ExecutionMetric
from services.decision_benchmark_service import DecisionBenchmarkService
from tests.conftest import TestAsyncSessionLocal


def test_decision_benchmark_extracts_news_context_source_codes() -> None:
    metadata = {
        "analysis_context": {
            "news_context_source_codes": ["DART"],
            "news_context_items": [
                {"source_code": "KRX", "title": "공시"},
                {"source_code": "DART", "title": "중복 공시"},
            ],
            "news_top_contributors": [
                {"source_code": "BLOOMBERG", "headline": "해외 뉴스"},
            ],
        }
    }

    codes = DecisionBenchmarkService._extract_news_source_codes(
        json.dumps(metadata, ensure_ascii=False)
    )

    assert codes == ("DART", "BLOOMBERG", "KRX")


async def _add_labeled_decision(
    *,
    symbol: str,
    final_action: str,
    return_pct: float,
    provider: str = "CODEX",
    stage: str = "ORDER_SUBMISSION",
    risk_gate: str = "PASS",
    event_source: str = "decision_maker",
    scanner_score: float | None = None,
    strategy_type: str | None = None,
    tier1_decision: str | None = None,
    tier2_decision: str | None = None,
    metadata: dict | None = None,
    created_at: datetime,
    cycle_id: str | None = None,
) -> None:
    async with TestAsyncSessionLocal() as session:
        event = DecisionEvent(
            cycle_id=cycle_id or f"cycle-{symbol}-{final_action}",
            symbol=symbol,
            stock_name=symbol,
            market="KRX",
            decision_stage=stage,
            source=event_source,
            strategy_type=strategy_type,
            scanner_score=scanner_score,
            tier1_decision=tier1_decision,
            tier2_decision=tier2_decision,
            risk_gate_result=risk_gate,
            final_action=final_action,
            reference_price=100_000,
            provider=provider,
            model="gpt-5.4",
            status="RECORDED",
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
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
async def test_decision_benchmark_excludes_probable_fixture_decision_events() -> None:
    created_at = datetime.now() - timedelta(days=1)
    async with TestAsyncSessionLocal() as session:
        real = DecisionEvent(
            cycle_id="7f868aeb-1b76-4384-846b-21f08f8b39cb",
            symbol="005930",
            stock_name="삼성전자",
            market="KRX",
            decision_stage="ORDER_SUBMISSION",
            source="decision_maker",
            final_action="BUY",
            reference_price=100_000,
            provider="CODEX",
            model="gpt-5.4",
            status="ORDER_SUBMITTED",
            created_at=created_at,
        )
        fixture = DecisionEvent(
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
            metadata_json=json.dumps({"order_result": {"order_id": "ORD-1"}}, ensure_ascii=False),
            created_at=created_at,
        )
        session.add_all([real, fixture])
        await session.flush()
        session.add_all([
            DecisionForwardReturn(
                decision_event_id=real.id,
                symbol="005930",
                horizon="close",
                target_at=created_at.replace(hour=15, minute=30),
                reference_price=100_000,
                target_price=102_000,
                return_pct=2.0,
                label_status="LABELED",
                price_source="market_data_daily.close",
            ),
            DecisionForwardReturn(
                decision_event_id=fixture.id,
                symbol="005930",
                horizon="close",
                target_at=created_at.replace(hour=15, minute=30),
                reference_price=100_000,
                target_price=90_000,
                return_pct=-10.0,
                label_status="LABELED",
                price_source="market_data_daily.close",
            ),
        ])
        await session.commit()

    report = await DecisionBenchmarkService().build_report(
        TestAsyncSessionLocal,
        days=7,
        horizon="close",
        min_sample_size=1,
    )

    assert report["overall"]["event_count"] == 1
    assert report["overall"]["avg_return_pct"] == 2.0


@pytest.mark.asyncio
async def test_decision_benchmark_service_groups_labeled_returns() -> None:
    created_at = datetime.now() - timedelta(days=1)
    await _add_labeled_decision(
        symbol="005930",
        final_action="BUY",
        return_pct=2.0,
        provider="CODEX",
        scanner_score=0.91,
        strategy_type="STABLE_SHORT",
        tier1_decision="BUY",
        tier2_decision="BUY",
        cycle_id="cycle-buy-005930",
        metadata={
            "signal_metadata": {
                "alpha_source": "LLM_DECISION_PIPELINE",
                "execution_profile": "STABLE_SHORT",
                "risk_profile": "STABLE",
                "news_top_contributors": [
                    {"source_code": "DART", "headline": "공시", "pressure": 0.4},
                    {"source_code": "YONHAP", "headline": "연합뉴스", "pressure": 0.2},
                ]
            }
        },
        created_at=created_at,
    )
    await _add_labeled_decision(
        symbol="005930",
        final_action="CANDIDATE",
        return_pct=1.8,
        provider="DETERMINISTIC",
        stage="CANDIDATE_SCORING",
        risk_gate="PASS",
        event_source="candidate_scoring",
        scanner_score=0.5,
        strategy_type="STABLE_SHORT",
        created_at=created_at,
        cycle_id="cycle-buy-005930",
    )
    await _add_labeled_decision(
        symbol="123456",
        final_action="CANDIDATE",
        return_pct=-0.5,
        provider="DETERMINISTIC",
        stage="CANDIDATE_SCORING",
        risk_gate="PASS",
        event_source="candidate_scoring",
        scanner_score=0.4,
        strategy_type="STABLE_SHORT",
        created_at=created_at,
        cycle_id="cycle-scanner-only",
    )
    await _add_labeled_decision(
        symbol="000660",
        final_action="SKIP",
        return_pct=-1.0,
        provider="CODEX",
        risk_gate="BLOCKED",
        event_source="risk_gate",
        scanner_score=0.84,
        strategy_type="AGGRESSIVE_SHORT",
        tier1_decision="BUY",
        metadata={
            "signal_metadata": {
                "news_top_contributors": [
                    {"source_code": "DART", "headline": "리스크 공시", "pressure": 0.6},
                ]
            }
        },
        created_at=created_at,
    )
    await _add_labeled_decision(
        symbol="035420",
        final_action="BUY",
        return_pct=0.5,
        provider="OLLAMA",
        stage="RECOMMENDATION",
        risk_gate="PENDING_APPROVAL",
        scanner_score=0.72,
        tier1_decision="BUY",
        tier2_decision="HOLD",
        metadata={
            "analysis_context": {
                "news_top_contributors": [
                    {"source_code": "BLOOMBERG", "headline": "반도체 수요", "pressure": 0.1},
                ]
            }
        },
        created_at=created_at,
    )
    async with TestAsyncSessionLocal() as session:
        session.add_all([
            ExecutionMetric(
                metric_type="AI_SKIPPED",
                metric_name="HOLDINGS_PRECHECK",
                status="SKIPPED",
                symbol="005930",
                item_count=1,
                success_count=1,
                error_count=0,
                detail=json.dumps({
                    "stage": "HOLDINGS_PRECHECK",
                    "reason_code": "HOLD",
                    "skipped_tier": "TIER1",
                    "reason": "명확한 HOLD 사전판단",
                }, ensure_ascii=False),
                created_at=created_at,
            ),
            ExecutionMetric(
                metric_type="AI_SKIPPED",
                metric_name="HOLDINGS_PRECHECK",
                status="SKIPPED",
                symbol="005930",
                item_count=1,
                success_count=1,
                error_count=0,
                detail=json.dumps({
                    "stage": "HOLDINGS_PRECHECK",
                    "reason_code": "SELL",
                    "skipped_tier": "TIER1",
                    "reason": "손실 과대",
                }, ensure_ascii=False),
                created_at=created_at,
            ),
        ])
        await session.commit()

    report = await DecisionBenchmarkService().build_report(
        TestAsyncSessionLocal,
        days=7,
        horizon="close",
        min_sample_size=2,
    )

    assert report["sample_status"] == "READY"
    assert report["overall"]["event_count"] == 5
    assert report["overall"]["avg_return_pct"] == 0.56
    assert report["overall"]["positive_rate"] == 0.6
    assert report["by_final_action"]["BUY"]["event_count"] == 2
    assert report["by_final_action"]["BUY"]["avg_return_pct"] == 1.25
    assert report["by_final_action"]["SKIP"]["avg_return_pct"] == -1.0
    assert report["by_provider"]["CODEX"]["event_count"] == 2
    assert report["by_provider"]["DETERMINISTIC"]["event_count"] == 2
    assert report["by_provider"]["OLLAMA"]["avg_return_pct"] == 0.5
    assert report["by_risk_gate"]["BLOCKED"]["avg_return_pct"] == -1.0
    assert report["by_event_source"]["DECISION_MAKER"]["event_count"] == 2
    assert report["by_event_source"]["RISK_GATE"]["event_count"] == 1
    assert report["by_strategy_type"]["STABLE_SHORT"]["avg_return_pct"] == 1.1
    assert report["by_alpha_source"]["LLM_DECISION_PIPELINE"]["event_count"] == 1
    assert report["by_execution_profile"]["STABLE_SHORT"]["event_count"] == 3
    assert report["by_risk_profile"]["STABLE"]["event_count"] == 1
    assert report["by_tier1_decision"]["BUY"]["event_count"] == 3
    assert report["by_tier2_decision"]["BUY"]["event_count"] == 1
    assert report["by_tier2_decision"]["HOLD"]["event_count"] == 1
    assert report["by_news_source_attribution"]["DART"]["event_count"] == 2
    assert report["by_news_source_attribution"]["BLOOMBERG"]["avg_return_pct"] == 0.5
    assert report["by_news_source_blocked"]["DART"]["event_count"] == 1
    assert report["by_news_source_blocked"]["DART"]["avg_return_pct"] == -1.0
    assert report["by_news_source_blocked_comparison"]["DART"]["blocked"]["event_count"] == 1
    assert report["by_news_source_blocked_comparison"]["DART"]["actual_buy"]["event_count"] == 1
    assert report["by_news_source_blocked_comparison"]["DART"]["delta_avg_return_pct"] == -3.0
    assert report["controls"]["actual_buy"]["event_count"] == 2
    assert report["controls"]["non_buy_candidates"]["event_count"] == 3
    assert report["controls"]["blocked_or_skipped"]["event_count"] == 1
    assert report["controls"]["random_same_count"]["event_count"] == 2
    assert report["controls"]["scanner_top_same_count"]["event_count"] == 2
    assert report["controls"]["scanner_top_same_count"]["avg_return_pct"] == 0.5
    assert report["controls"]["tier1_buy_only"]["event_count"] == 3
    assert report["controls"]["tier2_buy_only"]["event_count"] == 1
    assert report["candidate_path_comparison"]["scanner_candidates"]["event_count"] == 2
    assert report["candidate_path_comparison"]["scanner_candidates"]["avg_return_pct"] == 0.65
    assert report["candidate_path_comparison"]["scanner_only"]["event_count"] == 1
    assert report["candidate_path_comparison"]["scanner_only"]["avg_return_pct"] == -0.5
    assert report["candidate_path_comparison"]["scanner_only"]["delta_vs_actual_buy_avg_return_pct"] == -1.75
    assert report["candidate_path_comparison"]["tier1_reached"]["event_count"] == 3
    assert report["candidate_path_comparison"]["tier1_buy_only"]["event_count"] == 1
    assert report["candidate_path_comparison"]["tier2_buy"]["avg_return_pct"] == 2.0
    assert report["candidate_path_comparison"]["actual_buy"]["avg_return_pct"] == 1.25
    assert report["candidate_path_comparison"]["random_same_count_as_scanner"]["event_count"] == 2
    assert "cycle_id+symbol" in report["candidate_path_comparison"]["note"]
    assert report["ai_skipped_observation"]["total_skipped"] == 2
    assert {
        "stage": "HOLDINGS_PRECHECK",
        "reason_code": "HOLD",
        "skipped_tier": "TIER1",
        "count": 1,
    } in report["ai_skipped_observation"]["by_stage_reason"]
    assert report["ai_skipped_observation"]["top_symbols"] == [{"symbol": "005930", "count": 2}]
    assert "forward return" in report["ai_skipped_observation"]["note"]


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
