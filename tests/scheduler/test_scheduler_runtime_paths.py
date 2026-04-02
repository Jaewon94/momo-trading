import pytest
from types import SimpleNamespace

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
async def test_market_open_scan_skips_entirely_on_holiday(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: True)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._market_open_scan()

    assert run_cycle_called is False


@pytest.mark.asyncio
async def test_market_open_scan_checks_overnight_gap_in_swing_mode(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed: list[str] = []

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_check_overnight_gap() -> None:
        observed.append("overnight_gap")

    async def fake_run_cycle() -> dict:
        observed.append("run_cycle")
        return {"selected_symbols": [], "analyzed": 0, "executed": 0}

    async def fake_get_holdings() -> list:
        observed.append("get_holdings")
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr(scheduler, "_check_overnight_gap", fake_check_overnight_gap)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._market_open_scan()

    assert observed == ["overnight_gap", "run_cycle", "get_holdings"]


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
async def test_intraday_rescan_refreshes_subscriptions_when_new_symbols_exist(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed: list = []

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_run_cycle() -> dict:
        observed.append("run_cycle")
        return {"selected_symbols": [("005930", "KRX"), ("000660", "KRX")], "analyzed": 2, "executed": 1}

    async def fake_get_holdings() -> list:
        observed.append("get_holdings")
        return [SimpleNamespace(symbol="005930"), SimpleNamespace(symbol="035720")]

    async def fake_update_subscriptions(symbols) -> None:
        observed.append(symbols)

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 11, 0))
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("realtime.stream_manager.stream_manager.update_subscriptions", fake_update_subscriptions)

    await scheduler._intraday_rescan()

    assert observed[0:2] == ["run_cycle", "get_holdings"]
    assert observed[2] == [("005930", "KRX"), ("000660", "KRX"), ("035720", "KRX")]


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


@pytest.mark.asyncio
async def test_holdings_check_returns_early_when_no_holdings_exist(monkeypatch) -> None:
    scheduler = TradingScheduler()
    realtime_updated = False

    async def fake_update_realtime_subscriptions() -> None:
        nonlocal realtime_updated
        realtime_updated = True

    async def fake_get_holdings() -> list:
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)

    await scheduler._holdings_check()

    assert realtime_updated is False


@pytest.mark.asyncio
async def test_trigger_rescan_after_sell_skips_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._trigger_rescan_after_sell()

    assert run_cycle_called is False


@pytest.mark.asyncio
async def test_trigger_rescan_after_sell_runs_when_cash_and_market_conditions_allow(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed: list[str] = []

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_get_balance():
        observed.append("get_balance")
        return SimpleNamespace(cash=500_000)

    async def fake_run_cycle() -> dict:
        observed.append("run_cycle")
        return {}

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_HOUR", 14)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_MINUTE", 30)
    monkeypatch.setattr("scheduler.scheduler.settings.MIN_BUY_QUANTITY", 1)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("trading.account_manager.account_manager.get_balance", fake_get_balance)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._trigger_rescan_after_sell()

    assert observed == ["get_balance", "run_cycle"]


