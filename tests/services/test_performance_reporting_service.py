import json
import pytest
from types import SimpleNamespace

from models.trade_result import TradeResult
from services.performance_reporting_service import PerformanceReportingService, _ShadowPoint, _TradePoint


def test_calc_metrics_returns_expectancy_and_drawdown():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=100, return_pct=1.0, exit_at=__import__("datetime").datetime.now()),
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=-50, return_pct=-0.5, exit_at=__import__("datetime").datetime.now()),
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=200, return_pct=2.0, exit_at=__import__("datetime").datetime.now()),
    ]

    metrics = service._calc_metrics(trades)

    assert metrics["trade_count"] == 3
    assert metrics["win_rate"] == 0.6667
    assert metrics["expectancy"] > 0
    assert metrics["max_drawdown"] <= 0


def test_calc_metrics_does_not_report_infinite_pf_for_zero_pnl_sample():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=0, return_pct=0.0, exit_at=__import__("datetime").datetime.now()),
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=0, return_pct=0.0, exit_at=__import__("datetime").datetime.now()),
    ]

    metrics = service._calc_metrics(trades)

    assert metrics["trade_count"] == 2
    assert metrics["profit_factor"] == 0.0


def test_build_baseline_snapshot_returns_reset_notice():
    service = PerformanceReportingService()

    baseline = service._build_baseline_snapshot()

    assert baseline["active"] is True
    assert baseline["effective_date"] == "2026-04-06"
    assert "기준선 리셋" in baseline["label"]


@pytest.mark.asyncio
async def test_build_summary_includes_canonical_pnl_truth(monkeypatch):
    from tests.conftest import TestAsyncSessionLocal

    async def fake_pnl_truth_summary(_session):
        return {
            "sample_status": "INSUFFICIENT_CLOSED_TRADE_SAMPLE",
            "account_pnl_sample_status": "UNRECONCILED_ACCOUNT_PNL",
            "pnl_reconciliation_status": "UNEXPLAINED_ASSET_DELTA",
            "realized_trade_pnl": 0.0,
            "unrealized_broker_pnl": -2704805.0,
            "total_asset_delta": 7064565.0,
        }

    monkeypatch.setattr(
        "services.performance_reporting_service.pnl_truth_service.build_summary",
        fake_pnl_truth_summary,
    )
    monkeypatch.setattr(
        "services.performance_reporting_service.PerformanceReportingService._build_live_account_snapshot",
        lambda _self=None: __import__("asyncio").sleep(0, result={"synced": False}),
    )

    async with TestAsyncSessionLocal() as session:
        summary = await PerformanceReportingService().build_summary(session, days=1)

    assert summary["pnl_truth"] == {
        "sample_status": "INSUFFICIENT_CLOSED_TRADE_SAMPLE",
        "account_pnl_sample_status": "UNRECONCILED_ACCOUNT_PNL",
        "pnl_reconciliation_status": "UNEXPLAINED_ASSET_DELTA",
        "realized_trade_pnl": 0.0,
        "unrealized_broker_pnl": -2704805.0,
        "total_asset_delta": 7064565.0,
    }
    assert summary["metric_contract"] == {
        "overall_source": "trade_results.closed_buy",
        "account_pnl_source": "pnl_truth",
        "overall_deprecated_for_account_pnl": True,
        "sample_status": "UNRECONCILED_ACCOUNT_PNL",
        "closed_trade_sample_status": "INSUFFICIENT_CLOSED_TRADE_SAMPLE",
        "pnl_reconciliation_status": "UNEXPLAINED_ASSET_DELTA",
    }
    assert summary["data_quality"] == {
        "closed_trade_rows": 0,
        "excluded_reconciliation_close_rows": 0,
        "performance_trade_count": 0,
        "excluded_reconciliation_close_reason": (
            "broker holding missing neutral close rows are operational reconciliation, not realized trading performance"
        ),
    }


