import pytest

from scheduler.scheduler import TradingScheduler


@pytest.mark.asyncio
async def test_scheduler_start_skips_when_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    startup_called = False
    setup_called = False

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    def fake_setup_jobs() -> None:
        nonlocal setup_called
        setup_called = True

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_setup_jobs", fake_setup_jobs)

    await scheduler.start()

    assert scheduler.is_running is False
    assert setup_called is False
    assert startup_called is False


@pytest.mark.asyncio
async def test_scheduler_start_is_idempotent_when_already_running(monkeypatch) -> None:
    scheduler = TradingScheduler()
    scheduler._running = True
    startup_called = False
    setup_called = False

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    def fake_setup_jobs() -> None:
        nonlocal setup_called
        setup_called = True

    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_setup_jobs", fake_setup_jobs)

    await scheduler.start()

    assert scheduler.is_running is True
    assert setup_called is False
    assert startup_called is False


@pytest.mark.asyncio
async def test_market_open_scan_delegates_to_trading_agent_run_cycle(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed: list[str] = []

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_run_cycle() -> dict:
        observed.append("run_cycle")
        return {"selected_symbols": [], "analyzed": 3, "executed": 1}

    async def fake_get_holdings() -> list:
        observed.append("get_holdings")
        return []

    async def fake_update_subscriptions(symbols) -> None:
        observed.append(f"update:{len(symbols)}")

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("realtime.stream_manager.stream_manager.update_subscriptions", fake_update_subscriptions)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)

    await scheduler._market_open_scan()

    assert observed == ["run_cycle", "get_holdings"]


@pytest.mark.asyncio
async def test_intraday_rescan_skips_after_buy_cutoff_in_day_trading_mode(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    async def fake_log(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_HOUR", 14)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_MINUTE", 30)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 30))
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._intraday_rescan()

    assert run_cycle_called is False


@pytest.mark.asyncio
async def test_holdings_check_returns_early_outside_trading_hours(monkeypatch) -> None:
    scheduler = TradingScheduler()
    realtime_updated = False

    async def fake_update_realtime_subscriptions() -> None:
        nonlocal realtime_updated
        realtime_updated = True

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)

    await scheduler._holdings_check()

    assert realtime_updated is False