@pytest.mark.asyncio
async def test_post_market_if_needed_skips_when_report_exists(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def get_by_date(self, _target_date):
            return object()

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.daily_report_repository.DailyReportRepository", FakeRepo)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._post_market_if_needed()

    assert run_cycle_called is False


@pytest.mark.asyncio
async def test_post_market_if_needed_triggers_after_hours_review_when_missing(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed: list[str] = []

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session):
            pass

        async def get_by_date(self, _target_date):
            return None

    async def fake_run_cycle() -> dict:
        observed.append("run_cycle")
        return {}

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.daily_report_repository.DailyReportRepository", FakeRepo)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 15, 40))
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_day", lambda _now: True)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._post_market_if_needed()

    assert observed == ["run_cycle"]


@pytest.mark.asyncio
async def test_force_liquidation_skips_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    get_holdings_called = False

    async def fake_get_holdings() -> list:
        nonlocal get_holdings_called
        get_holdings_called = True
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._force_liquidation()

    assert get_holdings_called is False


@pytest.mark.asyncio
async def test_force_liquidation_logs_when_no_holdings_exist(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[tuple] = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_get_holdings() -> list:
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._force_liquidation()

    assert len(logs) == 1
    assert "청산 불필요" in logs[0][0][2]


@pytest.mark.asyncio
async def test_force_liquidation_returns_when_smart_liquidation_keeps_all_holdings(monkeypatch) -> None:
    scheduler = TradingScheduler()
    place_order_called = False
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=3, pnl_rate=1.5, current_price=71_000)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(holdings):
        return [], holdings

    async def fake_place_order(**kwargs):
        nonlocal place_order_called
        place_order_called = True
        return SimpleNamespace(success=True, data={"order_id": "SELL-0"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._force_liquidation()

    assert place_order_called is False


@pytest.mark.asyncio
async def test_force_liquidation_triggers_rescan_after_successful_swing_sell(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    removed_levels: list[str] = []
    created_tasks: list[object] = []
    confirmed_orders: list[dict] = []
    released: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=3, pnl_rate=1.5, current_price=71_000)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(holdings):
        return holdings, []

    async def fake_place_order(**kwargs):
        return SimpleNamespace(success=True, data={"order_id": "SELL-1"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(symbol: str) -> bool:
        return True

    def fake_release_sell(symbol: str) -> None:
        released.append(symbol)

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_trigger_rescan_after_sell() -> None:
        return None

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", fake_release_sell)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr(scheduler, "_trigger_rescan_after_sell", fake_trigger_rescan_after_sell)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._force_liquidation()

    assert confirmed_orders[0]["order_id"] == "SELL-1"
    assert confirmed_orders[0]["exit_reason"] == "FORCE_LIQUIDATION"
    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert len(created_tasks) == 1
    assert any("완료: 1건 매도" in message for message in logs)


@pytest.mark.asyncio
async def test_smart_liquidation_returns_fallback_sell_when_no_holdings_data(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=3)

    async def fake_collect_holdings_data(_sellable):
        return [], {}, [holding]

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == [holding]
    assert to_hold == []


@pytest.mark.asyncio
async def test_smart_liquidation_combines_llm_and_fallback_decisions(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding_hold = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    holding_sell = SimpleNamespace(symbol="000660", name="SK하이닉스", quantity=1)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    holdings_data = [
        {"symbol": "005930", "stock_name": "삼성전자"},
        {"symbol": "000660", "stock_name": "SK하이닉스"},
    ]
    holdings_map = {
        "005930": (holding_hold, trade_result, 71_000),
        "000660": (holding_sell, trade_result, 120_000),
    }

    async def fake_collect_holdings_data(_sellable):
        return holdings_data, holdings_map, []

    async def fake_generate_tier1(prompt, system_prompt=None):
        return '{"decisions":[{"symbol":"005930","action":"HOLD","reason":"추세 유지","confidence":0.82}]}', "CODEX"

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    fallback = SimpleNamespace(action="SELL", reason="보유 기간 초과")

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {"decisions": [{"symbol": "005930", "action": "HOLD", "reason": "추세 유지", "confidence": 0.82}]},
    )
    monkeypatch.setattr("strategy.holding_policy.evaluate_overnight_hold", lambda *args, **kwargs: fallback)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")

    to_sell, to_hold = await scheduler._smart_liquidation([holding_hold, holding_sell])

    assert to_hold == [holding_hold]
    assert to_sell == [holding_sell]
    assert any("삼성전자(005930): HOLD" in message for message in logs)
    assert any("SK하이닉스(000660): SELL" in message for message in logs)


@pytest.mark.asyncio
async def test_collect_holdings_data_marks_symbol_for_fallback_when_price_lookup_fails(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return None

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=False, data=None)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)

    holdings_data, holdings_map, fallback_sell = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert fallback_sell == [holding]


@pytest.mark.asyncio
async def test_collect_holdings_data_builds_prompt_payload_for_valid_holding(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    trade_result = SimpleNamespace(
        stock_name="삼성전자",
        ai_confidence=0.83,
        ai_target_price=75_000,
        ai_stop_loss_price=68_000,
        strategy_type="STABLE_SHORT",
    )

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=True, data={"price": 73_000})

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_500, take_profit=74_500),
    )
    monkeypatch.setattr("strategy.holding_policy._calc_hold_days", lambda _tr: 2)
    monkeypatch.setattr("strategy.holding_policy._get_max_hold_days", lambda _strategy, _settings: 5)

    holdings_data, holdings_map, fallback_sell = await scheduler._collect_holdings_data([holding])

    assert fallback_sell == []
    assert holdings_map["005930"] == (holding, trade_result, 73_000)
    assert holdings_data[0]["symbol"] == "005930"
    assert holdings_data[0]["stock_name"] == "삼성전자"
    assert round(holdings_data[0]["pnl_rate"], 2) == round((73_000 - 70_000) / 70_000 * 100, 2)
    assert holdings_data[0]["active_stop_loss"] == 68_500
    assert holdings_data[0]["active_take_profit"] == 74_500


@pytest.mark.asyncio
async def test_force_liquidation_skips_entirely_on_holiday(monkeypatch) -> None:
    scheduler = TradingScheduler()
    get_holdings_called = False

    async def fake_get_holdings() -> list:
        nonlocal get_holdings_called
        get_holdings_called = True
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._force_liquidation()

    assert get_holdings_called is False


@pytest.mark.asyncio
async def test_force_liquidation_returns_when_no_positive_quantity_exists(monkeypatch) -> None:
    scheduler = TradingScheduler()
    smart_called = False
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=0)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(_sellable):
        nonlocal smart_called
        smart_called = True
        return [], []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)

    await scheduler._force_liquidation()

    assert smart_called is False


