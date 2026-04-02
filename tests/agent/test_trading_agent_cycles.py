from datetime import datetime
from types import SimpleNamespace

import pytest

from agent.trading_agent import TradingAgent
from core.events import Event, EventType


class StubBrokerAdapter:
    pass


def _kst_time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 2, hour, minute, 0)


@pytest.mark.asyncio
async def test_run_cycle_skips_when_cycle_lock_is_held() -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    await agent._cycle_lock.acquire()

    try:
        result = await agent.run_cycle()
    finally:
        agent._cycle_lock.release()

    assert result == {"skipped": True, "reason": "cycle_already_running"}


@pytest.mark.asyncio
async def test_run_cycle_skips_new_buys_after_cutoff_in_day_trading_mode(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    activity_logs: list[tuple] = []

    async def fake_log(*args, **kwargs) -> None:
        activity_logs.append((args, kwargs))

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("agent.trading_agent.settings.BUY_CUTOFF_HOUR", 14)
    monkeypatch.setattr("agent.trading_agent.settings.BUY_CUTOFF_MINUTE", 30)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(14, 30))

    result = await agent.run_cycle()

    assert result == {"skipped": True, "reason": "buy_cutoff"}
    assert agent.last_cycle_time == _kst_time(14, 30)
    assert len(activity_logs) == 1


@pytest.mark.asyncio
async def test_run_cycle_dispatches_trading_cycle_during_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        return {"mode": "trading"}

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None) -> dict:
        raise AssertionError("after-hours cycle should not be called during market hours")

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CODEX")

    assert result == {"mode": "trading"}
    assert observed == {"manual_provider_override": "CODEX"}


@pytest.mark.asyncio
async def test_run_cycle_dispatches_after_hours_cycle_outside_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None) -> dict:
        raise AssertionError("trading cycle should not be called outside market hours")

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        return {"mode": "after-hours"}

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CLAUDE_CODE")

    assert result == {"mode": "after-hours"}
    assert observed == {"manual_provider_override": "CLAUDE_CODE"}