@pytest.mark.asyncio
async def test_fetch_closed_trades_excludes_holding_reconciliation_neutral_closes():
    from tests.conftest import TestAsyncSessionLocal

    now = __import__("datetime").datetime.now()
    async with TestAsyncSessionLocal() as session:
        session.add(TradeResult(
            stock_symbol="005930",
            stock_name="삼성전자",
            side="BUY",
            strategy_type="STABLE_SHORT",
            entry_price=70_000.0,
            exit_price=71_000.0,
            quantity=1,
            pnl=1_000.0,
            return_pct=1.4,
            is_win=True,
            hold_days=0,
            exit_reason="TAKE_PROFIT",
            ai_recommendation="BUY",
            ai_confidence=0.7,
            market="KRX",
            market_regime="NORMAL",
            status="CONFIRMED",
            entry_at=now,
            exit_at=now,
            notes='{"trade_horizon":"MID"}',
        ))
        session.add(TradeResult(
            stock_symbol="000660",
            stock_name="SK하이닉스",
            side="BUY",
            strategy_type="AGGRESSIVE_SHORT",
            entry_price=180_000.0,
            exit_price=180_000.0,
            quantity=1,
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="SYNC_CLOSE",
            ai_recommendation="BUY",
            ai_confidence=0.7,
            market="KRX",
            market_regime="NORMAL",
            status="CONFIRMED",
            entry_at=now,
            exit_at=now,
            notes="HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        ))
        session.add(TradeResult(
            stock_symbol="010140",
            stock_name="삼성중공업",
            side="BUY",
            strategy_type="AGGRESSIVE_SHORT",
            entry_price=33_800.0,
            exit_price=33_800.0,
            quantity=159,
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="BROKER_HOLDING_MISSING",
            ai_recommendation="BUY",
            ai_confidence=0.7,
            market="KRX",
            market_regime="NORMAL",
            status="CONFIRMED",
            entry_at=now,
            exit_at=now,
            notes=(
                "CLOSE_RECONCILIATION_SPLIT_REMAINING: sell_id=sell-1 | "
                "previous=HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"
            ),
        ))
        session.add(TradeResult(
            stock_symbol="452430",
            stock_name="사피엔반도체",
            side="BUY",
            strategy_type="STABLE_SHORT",
            entry_price=45_750.0,
            exit_price=50_900.0,
            quantity=283,
            pnl=1_457_450.0,
            return_pct=11.2568,
            is_win=True,
            hold_days=0,
            exit_reason="SELL_RECONCILIATION",
            ai_recommendation="BUY",
            ai_confidence=0.7,
            market="KRX",
            market_regime="NORMAL",
            status="CONFIRMED",
            entry_at=now,
            exit_at=now,
            notes=(
                "CLOSE_RECONCILIATION_APPLY: sell_id=sell-2 | "
                "previous=HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"
            ),
        ))
        await session.commit()

        service = PerformanceReportingService()
        trades = await service._fetch_closed_trades(
            session,
            from_dt=now - __import__("datetime").timedelta(minutes=1),
            to_dt=now + __import__("datetime").timedelta(minutes=1),
        )
        quality = await service._fetch_closed_trade_data_quality(
            session,
            from_dt=now - __import__("datetime").timedelta(minutes=1),
            to_dt=now + __import__("datetime").timedelta(minutes=1),
        )

    assert [trade.strategy_type for trade in trades] == ["STABLE_SHORT", "STABLE_SHORT"]
    assert quality["closed_trade_rows"] == 4
    assert quality["excluded_reconciliation_close_rows"] == 2
    assert quality["performance_trade_count"] == 2


def test_calc_metrics_includes_cost_adjusted_net_pnl():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(
            strategy_type="A",
            horizon="MID",
            pnl=1500,
            return_pct=1.5,
            exit_at=__import__("datetime").datetime.now(),
            entry_price=10_000,
            quantity=10,
            estimated_cost_bps=50,
        ),
        _TradePoint(
            strategy_type="A",
            horizon="MID",
            pnl=500,
            return_pct=0.5,
            exit_at=__import__("datetime").datetime.now(),
            entry_price=20_000,
            quantity=5,
            estimated_cost_bps=20,
        ),
    ]

    metrics = service._calc_metrics(trades)

    assert metrics["estimated_cost_total"] == 700.0
    assert metrics["net_pnl_after_cost"] == 1300.0


def test_extract_horizon_prefers_notes_json():
    service = PerformanceReportingService()
    trade = SimpleNamespace(
        notes=json.dumps({"trade_horizon": "LONG"}, ensure_ascii=False),
        strategy_type="AGGRESSIVE_SHORT",
    )
    assert service._extract_horizon(trade) == "LONG"


def test_extract_news_negative_pressure_from_notes_json():
    service = PerformanceReportingService()
    trade = SimpleNamespace(
        notes=json.dumps({"news_negative_pressure": 0.42}, ensure_ascii=False),
        strategy_type="STABLE_SHORT",
    )

    assert service._extract_news_negative_pressure(trade) == 0.42


def test_extract_news_negative_pressure_falls_back_to_news_context_json():
    service = PerformanceReportingService()
    trade = SimpleNamespace(
        notes=json.dumps({
            "news_context_available": True,
            "news_context_negative_pressure": 0.18,
            "news_context_item_count": 1,
        }, ensure_ascii=False),
        strategy_type="STABLE_SHORT",
    )

    assert service._extract_news_negative_pressure(trade) == 0.18
    assert service._extract_news_enriched(trade) is True


def test_calc_news_context_returns_average_pressure():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(strategy_type="A", horizon="SHORT", pnl=100, return_pct=1.0, exit_at=__import__("datetime").datetime.now(), news_negative_pressure=0.2),
        _TradePoint(strategy_type="A", horizon="MID", pnl=50, return_pct=0.5, exit_at=__import__("datetime").datetime.now(), news_negative_pressure=0.4),
    ]

    metrics = service._calc_news_context(trades)

    assert metrics["trade_count"] == 2
    assert metrics["avg_negative_pressure"] == 0.3