@pytest.mark.asyncio
async def test_force_liquidation_day_trading_mode_skips_smart_liquidation(monkeypatch) -> None:
    scheduler = TradingScheduler()
    smart_called = False
    place_order_called = False
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, pnl_rate=1.2, current_price=71_000)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(_sellable):
        nonlocal smart_called
        smart_called = True
        return [], []

    async def fake_place_order(**kwargs):
        nonlocal place_order_called
        place_order_called = True
        return SimpleNamespace(success=True, data={"order_id": "SELL-DAY"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_acquire_sell(_symbol: str) -> bool:
        return False

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert smart_called is False
    assert place_order_called is False


@pytest.mark.asyncio
async def test_force_liquidation_retries_failed_orders_once(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    sleep_calls: list[float] = []
    place_order_calls: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, pnl_rate=-1.3, current_price=69_500)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(_sellable):
        return [holding], []

    async def fake_place_order(**kwargs):
        place_order_calls.append(kwargs["symbol"])
        if len(place_order_calls) == 1:
            return SimpleNamespace(success=False, data=None, error="temporary fail")
        return SimpleNamespace(success=True, data={"order_id": "SELL-RETRY"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert place_order_calls == ["005930", "005930"]
    assert sleep_calls == [5]
    assert any("청산 1건 실패" in message for message in logs)
    assert any("실패 1건" in message for message in logs)


@pytest.mark.asyncio
async def test_force_liquidation_continues_when_order_task_raises(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, pnl_rate=0.5, current_price=71_000)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(_sellable):
        return [holding], []

    async def fake_place_order(**kwargs):
        raise RuntimeError("network down")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert any("스마트 청산 완료: 0건 매도" in message for message in logs)


@pytest.mark.asyncio
async def test_collect_holdings_data_marks_symbol_for_fallback_when_trade_result_is_missing(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return None

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=True, data={"price": 73_000})

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)

    holdings_data, holdings_map, fallback_sell = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert fallback_sell == [holding]


@pytest.mark.asyncio
async def test_collect_holdings_data_marks_symbol_for_fallback_on_repository_error(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            raise RuntimeError("db failure")

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=True, data={"price": 73_000})

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)

    holdings_data, holdings_map, fallback_sell = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert fallback_sell == [holding]


@pytest.mark.asyncio
async def test_smart_liquidation_falls_back_to_code_rules_when_llm_raises(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_collect_holdings_data(_sellable):
        return [{"symbol": "005930", "stock_name": "삼성전자"}], {"005930": (holding, trade_result, 73_000)}, []

    async def fake_generate_tier1(prompt, system_prompt=None):
        raise RuntimeError("llm timeout")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("strategy.holding_policy.evaluate_overnight_hold", lambda *args, **kwargs: SimpleNamespace(action="HOLD", reason="추세 유지"))
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "RANGE")

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == []
    assert to_hold == [holding]
    assert "(코드 룰 폴백)" in logs[0]
    assert "삼성전자(005930): HOLD" in logs[0]


@pytest.mark.asyncio
async def test_smart_liquidation_respects_explicit_llm_sell_decision(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_collect_holdings_data(_sellable):
        return [{"symbol": "005930", "stock_name": "삼성전자"}], {"005930": (holding, trade_result, 72_000)}, []

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"SELL","reason":"변동성 확대","confidence":0.63}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {"decisions": [{"symbol": "005930", "action": "SELL", "reason": "변동성 확대", "confidence": 0.63}]},
    )
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "RANGE")

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == [holding]
    assert to_hold == []
    assert "SELL" in logs[0]


