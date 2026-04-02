from datetime import datetime

import pytest

from agent.trading_agent import TradingAgent


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
