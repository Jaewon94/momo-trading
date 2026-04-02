from datetime import datetime

import pytest

from agent.trading_agent import TradingAgent
from core.events import EventType


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