@pytest.mark.asyncio
async def test_intraday_holdings_review_sells_position_and_triggers_rescan(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    removed_levels: list[str] = []
    confirmed_orders: list[dict] = []
    released: list[str] = []
    created_tasks: list[object] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_collect_holdings_data(_sellable):
        return (
            [{"symbol": "005930", "stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"}],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"SELL","reason":"모멘텀 약화","confidence":0.71}]}',
            "CODEX",
        )

    async def fake_place_order(**kwargs):
        return SimpleNamespace(success=True, data={"order_id": "SELL-REVIEW"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {
            "decisions": [
                {"symbol": "005930", "action": "SELL", "reason": "모멘텀 약화", "confidence": 0.71}
            ]
        },
    )
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "강세 유지")
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._intraday_holdings_review()

    assert confirmed_orders[0]["order_id"] == "SELL-REVIEW"
    assert confirmed_orders[0]["exit_reason"] == "HOLDINGS_REVIEW"
    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert len(created_tasks) == 1
    assert any("장중 재평가 매도" in message for message in logs)
    assert any("SELL 매도 성공" in message for message in logs)


@pytest.mark.asyncio
async def test_intraday_holdings_review_adjusts_thresholds_on_hold(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    thresholds: list[tuple[str, dict]] = []
    trade_result = SimpleNamespace(ai_stop_loss_price=None, ai_target_price=None)
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = 0
            self.committed = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self) -> None:
            self.flushed += 1

        async def commit(self) -> None:
            self.committed += 1

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, _symbol: str):
            return trade_result

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_collect_holdings_data(_sellable):
        return (
            [{"symbol": "005930", "stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"}],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"HOLD","reason":"상승 추세","confidence":0.88,"adjusted_stop_loss_price":69000,"adjusted_take_profit_price":74500}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 30))
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {
            "decisions": [
                {
                    "symbol": "005930",
                    "action": "HOLD",
                    "reason": "상승 추세",
                    "confidence": 0.88,
                    "adjusted_stop_loss_price": 69_000,
                    "adjusted_take_profit_price": 74_500,
                }
            ]
        },
    )
    monkeypatch.setattr("realtime.event_detector.event_detector.set_thresholds", lambda symbol, **kwargs: thresholds.append((symbol, kwargs)))
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "강세 유지")

    await scheduler._intraday_holdings_review()

    assert thresholds == [("005930", {"stop_loss": 69_000.0, "take_profit": 74_500.0})]
    assert trade_result.ai_stop_loss_price == 69_000.0
    assert trade_result.ai_target_price == 74_500.0
    assert session.flushed == 1
    assert session.committed == 1
    assert any("임계값 조정" in message for message in logs)