def test_calc_news_context_counts_enriched_trade_even_without_negative_pressure():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(
            strategy_type="A",
            horizon="MID",
            pnl=50,
            return_pct=0.5,
            exit_at=__import__("datetime").datetime.now(),
            news_negative_pressure=None,
            news_enriched=True,
        ),
    ]

    metrics = service._calc_news_context(trades)

    assert metrics["trade_count"] == 1
    assert metrics["avg_negative_pressure"] == 0.0


def test_calc_shadow_context_counts_news_policy_candidates():
    service = PerformanceReportingService()
    points = [
        _ShadowPoint(
            strategy_type="A",
            horizon="SHORT",
            actual_decision="BUY",
            baseline_decision="BUY",
            blocked_by_news=False,
            negative_pressure=0.22,
            threshold=0.75,
        ),
        _ShadowPoint(
            strategy_type="A",
            horizon="MID",
            actual_decision="BLOCK",
            baseline_decision="BUY",
            blocked_by_news=True,
            negative_pressure=0.88,
            threshold=0.75,
        ),
    ]

    summary = service._calc_shadow_context(points)

    assert summary["candidate_count"] == 2
    assert summary["actual_buy_count"] == 1
    assert summary["blocked_by_news_count"] == 1
    assert summary["baseline_buy_count"] == 2
    assert summary["buy_delta"] == -1
    assert summary["avg_negative_pressure"] == 0.55
    assert summary["block_rate"] == 0.5


def test_calc_trade_comparisons_splits_news_enriched_and_plain():
    service = PerformanceReportingService()
    trades = [
        _TradePoint(
            strategy_type="A",
            horizon="MID",
            pnl=1500,
            return_pct=1.5,
            exit_at=__import__("datetime").datetime.now(),
            news_negative_pressure=0.22,
            entry_price=10_000,
            quantity=10,
            estimated_cost_bps=20,
        ),
        _TradePoint(
            strategy_type="A",
            horizon="MID",
            pnl=-300,
            return_pct=-0.4,
            exit_at=__import__("datetime").datetime.now(),
            news_negative_pressure=0.35,
            entry_price=12_000,
            quantity=5,
            estimated_cost_bps=20,
        ),
        _TradePoint(
            strategy_type="B",
            horizon="SHORT",
            pnl=800,
            return_pct=0.9,
            exit_at=__import__("datetime").datetime.now(),
            news_negative_pressure=None,
            news_enriched=True,
            entry_price=20_000,
            quantity=3,
            estimated_cost_bps=10,
        ),
    ]

    comparison = service._calc_trade_comparisons(trades)

    assert comparison["news_enriched"]["trade_count"] == 3
    assert comparison["plain"]["trade_count"] == 0
    assert comparison["news_enriched"]["expectancy"] == 666.67
    assert comparison["plain"]["expectancy"] == 0.0
    assert comparison["delta"]["expectancy"] == 666.67