@pytest.mark.asyncio
async def test_run_trading_cycle_returns_zeroed_results_when_snapshot_runtime_error(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        raise RuntimeError("계좌 조회 실패")

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-1")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 5))

    result = await agent._run_trading_cycle()

    assert result == {"scanned": 0, "analyzed": 0, "signals": 0, "executed": 0, "selected_symbols": []}
    assert agent.last_cycle_time == _kst_time(9, 5)
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START]
    assert any("계좌 조회 실패" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_completes_cleanly_when_scan_selects_no_candidates(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {"selected": []}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-2")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 12)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 6))

    result = await agent._run_trading_cycle()

    assert result == {"scanned": 0, "analyzed": 0, "signals": 0, "executed": 0, "selected_symbols": []}
    assert agent.last_cycle_time == _kst_time(9, 6)
    assert agent._daily_start_balance == 2_000_000
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START]
    assert any("선정 종목 없음" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_caches_scan_metadata_before_analysis(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []
    applied_thresholds = []
    analyzed_payloads = []
    resume_calls = []

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "BULLISH",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str) -> dict:
        return {"success": True, "max_qty": 10}

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs) -> dict:
        analyzed_payloads.append(
            {
                "stock_info": dict(stock_info),
                "cycle_id": cycle_id,
                "manual_provider_override": kwargs.get("manual_provider_override"),
                "portfolio_snapshot": kwargs.get("portfolio_snapshot"),
            }
        )
        return {"signal": True, "executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: "session-1")
    monkeypatch.setattr("agent.trading_agent.llm_factory.resume_session", lambda sid: resume_calls.append(sid))
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "ended-session")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-3")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 50)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda candidates: applied_thresholds.extend(dict(c) for c in candidates))
    monkeypatch.setattr("trading.kis_api.get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 7))

    result = await agent._run_trading_cycle(manual_provider_override="CODEX")

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 1
    assert result["executed"] == 0
    assert result["selected_symbols"] == [("005930", "KRX")]
    assert agent._symbol_names == {"005930": "삼성전자"}
    assert agent._market_regime == "BULLISH"
    assert agent._market_context == "market-context"
    assert agent._trading_context == "trade-context"
    assert applied_thresholds == [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}]
    assert analyzed_payloads[0]["manual_provider_override"] == "CODEX"
    assert analyzed_payloads[0]["portfolio_snapshot"]["total_asset"] == 2_000_000
    assert resume_calls == ["session-1"]
    assert agent._last_session_id == "ended-session"
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("사이클 완료" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_skips_buy_candidate_when_cash_is_blocked(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    analyze_called = False

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 50_000,
            "total_asset": 1_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
            "min_holding_price": 100_000,
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal analyze_called
        analyze_called = True
        return {"executed": False}

    async def fail_buying_power(_symbol: str) -> dict:
        raise AssertionError("buying power should not be checked when buy_blocked is true")

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-cash-block")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 20)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda _candidates: None)
    monkeypatch.setattr("trading.kis_api.get_buying_power", fail_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 8))

    result = await agent._run_trading_cycle()

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 0
    assert result["executed"] == 0
    assert result["selected_symbols"] == [("005930", "KRX")]
    assert analyze_called is False
    assert any("현금 부족" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_skips_buy_candidate_when_buying_power_is_too_low(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    analyze_called = False

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_build_portfolio_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 1_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
            "min_holding_price": 0,
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {
            "selected": [{"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"}],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str) -> dict:
        return {"success": True, "max_qty": 0}

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal analyze_called
        analyze_called = True
        return {"executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-buying-power")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 20)
    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr(agent, "_build_market_context", lambda _scan_result: "market-context")
    monkeypatch.setattr(agent, "_build_trading_context", fake_build_trading_context)
    monkeypatch.setattr(agent, "_apply_scan_thresholds", lambda _candidates: None)
    monkeypatch.setattr("trading.kis_api.get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 9))

    result = await agent._run_trading_cycle()

    assert result["scanned"] == 1
    assert result["analyzed"] == 1
    assert result["signals"] == 0
    assert result["executed"] == 0
    assert analyze_called is False


@pytest.mark.asyncio
async def test_on_market_event_normalizes_a_prefixed_symbol_before_analysis(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    agent._running = True
    observed: dict = {}
    logged: list[tuple] = []

    async def fake_log(*args, **kwargs) -> None:
        logged.append((args, kwargs))

    async def fake_trading_context() -> str:
        return "live-context"

    async def fake_snapshot() -> dict:
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 1,
            "today_trade_count": 0,
            "holding_symbols": ["010170"],
        }

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs) -> dict:
        observed["stock_info"] = dict(stock_info)
        observed["cycle_id"] = cycle_id
        observed["portfolio_snapshot"] = kwargs.get("portfolio_snapshot")
        return {"executed": False}

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-live")
    monkeypatch.setattr(agent, "_build_trading_context", fake_trading_context)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)

    await agent._on_market_event(Event(
        type=EventType.PRICE_SURGE,
        data={
            "symbol": "A010170",
            "name": "대한광통신",
            "price": 10_030,
            "change_rate": 6.59,
        },
        source="test",
    ))

    assert observed["stock_info"]["symbol"] == "010170"
    assert observed["stock_info"]["name"] == "대한광통신"
    assert observed["portfolio_snapshot"]["holding_symbols"] == ["010170"]
    assert logged[0][1]["symbol"] == "010170"


@pytest.mark.asyncio
async def test_run_after_hours_cycle_generates_review_and_saves_report(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    events = []
    logs = []
    saved_reports = []
    generate_manual_calls = []
    end_session_calls = []

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeActivityRepo:
        def __init__(self, _session) -> None:
            pass

        async def count_by_date(self, _date):
            return {"CYCLE": 4, "TIER1_ANALYSIS": 3, "DECISION": 2, "ORDER": 1}

        async def get_by_date(self, _date, limit=50):
            return [SimpleNamespace(activity_type="CYCLE", phase="COMPLETE", summary="사이클 종료")]

    class FakePerformanceTracker:
        def __init__(self, _session) -> None:
            pass

        async def get_overall_stats(self):
            return {"overall": SimpleNamespace(total_trades=5, win_rate=0.6, total_pnl=12_345)}

    async def fake_publish(event) -> None:
        events.append(event)

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_collect_market_close_data():
        return ("close-data", "volume-data", "surge-data", "drop-data")

    async def fake_get_balance():
        return SimpleNamespace(
            total_asset=2_000_000,
            cash=1_000_000,
            stock_value=1_000_000,
            total_pnl=50_000,
            total_pnl_rate=2.5,
        )

    async def fake_generate_manual(prompt, **kwargs):
        generate_manual_calls.append({"prompt": prompt, **kwargs})
        return ('{"today_review":"좋음"}', "CODEX")

    async def fake_save_daily_report(report_date, parsed, **kwargs):
        saved_reports.append((report_date, parsed, kwargs))

    async def fake_generate_rules_from_review(parsed, today_date):
        return []

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: end_session_calls.append("end") or "after-hours-session")
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-after-hours")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda _timer: 80)
    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.agent_activity_repository.AgentActivityRepository", FakeActivityRepo)
    monkeypatch.setattr("analysis.feedback.performance_tracker.PerformanceTracker", FakePerformanceTracker)
    monkeypatch.setattr("analysis.feedback.trading_rules.trading_rule_engine.generate_rules_from_review", fake_generate_rules_from_review)
    monkeypatch.setattr(agent, "_collect_market_close_data", fake_collect_market_close_data)
    monkeypatch.setattr(agent, "_save_daily_report", fake_save_daily_report)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {"today_review": "좋음", "trade_evaluation": {"total_trades": 1}})
    monkeypatch.setattr(agent, "_broker_adapter", SimpleNamespace(get_balance=fake_get_balance))
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("agent.trading_agent.market_calendar.next_krx_open", lambda: _kst_time(9, 0))
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(16, 0))

    result = await agent._run_after_hours_cycle(manual_provider_override="CODEX")

    assert result == {"mode": "AFTER_HOURS", "review_generated": True}
    assert generate_manual_calls[0]["manual_provider_override"] == "CODEX"
    assert saved_reports and saved_reports[0][1]["today_review"] == "좋음"
    assert end_session_calls == ["end"]
    assert agent._last_session_id is None
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("장 마감 리뷰 완료" in args[2] for args, _kwargs in logs)