@pytest.mark.asyncio
async def test_intraday_holdings_review_queues_add_buy_followup(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    created_tasks: list[object] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="N/A")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_collect_holdings_data(_sellable):
        return (
            [{"symbol": "005930", "stock_name": "삼성전자", "strategy_type": "N/A"}],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"ADD_BUY","reason":"추세 강화","confidence":0.77}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_analyze_and_trade(**kwargs):
        return None

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 0))
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {
            "decisions": [
                {"symbol": "005930", "action": "ADD_BUY", "reason": "추세 강화", "confidence": 0.77}
            ]
        },
    )
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "강세 유지")
    monkeypatch.setattr("agent.trading_agent.trading_agent._analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._intraday_holdings_review()

    assert len(created_tasks) == 1
    assert any("ADD_BUY → 분석 파이프라인 진행" in message for message in logs)


@pytest.mark.asyncio
async def test_check_overnight_positions_restores_thresholds_and_warns_on_max_hold(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    restored_thresholds: list[tuple[str, dict]] = []
    now = __import__("datetime").datetime(2026, 4, 2, 8, 50)
    orphan = SimpleNamespace(
        stock_symbol="035720",
        stock_name="카카오",
        quantity=1,
        entry_price=50_000,
        entry_at=now - __import__("datetime").timedelta(days=2),
        exit_at=None,
        exit_reason="",
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        ai_stop_loss_price=None,
        ai_target_price=None,
        strategy_type="SWING",
    )
    live = SimpleNamespace(
        stock_symbol="005930",
        stock_name="삼성전자",
        quantity=2,
        entry_price=70_000,
        entry_at=now - __import__("datetime").timedelta(days=6),
        exit_at=None,
        exit_reason="",
        ai_stop_loss_price=68_000,
        ai_target_price=75_000,
        strategy_type="STABLE_SHORT",
    )

    class FakeSession:
        def __init__(self) -> None:
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self) -> None:
            self.commits += 1

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [orphan, live]

    async def fake_get_holdings() -> list:
        return [SimpleNamespace(symbol="005930", quantity=2)]

    async def fake_get_current_price(symbol: str):
        assert symbol == "035720"
        return SimpleNamespace(success=True, data={"price": 48_000})

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)
    monkeypatch.setattr("realtime.event_detector.event_detector.set_thresholds", lambda symbol, **kwargs: restored_thresholds.append((symbol, kwargs)))
    monkeypatch.setattr("strategy.holding_policy._calc_hold_days", lambda tr: 6 if tr.stock_symbol == "005930" else 2)
    monkeypatch.setattr("strategy.holding_policy._get_max_hold_days", lambda _strategy, _settings: 5)
    monkeypatch.setattr("util.time_util.now_kst", lambda: now)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._check_overnight_positions()

    assert session.commits == 1
    assert orphan.exit_reason == "ORPHAN_CLEANUP"
    assert orphan.exit_price == 48_000
    assert orphan.pnl == -2_000
    assert restored_thresholds == [("005930", {"stop_loss": 68_000, "take_profit": 75_000})]
    assert "임계값 복원 1건" in logs[0]
    assert "초과보유" in logs[0]


@pytest.mark.asyncio
async def test_intraday_holdings_review_falls_back_when_llm_fails_and_trading_is_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_collect_holdings_data(_sellable):
        return (
            [{"symbol": "005930", "stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"}],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        raise RuntimeError("llm timeout")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 15))
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr("strategy.holding_policy.evaluate_overnight_hold", lambda *args, **kwargs: SimpleNamespace(action="SELL", reason="규칙 기반 청산"))
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "RANGE")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "변동성 확대")

    await scheduler._intraday_holdings_review()

    assert "(코드 룰 폴백)" in logs[0]
    assert "TRADING_ENABLED=false" in logs[0]


@pytest.mark.asyncio
async def test_intraday_holdings_review_records_sell_failure_message(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    released: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_collect_holdings_data(_sellable):
        return (
            [{"symbol": "005930", "stock_name": "삼성전자", "strategy_type": "STABLE_SHORT"}],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"SELL","reason":"추세 이탈","confidence":0.59}]}',
            "CODEX",
        )

    async def fake_place_order(**kwargs):
        return SimpleNamespace(success=False, data=None, error="broker reject")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 45))
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {"decisions": [{"symbol": "005930", "action": "SELL", "reason": "추세 이탈", "confidence": 0.59}]},
    )
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "RANGE")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "변동성 확대")
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)

    await scheduler._intraday_holdings_review()

    assert released == ["005930"]
    assert "SELL 매도 실패" in logs[0]


@pytest.mark.asyncio
async def test_check_overnight_gap_executes_sell_on_stop_loss(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    removed_levels: list[str] = []
    confirmed_orders: list[dict] = []
    released: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_symbol="005930", ai_stop_loss_price=68_000, ai_target_price=75_000)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [trade_result]

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=True, data={"price": 67_000})

    async def fake_place_order(**kwargs):
        return SimpleNamespace(success=True, data={"order_id": "SELL-GAP"}, error=None)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)

    await scheduler._check_overnight_gap()

    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert confirmed_orders[0]["order_id"] == "SELL-GAP"
    assert confirmed_orders[0]["exit_reason"] == "GAP_CHECK"
    assert "갭 하락 손절" in logs[0]


@pytest.mark.asyncio
async def test_check_overnight_gap_logs_disabled_target_profit_sell(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_symbol="005930", ai_stop_loss_price=68_000, ai_target_price=75_000)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [trade_result]

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_current_price(_symbol: str):
        return SimpleNamespace(success=True, data={"price": 76_000})

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fake_get_current_price)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)

    await scheduler._check_overnight_gap()

    assert "갭 상승 익절" in logs[0]
    assert "TRADING_ENABLED=false" in logs[0]