def test_build_rollout_status_promotes_when_samples_and_metrics_are_good():
    service = PerformanceReportingService()

    rollout = service._build_rollout_status(
        overall={
            "trade_count": 14,
            "expectancy": 1250.0,
            "profit_factor": 1.45,
            "max_drawdown": -850.0,
        },
        shadow={
            "candidate_count": 18,
            "blocked_by_news_count": 4,
            "actual_buy_count": 14,
        },
        sample_status="OK",
        min_sample_size=12,
        min_profit_factor=1.15,
        min_expectancy=0.0,
        max_drawdown_limit=-5000.0,
    )

    assert rollout["status"] == "PROMOTE"
    assert "확대" in rollout["reason"]
    assert len(rollout["checks"]) >= 4
    assert rollout["checks"][0]["key"] == "metric_quality"
    assert rollout["checks"][1]["key"] == "sample"
    assert any("Shadow 후보 18건" in line for line in rollout["details"])


def test_build_rollout_status_rolls_back_when_metrics_degrade():
    service = PerformanceReportingService()

    rollout = service._build_rollout_status(
        overall={
            "trade_count": 16,
            "expectancy": -120.0,
            "profit_factor": 0.82,
            "max_drawdown": -6200.0,
        },
        shadow={
            "candidate_count": 20,
            "blocked_by_news_count": 6,
            "actual_buy_count": 10,
        },
        sample_status="OK",
        min_sample_size=12,
        min_profit_factor=1.1,
        min_expectancy=0.0,
        max_drawdown_limit=-5000.0,
    )

    assert rollout["status"] == "ROLLBACK"
    assert "롤백" in rollout["reason"]
    assert any(check["key"] == "expectancy" and check["passed"] is False for check in rollout["checks"])
    assert any(check["key"] == "profit_factor" and check["passed"] is False for check in rollout["checks"])


def test_build_rollout_status_keeps_when_news_enriched_underperforms_plain():
    service = PerformanceReportingService()

    rollout = service._build_rollout_status(
        overall={
            "trade_count": 16,
            "expectancy": 1250.0,
            "profit_factor": 1.42,
            "max_drawdown": -2200.0,
        },
        shadow={
            "candidate_count": 20,
            "blocked_by_news_count": 5,
            "actual_buy_count": 14,
        },
        comparisons={
            "news_enriched": {"trade_count": 10, "expectancy": 900.0, "net_pnl_after_cost": 85000.0},
            "plain": {"trade_count": 6, "expectancy": 1400.0, "net_pnl_after_cost": 120000.0},
            "delta": {"expectancy": -500.0, "profit_factor": -0.2, "net_pnl_after_cost": -35000.0},
        },
        sample_status="OK",
        min_sample_size=12,
        min_profit_factor=1.1,
        min_expectancy=0.0,
        max_drawdown_limit=-5000.0,
    )

    assert rollout["status"] == "KEEP"
    assert "열위" in rollout["reason"]
    assert any(check["key"] == "comparison_expectancy" and check["passed"] is False for check in rollout["checks"])
    assert any(check["key"] == "comparison_net_pnl" and check["passed"] is False for check in rollout["checks"])


def test_build_rollout_status_holds_out_when_account_pnl_is_unreconciled():
    service = PerformanceReportingService()

    rollout = service._build_rollout_status(
        overall={
            "trade_count": 72,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
        },
        shadow={
            "candidate_count": 101,
            "blocked_by_news_count": 0,
            "actual_buy_count": 101,
            "baseline_buy_count": 101,
        },
        sample_status="UNRECONCILED_ACCOUNT_PNL",
        min_sample_size=12,
        min_profit_factor=1.1,
        min_expectancy=0.0,
        max_drawdown_limit=-5000.0,
    )

    assert rollout["status"] == "HOLDOUT"
    assert "성과 대사 대기" in rollout["reason"]
    assert rollout["checks"][0] == {
        "key": "metric_quality",
        "label": "성과 대사",
        "passed": False,
        "actual": "0원 표본",
        "target": "계좌 손익 대사 완료",
    }
