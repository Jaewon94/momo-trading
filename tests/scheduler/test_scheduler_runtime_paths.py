import pytest
from types import SimpleNamespace
import asyncio
import json

from core.events import Event, EventType
from scheduler.scheduler import TradingScheduler
from strategy.trade_horizon import TradeHorizon
from trading.enums import ActivityPhase, ActivityType, Market, OrderSide, OrderType
from trading.models import CurrentPrice, OrderResult


@pytest.fixture(autouse=True)
def _default_broker_provider(monkeypatch) -> None:
    monkeypatch.setattr("scheduler.scheduler.settings.BROKER_PROVIDER", "KIS")
    monkeypatch.setattr("scheduler.scheduler.settings.ORDER_SUBMISSION_MODE", "FULL")


@pytest.mark.asyncio
async def test_scheduler_place_market_sell_respects_read_only_order_submission_mode(monkeypatch) -> None:
    scheduler = TradingScheduler()
    requests = []

    class FakeBrokerAdapter:
        async def place_order(self, request):
            requests.append(request)
            return OrderResult(success=True, order_id="SELL-1", message="submitted")

    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.ORDER_SUBMISSION_MODE", "READ_ONLY", raising=False)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())

    result = await scheduler._place_market_sell("005930", 3)

    assert result.success is False
    assert result.order_id == ""
    assert "READ_ONLY" in result.message
    assert requests == []


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
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", False)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_setup_jobs", fake_setup_jobs)

    await scheduler.start()

    assert scheduler.is_running is False
    assert setup_called is False
    assert startup_called is False


@pytest.mark.asyncio
async def test_scheduler_start_runs_news_jobs_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    startup_called = False
    news_poll_called = False
    news_translation_called = False
    job_ids: list[str] = []
    created_tasks: list[object] = []

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    async def fake_news_poll(*args, **kwargs) -> None:
        nonlocal news_poll_called
        news_poll_called = True

    async def fake_news_translation_backfill() -> None:
        nonlocal news_translation_called
        news_translation_called = True

    class FakeScheduler:
        def start(self) -> None:
            return None

        def add_job(self, _func, _trigger, **kwargs) -> None:
            job_ids.append(kwargs["id"])

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        return DummyTask()

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)
    monkeypatch.setattr(scheduler, "_news_translation_backfill", fake_news_translation_backfill)
    monkeypatch.setattr(scheduler, "_build_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler.start()
    await asyncio.sleep(0)

    for coro in created_tasks:
        await coro

    assert scheduler.is_running is True
    assert startup_called is False
    assert news_poll_called is True
    assert news_translation_called is True
    assert set(job_ids) == {
        "news_poll_trading",
        "news_poll_off_hours",
        "news_translation_backfill",
        "resource_snapshot",
        "observability_maintenance",
        "forward_return_label",
    }


@pytest.mark.asyncio
async def test_scheduler_start_runs_news_poll_once_on_startup_when_trading_enabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    startup_called = False
    news_poll_called = False
    news_translation_called = False
    job_ids: list[str] = []
    created_tasks: list[object] = []

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    async def fake_news_poll(*args, **kwargs) -> None:
        nonlocal news_poll_called
        news_poll_called = True

    async def fake_news_translation_backfill() -> None:
        nonlocal news_translation_called
        news_translation_called = True

    class FakeScheduler:
        def start(self) -> None:
            return None

        def add_job(self, _func, _trigger, **kwargs) -> None:
            job_ids.append(kwargs["id"])

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        return DummyTask()

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)
    monkeypatch.setattr(scheduler, "_news_translation_backfill", fake_news_translation_backfill)
    monkeypatch.setattr(scheduler, "_build_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler.start()
    await asyncio.sleep(0)

    for coro in created_tasks:
        await coro

    assert scheduler.is_running is True
    assert startup_called is True
    assert news_poll_called is True
    assert news_translation_called is True
    assert "news_poll_trading" in job_ids
    assert "news_poll_off_hours" in job_ids
    assert "news_translation_backfill" in job_ids
    assert "resource_snapshot" in job_ids
    assert "observability_maintenance" in job_ids
    assert "forward_return_label" in job_ids
    assert "account_equity_snapshot" in job_ids


@pytest.mark.asyncio
async def test_scheduler_start_does_not_block_on_initial_news_poll(monkeypatch) -> None:
    scheduler = TradingScheduler()
    startup_called = False
    news_poll_started = asyncio.Event()
    allow_news_poll_finish = asyncio.Event()

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    async def fake_news_poll(*args, **kwargs) -> None:
        news_poll_started.set()
        await allow_news_poll_finish.wait()

    class FakeScheduler:
        def start(self) -> None:
            return None

        def add_job(self, _func, _trigger, **kwargs) -> None:
            return None

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)
    monkeypatch.setattr(scheduler, "_build_scheduler", lambda: FakeScheduler())

    start_task = asyncio.create_task(scheduler.start())

    await asyncio.wait_for(news_poll_started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert startup_called is True
    assert start_task.done() is True
    assert scheduler.is_running is True

    allow_news_poll_finish.set()
    await asyncio.wait_for(start_task, timeout=1)


@pytest.mark.asyncio
async def test_scheduler_start_is_idempotent_when_already_running(monkeypatch) -> None:
    scheduler = TradingScheduler()
    scheduler._running = True
    scheduler._trading_jobs_registered = True
    scheduler._news_jobs_registered = True
    scheduler._common_jobs_registered = True
    startup_called = False
    setup_called = False

    async def fake_on_startup() -> None:
        nonlocal startup_called
        startup_called = True

    def fake_setup_jobs(**_kwargs) -> None:
        nonlocal setup_called
        setup_called = True

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_setup_jobs", fake_setup_jobs)

    await scheduler.start()

    assert scheduler.is_running is True
    assert setup_called is False
    assert startup_called is False


@pytest.mark.asyncio
async def test_scheduler_start_registers_trading_jobs_when_enabled_after_news_only_start(monkeypatch) -> None:
    """뉴스 잡만 등록된 채로 실행 중일 때, SCHEDULER_ENABLED가 True로 바뀐 뒤 start()를 다시 호출하면 트레이딩 잡이 추가 등록되어야 한다."""
    scheduler = TradingScheduler()
    job_ids: list[str] = []
    created_tasks: list[object] = []

    async def fake_on_startup() -> None:
        return None

    async def fake_news_poll(*args, **kwargs) -> None:
        return None

    async def fake_news_translation_backfill() -> None:
        return None

    class FakeScheduler:
        def start(self) -> None:
            return None

        def add_job(self, _func, _trigger, **kwargs) -> None:
            job_ids.append(kwargs["id"])

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr(scheduler, "_on_startup", fake_on_startup)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)
    monkeypatch.setattr(scheduler, "_news_translation_backfill", fake_news_translation_backfill)
    monkeypatch.setattr(scheduler, "_build_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", False)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    await scheduler.start()
    assert scheduler.is_running is True
    assert scheduler._news_jobs_registered is True
    assert scheduler._trading_jobs_registered is False
    assert "news_poll_trading" in job_ids
    assert "intraday_rescan" not in job_ids
    assert "account_equity_snapshot" not in job_ids

    job_ids.clear()
    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", True)
    await scheduler.start()

    assert scheduler._trading_jobs_registered is True
    assert "intraday_rescan" in job_ids
    assert "intraday_rescan_interval" in job_ids
    assert "account_equity_snapshot" in job_ids
    assert "holdings_check" in job_ids
    # common jobs(resource_snapshot 등)와 news 잡은 첫 start에서 등록됐으므로 중복 등록되지 않아야 한다.
    assert "resource_snapshot" not in job_ids
    assert "news_poll_trading" not in job_ids


@pytest.mark.asyncio
async def test_scheduler_on_startup_schedules_market_open_scan_during_trading_hours(monkeypatch) -> None:
    scheduler = TradingScheduler()
    sleep_calls: list[float] = []
    created_tasks: list[object] = []
    snapshot_calls = 0

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def fake_market_open_scan() -> None:
        return None

    async def fake_account_equity_snapshot() -> None:
        nonlocal snapshot_calls
        snapshot_calls += 1

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(scheduler, "_market_open_scan", fake_market_open_scan)
    monkeypatch.setattr(scheduler, "_account_equity_snapshot", fake_account_equity_snapshot)

    await scheduler._on_startup()

    assert sleep_calls == [3]
    assert snapshot_calls == 1
    assert any(
        getattr(task, "cr_code", None) and task.cr_code.co_name == "fake_market_open_scan"
        for task in created_tasks
    )


@pytest.mark.asyncio
async def test_scheduler_on_startup_skips_snapshot_refresh_when_trading_disabled(monkeypatch) -> None:
    """TRADING_ENABLED=False면 스냅샷 갱신도 건너뛴다 (불필요한 브로커 호출 차단)."""
    scheduler = TradingScheduler()
    snapshot_calls = 0

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_account_equity_snapshot() -> None:
        nonlocal snapshot_calls
        snapshot_calls += 1

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr(scheduler, "_account_equity_snapshot", fake_account_equity_snapshot)

    await scheduler._on_startup()

    assert snapshot_calls == 0


@pytest.mark.asyncio
async def test_scheduler_on_startup_continues_after_snapshot_refresh_failure(monkeypatch) -> None:
    """스냅샷 갱신이 실패해도 market_open_scan은 예약되어야 한다."""
    scheduler = TradingScheduler()
    created_tasks: list[object] = []

    async def fake_sleep(_seconds: float) -> None:
        return None

    async def fake_market_open_scan() -> None:
        return None

    async def failing_account_equity_snapshot() -> None:
        raise RuntimeError("simulated broker timeout")

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr(scheduler, "_market_open_scan", fake_market_open_scan)
    monkeypatch.setattr(scheduler, "_account_equity_snapshot", failing_account_equity_snapshot)

    await scheduler._on_startup()

    assert any(
        getattr(task, "cr_code", None) and task.cr_code.co_name == "fake_market_open_scan"
        for task in created_tasks
    )


@pytest.mark.asyncio
async def test_scheduler_on_startup_skips_market_open_scan_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    sleep_calls: list[float] = []
    created_tasks: list[object] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)

    await scheduler._on_startup()

    assert sleep_calls == [3]
    assert created_tasks == []


@pytest.mark.asyncio
async def test_scheduler_on_startup_schedules_post_market_check_outside_trading_hours(monkeypatch) -> None:
    scheduler = TradingScheduler()
    sleep_calls: list[float] = []
    created_tasks: list[object] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def fake_post_market_if_needed() -> None:
        return None

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr(
        "scheduler.market_calendar.market_calendar.next_krx_open",
        lambda: __import__("datetime").datetime(2026, 4, 3, 9, 0),
    )
    monkeypatch.setattr(scheduler, "_post_market_if_needed", fake_post_market_if_needed)

    await scheduler._on_startup()

    assert sleep_calls == [3]
    assert any(
        getattr(task, "cr_code", None) and task.cr_code.co_name == "fake_post_market_if_needed"
        for task in created_tasks
    )


def test_scheduler_setup_jobs_registers_expected_job_ids() -> None:
    scheduler = TradingScheduler()
    job_ids: list[str] = []

    class FakeScheduler:
        def add_job(self, _func, _trigger, **kwargs) -> None:
            job_ids.append(kwargs["id"])

    scheduler.scheduler = FakeScheduler()

    scheduler._setup_jobs()

    assert set(job_ids) == {
        "pre_market",
        "market_open_scan",
        "intraday_rescan",
        "intraday_rescan_interval",
        "news_poll_trading",
        "news_poll_off_hours",
        "news_translation_backfill",
        "resource_snapshot",
        "observability_maintenance",
        "forward_return_label",
        "account_equity_snapshot",
        "fast_holdings_guard",
        "holdings_check",
        "intraday_holdings_review",
        "force_liquidation",
        "post_market",
        "portfolio_sync",
        "market_data",
        "expire_recommendations",
    }


def test_soft_stop_defers_shallow_breach_once_then_confirms(monkeypatch) -> None:
    scheduler = TradingScheduler()
    monkeypatch.setattr("scheduler.scheduler.settings.RISK_APPETITE", "MODERATE")

    defer_first, reason_first = scheduler._should_defer_soft_stop(
        "005930",
        pnl_rate=-3.2,
        stop_loss_pct=-3.0,
        minutes_left=45,
        observed_at=1000.0,
        scope="holdings_check",
    )
    defer_second, reason_second = scheduler._should_defer_soft_stop(
        "005930",
        pnl_rate=-3.3,
        stop_loss_pct=-3.0,
        minutes_left=44,
        observed_at=1060.0,
        scope="holdings_check",
    )

    assert defer_first is True
    assert reason_first == "first_observation"
    assert defer_second is False
    assert reason_second == "confirmed"


def test_soft_stop_allows_immediate_sell_on_hard_breach_or_near_close(monkeypatch) -> None:
    scheduler = TradingScheduler()
    monkeypatch.setattr("scheduler.scheduler.settings.RISK_APPETITE", "MODERATE")

    defer_hard, reason_hard = scheduler._should_defer_soft_stop(
        "005930",
        pnl_rate=-4.1,
        stop_loss_pct=-3.0,
        minutes_left=45,
        observed_at=1000.0,
        scope="holdings_check",
    )
    defer_late, reason_late = scheduler._should_defer_soft_stop(
        "000660",
        pnl_rate=-3.2,
        stop_loss_pct=-3.0,
        minutes_left=10,
        observed_at=1000.0,
        scope="holdings_check",
    )

    assert defer_hard is False
    assert reason_hard == "hard_breach"
    assert defer_late is False
    assert reason_late == "near_close"


def test_partial_take_profit_uses_horizon_profile(monkeypatch) -> None:
    scheduler = TradingScheduler()
    trade_result = SimpleNamespace(
        strategy_type="AGGRESSIVE_SHORT",
        notes='{"trade_horizon":"SHORT"}',
    )

    monkeypatch.setattr("scheduler.scheduler.settings.POSITION_EXIT_MANAGEMENT_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.PARTIAL_TAKE_PROFIT_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.PARTIAL_TAKE_PROFIT_PCT_SHORT", 1.5)
    monkeypatch.setattr("scheduler.scheduler.settings.PARTIAL_TAKE_PROFIT_SIZE_PCT_SHORT", 40.0)

    should_sell, quantity, reason = scheduler._should_partial_take_profit(
        tr=trade_result,
        pnl_rate=1.7,
        holding_quantity=10,
    )

    assert should_sell is True
    assert quantity == 4
    assert "SHORT 부분익절" in reason


def test_partial_take_profit_skips_when_already_done() -> None:
    scheduler = TradingScheduler()
    trade_result = SimpleNamespace(
        strategy_type="AGGRESSIVE_SHORT",
        notes='{"trade_horizon":"SHORT"} | PARTIAL_TAKE_PROFIT_DONE',
    )

    should_sell, quantity, reason = scheduler._should_partial_take_profit(
        tr=trade_result,
        pnl_rate=5.0,
        holding_quantity=10,
    )

    assert should_sell is False
    assert quantity == 0
    assert reason == ""


def test_breakeven_and_scale_in_are_horizon_aware(monkeypatch) -> None:
    scheduler = TradingScheduler()
    mid_trade = SimpleNamespace(strategy_type="STABLE_SHORT", notes='{"trade_horizon":"MID"}')
    short_trade = SimpleNamespace(strategy_type="AGGRESSIVE_SHORT", notes='{"trade_horizon":"SHORT"}')

    monkeypatch.setattr("scheduler.scheduler.settings.BREAKEVEN_STOP_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.BREAKEVEN_TRIGGER_PCT_MID", 1.5)
    monkeypatch.setattr("scheduler.scheduler.settings.BREAKEVEN_BUFFER_BPS", 10)

    assert scheduler._breakeven_stop_price(
        avg_buy_price=10_000,
        pnl_rate=1.6,
        tr=mid_trade,
    ) == pytest.approx(10_010)

    assert scheduler._scale_in_candidate_reason(
        tr=mid_trade,
        pnl_rate=-1.5,
        current_price=9_850,
        active_stop_loss=9_600,
    )
    assert scheduler._scale_in_candidate_reason(
        tr=short_trade,
        pnl_rate=-1.5,
        current_price=9_850,
        active_stop_loss=9_600,
    ) is None


def test_default_exit_thresholds_are_horizon_aware(monkeypatch) -> None:
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_STOP_LOSS_PCT_SHORT", -3.0)
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_STOP_LOSS_PCT_MID", -4.0)
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_STOP_LOSS_PCT_LONG", -6.0)
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_TAKE_PROFIT_PCT_SHORT", 5.0)
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_TAKE_PROFIT_PCT_MID", 8.0)
    monkeypatch.setattr("scheduler.scheduler.settings.DEFAULT_TAKE_PROFIT_PCT_LONG", 12.0)

    assert TradingScheduler._default_stop_loss_pct(TradeHorizon.SHORT) == pytest.approx(-3.0)
    assert TradingScheduler._default_stop_loss_pct(TradeHorizon.MID) == pytest.approx(-4.0)
    assert TradingScheduler._default_stop_loss_pct(TradeHorizon.LONG) == pytest.approx(-6.0)
    assert TradingScheduler._default_take_profit_pct(TradeHorizon.SHORT) == pytest.approx(5.0)
    assert TradingScheduler._default_take_profit_pct(TradeHorizon.MID) == pytest.approx(8.0)
    assert TradingScheduler._default_take_profit_pct(TradeHorizon.LONG) == pytest.approx(12.0)


def test_trailing_profit_guard_waits_for_activation_then_sells_on_drawdown(monkeypatch) -> None:
    scheduler = TradingScheduler()
    trade_result = SimpleNamespace(strategy_type="AGGRESSIVE_SHORT", notes='{"trade_horizon":"SHORT"}')

    monkeypatch.setattr("scheduler.scheduler.settings.POSITION_EXIT_MANAGEMENT_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_GUARD_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_ACTIVATE_PCT_SHORT", 2.0)
    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_DRAWDOWN_PCT_SHORT", 1.0)
    monkeypatch.setattr("scheduler.scheduler.settings.RISK_APPETITE", "CONSERVATIVE")

    should_sell, reason, detail = scheduler._evaluate_trailing_profit_guard(
        symbol="005930",
        avg_buy_price=10_000,
        current_price=10_250,
        pnl_rate=2.5,
        tr=trade_result,
    )
    assert should_sell is False
    assert detail["peak_pnl_rate"] == pytest.approx(2.5)

    should_sell, reason, detail = scheduler._evaluate_trailing_profit_guard(
        symbol="005930",
        avg_buy_price=10_000,
        current_price=10_120,
        pnl_rate=1.2,
        tr=trade_result,
    )
    assert should_sell is True
    assert "트레일링 수익보호" in reason
    assert detail["drawdown_pct"] == pytest.approx(1.3)


def test_trailing_profit_guard_is_wider_for_long_horizon(monkeypatch) -> None:
    scheduler = TradingScheduler()
    trade_result = SimpleNamespace(strategy_type="STABLE_SHORT", notes='{"trade_horizon":"LONG"}')

    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_GUARD_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_ACTIVATE_PCT_LONG", 5.0)
    monkeypatch.setattr("scheduler.scheduler.settings.TRAILING_PROFIT_DRAWDOWN_PCT_LONG", 3.0)
    monkeypatch.setattr("scheduler.scheduler.settings.RISK_APPETITE", "CONSERVATIVE")

    scheduler._evaluate_trailing_profit_guard(
        symbol="005930",
        avg_buy_price=10_000,
        current_price=10_600,
        pnl_rate=6.0,
        tr=trade_result,
    )
    should_sell, _, detail = scheduler._evaluate_trailing_profit_guard(
        symbol="005930",
        avg_buy_price=10_000,
        current_price=10_350,
        pnl_rate=3.5,
        tr=trade_result,
    )

    assert should_sell is False
    assert detail["drawdown_pct"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_scheduler_news_poll_calls_service_with_market_hours(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}
    committed = False
    activity_logged_after_commit = False
    metric_recorded_after_commit = False

    async def fake_poll_sources(_session, *, market_hours: bool, mode: str | None = None):
        observed["market_hours"] = market_hours
        observed["mode"] = mode
        return {
            "created": 1,
            "metric_payload": {
                "status": "SUCCESS",
                "elapsed_ms": 123,
                "item_count": 2,
                "success_count": 1,
                "error_count": 0,
                "detail": {"mode": mode},
            },
            "activity_log": {
                "summary": "뉴스 자동 수집 완료",
                "detail": {"mode": mode},
            },
        }

    async def fake_log_activity_from_summary(summary):
        nonlocal activity_logged_after_commit
        assert committed is True
        activity_logged_after_commit = True
        observed["activity_log"] = summary.get("activity_log")

    async def fake_record_news_poll(**kwargs):
        nonlocal metric_recorded_after_commit
        assert committed is True
        metric_recorded_after_commit = True
        observed["metric"] = kwargs

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            nonlocal committed
            committed = True

    fake_session = FakeSession()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr("services.news_polling_service.news_polling_service.poll_sources", fake_poll_sources)
    monkeypatch.setattr(
        "services.news_polling_service.news_polling_service.log_activity_from_summary",
        fake_log_activity_from_summary,
    )
    monkeypatch.setattr("scheduler.scheduler.observability_service.record_news_poll", fake_record_news_poll)

    await scheduler._news_poll()

    assert observed["market_hours"] is True
    assert observed["mode"] == "AUTO_TRADING"
    assert committed is True
    assert activity_logged_after_commit is True
    assert observed["activity_log"]["summary"] == "뉴스 자동 수집 완료"
    assert metric_recorded_after_commit is True
    assert observed["metric"]["item_count"] == 2


@pytest.mark.asyncio
async def test_scheduler_news_poll_captures_runtime_errors(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def failing_poll_sources(_session, *, market_hours: bool, mode: str | None = None):
        raise RuntimeError("poll exploded")

    async def fake_capture_exception(**kwargs):
        observed.update(kwargs)
        return {"fingerprint": "fp-1"}

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("services.news_polling_service.news_polling_service.poll_sources", failing_poll_sources)
    monkeypatch.setattr("scheduler.scheduler.error_capture_service.capture_exception", fake_capture_exception)

    await scheduler._news_poll(trigger_mode="AUTO_EVENT", trigger_reason="PRICE_SURGE")

    assert observed["component"] == "scheduler"
    assert observed["operation"] == "news_poll"
    assert observed["detail"]["trigger_mode"] == "AUTO_EVENT"
    assert observed["detail"]["trigger_reason"] == "PRICE_SURGE"
    assert observed["detail"]["market_hours"] is False
    assert isinstance(observed["exc"], RuntimeError)


@pytest.mark.asyncio
async def test_scheduler_event_trigger_runs_news_poll_in_auto_event_mode(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def fake_news_poll(*args, **kwargs) -> None:
        observed["mode"] = kwargs.get("trigger_mode")
        observed["reason"] = kwargs.get("trigger_reason")

    class DummyTask:
        pass

    def fake_create_task(coro):
        observed["task_created"] = True
        loop = __import__("asyncio").get_event_loop()
        return loop.create_task(coro)

    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._on_news_trigger_event(Event(
        type=EventType.PRICE_SURGE,
        data={"symbol": "005930"},
        source="test",
    ))
    await __import__("asyncio").sleep(0)

    assert observed["task_created"] is True
    assert observed["mode"] == "AUTO_EVENT"
    assert observed["reason"] == "PRICE_SURGE"


@pytest.mark.asyncio
async def test_scheduler_event_trigger_respects_global_cooldown(monkeypatch) -> None:
    scheduler = TradingScheduler()
    calls: list[str] = []

    async def fake_news_poll(*args, **kwargs) -> None:
        calls.append(kwargs.get("trigger_reason") or "")

    monkeypatch.setattr("scheduler.scheduler.settings.NEWS_POLL_ENABLED", True)
    monkeypatch.setattr(scheduler, "_news_poll", fake_news_poll)

    await scheduler._on_news_trigger_event(Event(
        type=EventType.PRICE_SURGE,
        data={"symbol": "005930"},
        source="test",
    ))
    await __import__("asyncio").sleep(0)
    await scheduler._on_news_trigger_event(Event(
        type=EventType.PRICE_DROP,
        data={"symbol": "005930"},
        source="test",
    ))
    await __import__("asyncio").sleep(0)

    assert calls == ["PRICE_SURGE"]


@pytest.mark.asyncio
async def test_scheduler_observability_maintenance_records_success_metric(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def fake_run_maintenance():
        return {
            "resource_rollups_created": 2,
            "execution_rollups_created": 3,
            "deleted_resource_rows": 4,
            "deleted_execution_rows": 1,
        }

    async def fake_record_execution_metric(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(
        "scheduler.scheduler.observability_maintenance_service.run_maintenance",
        fake_run_maintenance,
    )
    monkeypatch.setattr(
        "scheduler.scheduler.observability_service.record_execution_metric",
        fake_record_execution_metric,
    )

    await scheduler._observability_maintenance()

    assert observed["metric_type"] == "JOB"
    assert observed["metric_name"] == "OBSERVABILITY_MAINTENANCE"
    assert observed["status"] == "SUCCESS"
    assert observed["detail"]["resource_rollups_created"] == 2


@pytest.mark.asyncio
async def test_scheduler_observability_maintenance_records_error_metric(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def fake_run_maintenance():
        raise RuntimeError("maintenance failed")

    async def fake_record_execution_metric(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(
        "scheduler.scheduler.observability_maintenance_service.run_maintenance",
        fake_run_maintenance,
    )
    monkeypatch.setattr(
        "scheduler.scheduler.observability_service.record_execution_metric",
        fake_record_execution_metric,
    )

    with pytest.raises(RuntimeError):
        await scheduler._observability_maintenance()

    assert observed["metric_name"] == "OBSERVABILITY_MAINTENANCE"
    assert observed["status"] == "ERROR"


@pytest.mark.asyncio
async def test_scheduler_forward_return_label_records_success_metric(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def fake_run_once():
        return {"labeled": 2, "waiting_data": 1}

    async def fake_record_execution_metric(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(
        "scheduler.scheduler.forward_return_label_job.run_once",
        fake_run_once,
    )
    monkeypatch.setattr(
        "scheduler.scheduler.observability_service.record_execution_metric",
        fake_record_execution_metric,
    )

    await scheduler._forward_return_label()

    assert observed["metric_type"] == "JOB"
    assert observed["metric_name"] == "FORWARD_RETURN_LABEL"
    assert observed["status"] == "SUCCESS"
    assert observed["detail"]["labeled"] == 2


@pytest.mark.asyncio
async def test_scheduler_forward_return_label_records_error_metric(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}

    async def fake_run_once():
        raise RuntimeError("label failed")

    async def fake_record_execution_metric(**kwargs):
        observed.update(kwargs)

    monkeypatch.setattr(
        "scheduler.scheduler.forward_return_label_job.run_once",
        fake_run_once,
    )
    monkeypatch.setattr(
        "scheduler.scheduler.observability_service.record_execution_metric",
        fake_record_execution_metric,
    )

    with pytest.raises(RuntimeError):
        await scheduler._forward_return_label()

    assert observed["metric_name"] == "FORWARD_RETURN_LABEL"
    assert observed["status"] == "ERROR"


@pytest.mark.asyncio
async def test_scheduler_account_equity_snapshot_delegates_to_service(monkeypatch) -> None:
    scheduler = TradingScheduler()
    observed = {}
    backfill_called = False

    async def fake_capture_and_record_current(**kwargs):
        observed.update(kwargs)
        return {"ok": True}

    async def fake_backfill_missing_open_buys_from_holdings():
        nonlocal backfill_called
        backfill_called = True
        return {"provider": "KIWOOM", "backfilled": 0, "skipped": 0}

    monkeypatch.setattr(
        "scheduler.scheduler.account_equity_service.capture_and_record_current",
        fake_capture_and_record_current,
    )
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job._backfill_missing_open_buys_from_holdings",
        fake_backfill_missing_open_buys_from_holdings,
    )

    await scheduler._account_equity_snapshot()

    assert observed["session_phase"] == "INTRADAY"
    assert observed["detail"]["reason"] == "scheduler_interval"
    assert backfill_called is True


@pytest.mark.asyncio
async def test_pre_market_skips_on_holiday_and_logs_reason(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.get_holiday_name", lambda: "신정")
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._pre_market()

    assert logs == ["🏖️ 오늘은 휴장일 (신정) — 매매 스킵"]


@pytest.mark.asyncio
async def test_pre_market_restores_swing_context_and_applies_trading_rules(monkeypatch) -> None:
    from agent.trading_agent import trading_agent as global_trading_agent

    scheduler = TradingScheduler()
    logs: list[str] = []
    overnight_checks: list[str] = []
    strategy_rule_calls: list[tuple] = []
    risk_rule_calls: list[tuple] = []
    recorded_rule_ids: list[list[str]] = []
    expired_calls: list[str] = []

    class FakeRule:
        def __init__(self, rule_id: str, param_name: str, param_value: str) -> None:
            self.id = rule_id
            self.param_name = param_name
            self.param_value = param_value

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_by_date(self, _date):
            return SimpleNamespace(lessons_learned="손절은 더 빠르게, 익절은 분할")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_get_balance():
        return SimpleNamespace(total_asset=12_345_678)

    async def fake_check_overnight_positions() -> None:
        overnight_checks.append("called")

    active_rules = {
        "rules": [
            FakeRule("rule-1", "max_position_size", "0.2"),
            FakeRule("rule-2", "stop_loss", "-0.03"),
        ]
    }

    async def fake_load_active_rules():
        return active_rules

    def fake_apply_to_strategies(strategies, loaded_rules) -> None:
        strategy_rule_calls.append((strategies, loaded_rules))

    def fake_apply_to_risk_manager(risk_manager_obj, loaded_rules) -> None:
        risk_rule_calls.append((risk_manager_obj, loaded_rules))

    async def fake_record_application(rule_ids: list[str]) -> None:
        recorded_rule_ids.append(rule_ids)

    async def fake_expire_old_rules() -> int:
        expired_calls.append("called")
        return 2

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("trading.account_manager.account_manager.get_balance", fake_get_balance)
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.daily_report_repository.DailyReportRepository", FakeRepo)
    monkeypatch.setattr(scheduler, "_check_overnight_positions", fake_check_overnight_positions)
    monkeypatch.setattr("analysis.feedback.trading_rules.trading_rule_engine.load_active_rules", fake_load_active_rules)
    monkeypatch.setattr(
        "analysis.feedback.trading_rules.trading_rule_engine.apply_to_strategies",
        fake_apply_to_strategies,
    )
    monkeypatch.setattr(
        "analysis.feedback.trading_rules.trading_rule_engine.apply_to_risk_manager",
        fake_apply_to_risk_manager,
    )
    monkeypatch.setattr(
        "analysis.feedback.trading_rules.trading_rule_engine.record_application",
        fake_record_application,
    )
    monkeypatch.setattr(
        "analysis.feedback.trading_rules.trading_rule_engine.expire_old_rules",
        fake_expire_old_rules,
    )
    monkeypatch.setattr("agent.trading_agent.trading_agent._daily_start_balance", 0.0)
    monkeypatch.setattr("agent.trading_agent.trading_agent._active_trading_rules", {})
    monkeypatch.setattr("agent.trading_agent.trading_agent.strategies", {"STABLE_SHORT": object()})

    await scheduler._pre_market()

    assert overnight_checks == ["called"]
    assert strategy_rule_calls and strategy_rule_calls[0][1] == active_rules
    assert risk_rule_calls and risk_rule_calls[0][1] == active_rules
    assert recorded_rule_ids == [["rule-1", "rule-2"]]
    assert expired_calls == ["called"]
    assert any("어제 리뷰 피드백" in message for message in logs)
    assert any("트레이딩 규칙 2건 적용" in message for message in logs)
    assert global_trading_agent._daily_start_balance == 12_345_678
    assert global_trading_agent._active_trading_rules == active_rules


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
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)

    await scheduler._market_open_scan()

    assert observed == ["run_cycle", "get_holdings"]


@pytest.mark.asyncio
async def test_market_open_scan_skips_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False
    logs: list[tuple] = []

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)

    await scheduler._market_open_scan()

    assert run_cycle_called is False
    assert logs[0][0][1] == ActivityPhase.SKIP


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
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
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
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_HOUR", 14)
    monkeypatch.setattr("scheduler.scheduler.settings.BUY_CUTOFF_MINUTE", 30)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 30))
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._intraday_rescan()

    assert run_cycle_called is False


@pytest.mark.asyncio
async def test_intraday_rescan_skips_when_trading_disabled(monkeypatch) -> None:
    scheduler = TradingScheduler()
    run_cycle_called = False
    logs: list[tuple] = []

    async def fake_run_cycle() -> dict:
        nonlocal run_cycle_called
        run_cycle_called = True
        return {}

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._intraday_rescan()

    assert run_cycle_called is False
    assert logs[0][0][1] == ActivityPhase.SKIP


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
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 11, 0))
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent.run_cycle", fake_run_cycle)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("realtime.stream_manager.stream_manager.update_subscriptions", fake_update_subscriptions)

    await scheduler._intraday_rescan()

    assert observed[0:2] == ["run_cycle", "get_holdings"]
    assert [(item.symbol, item.market, item.priority.name) for item in observed[2]] == [
        ("005930", "KRX", "HELD_POSITION"),
        ("000660", "KRX", "NEW_CANDIDATE"),
        ("035720", "KRX", "HELD_POSITION"),
    ]


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
async def test_holdings_check_returns_early_outside_automated_trading_session(monkeypatch) -> None:
    scheduler = TradingScheduler()
    fetched_holdings = False

    async def fake_get_holdings() -> list:
        nonlocal fetched_holdings
        fetched_holdings = True
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda: False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._holdings_check()

    assert fetched_holdings is False


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
async def test_holdings_check_restores_persisted_ai_exit_thresholds_after_restart(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    restored: list[tuple[str, dict]] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    trade_result = SimpleNamespace(
        stock_symbol="005930",
        strategy_type="STABLE_SHORT",
        ai_stop_loss_price=68_000,
        ai_target_price=75_000,
        notes='{"trade_horizon":"MID","active_trailing_stop_pct":4.5}',
    )
    threshold_state = {
        "005930": SimpleNamespace(stop_loss=0.0, take_profit=0.0, trailing_stop_pct=0.0)
    }

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [trade_result]

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_fetch_current_price(_symbol: str) -> float:
        return 71_000

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    def fake_get_thresholds(symbol: str):
        return threshold_state[symbol]

    def fake_set_thresholds(symbol: str, **kwargs) -> None:
        restored.append((symbol, kwargs))
        th = threshold_state[symbol]
        for key, value in kwargs.items():
            setattr(th, key, value)

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda *_args: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr(scheduler, "_fetch_current_price", fake_fetch_current_price)
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("realtime.event_detector.event_detector.get_thresholds", fake_get_thresholds)
    monkeypatch.setattr("realtime.event_detector.event_detector.set_thresholds", fake_set_thresholds)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._holdings_check()

    assert restored == [
        ("005930", {"stop_loss": 68_000.0, "take_profit": 75_000.0, "trailing_stop_pct": 4.5})
    ]
    assert threshold_state["005930"].stop_loss == 68_000.0
    assert threshold_state["005930"].take_profit == 75_000.0
    assert any("AI 손절/익절 임계값 복원" in message for message in logs)
    assert all("AI 손절/익절 미설정" not in message for message in logs)


@pytest.mark.asyncio
async def test_holdings_check_executes_sell_and_triggers_rescan(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    log_calls: list[tuple[tuple, dict]] = []
    removed_levels: list[str] = []
    confirmed_orders: list[dict] = []
    released: list[str] = []
    created_tasks: list[object] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_current_price(_symbol: str):
        return CurrentPrice(
            symbol="005930",
            market=Market.KRX,
            price=73_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

        async def place_order(self, request):
            return OrderResult(success=True, order_id="SELL-HOLDING", message="ok")

    async def fake_log(*args, **kwargs) -> None:
        log_calls.append((args, kwargs))
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-adapter"

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-1"

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_000, take_profit=72_000),
    )
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._holdings_check()

    assert confirmed_orders[0]["order_id"] == "SELL-HOLDING"
    assert confirmed_orders[0]["exit_reason"] == "HOLDINGS_CHECK"
    assert confirmed_orders[0]["pending_record_id"] == "pending-sell-1"
    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert any(
        getattr(task, "cr_code", None) and task.cr_code.co_name == "_trigger_rescan_after_sell"
        for task in created_tasks
    )
    assert any("보유점검 매도" in message for message in logs)
    assert any("체결 확인 완료" in message for message in logs)


@pytest.mark.asyncio
async def test_holdings_check_does_not_complete_when_sell_confirmation_fails(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    removed_levels: list[str] = []
    released: list[str] = []
    rescans: list[bool] = []
    confirmed_orders: list[dict] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_get_holdings() -> list:
        return [holding]

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return CurrentPrice(
                symbol=symbol,
                market=market,
                price=73_000,
                change=0.0,
                change_rate=0.0,
                volume=0,
                timestamp=__import__("datetime").datetime.now(),
            )

        async def place_order(self, request):
            return OrderResult(success=True, order_id="SELL-HOLDING-FAIL", message="ok")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-fail"

    async def fake_confirm_and_record(**kwargs) -> bool:
        confirmed_orders.append(kwargs)
        return False

    async def fake_trigger_rescan_after_sell() -> None:
        rescans.append(True)

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_000, take_profit=72_000),
    )
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr(scheduler, "_trigger_rescan_after_sell", fake_trigger_rescan_after_sell)

    await scheduler._holdings_check()
    await asyncio.sleep(0)

    assert confirmed_orders[0]["order_id"] == "SELL-HOLDING-FAIL"
    assert removed_levels == []
    assert released == ["005930"]
    assert rescans == []
    assert any("체결 확인 실패" in message for message in logs)
    assert not any("보유점검 매도 완료" in message for message in logs)


@pytest.mark.asyncio
async def test_holdings_check_logs_disabled_sell_when_trading_is_off(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_current_price(_symbol: str):
        return CurrentPrice(
            symbol="005930",
            market=Market.KRX,
            price=73_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_000, take_profit=72_000),
    )
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)

    await scheduler._holdings_check()

    assert "TRADING_ENABLED=false" in logs[0]


@pytest.mark.asyncio
async def test_holdings_check_logs_when_sell_is_already_in_progress(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_current_price(_symbol: str):
        return CurrentPrice(
            symbol="005930",
            market=Market.KRX,
            price=73_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return False

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_000, take_profit=72_000),
    )
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)

    await scheduler._holdings_check()

    assert "이미 매도 진행 중" in logs[0]


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
    assert "보유 심사 불필요" in logs[0][0][2]


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
async def test_force_liquidation_does_not_rescan_after_successful_swing_sell(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    log_calls: list[tuple[tuple, dict]] = []
    removed_levels: list[str] = []
    created_tasks: list[object] = []
    confirmed_orders: list[dict] = []
    released: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=3, pnl_rate=1.5, current_price=71_000)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_pending_orders() -> list:
        return []

    async def fake_smart_liquidation(holdings):
        return holdings, []

    async def fake_place_order(**kwargs):
        return None

    class FakeBrokerAdapter:
        async def place_order(self, request):
            return OrderResult(success=True, order_id="SELL-1", message="ok")

    async def fake_log(*args, **kwargs) -> None:
        log_calls.append((args, kwargs))
        logs.append(args[2])

    async def fake_acquire_sell(symbol: str) -> bool:
        return True

    def fake_release_sell(symbol: str) -> None:
        released.append(symbol)

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-gap"

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-1"

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
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", fake_release_sell)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr(scheduler, "_trigger_rescan_after_sell", fake_trigger_rescan_after_sell)
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._force_liquidation()

    assert confirmed_orders[0]["order_id"] == "SELL-1"
    assert confirmed_orders[0]["exit_reason"] == "CLOSE_REVIEW"
    assert confirmed_orders[0]["pending_record_id"] == "pending-sell-1"
    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert created_tasks == []
    assert any("주문 접수: 1건 매도" in message for message in logs)


@pytest.mark.asyncio
async def test_smart_liquidation_holds_for_review_when_no_holdings_data(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=3)

    async def fake_collect_holdings_data(_sellable):
        return [], {}, [{"holding": holding, "reason": "현재가 조회 실패"}]

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == []
    assert to_hold == [holding]


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
async def test_collect_holdings_data_marks_symbol_for_review_when_price_lookup_fails(monkeypatch) -> None:
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
        raise RuntimeError("price lookup failed")

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())

    holdings_data, holdings_map, review_required = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert review_required[0]["holding"] == holding
    assert review_required[0]["reason_code"] == "PRICE_LOOKUP_FAILED"


@pytest.mark.asyncio
async def test_collect_holdings_data_builds_prompt_payload_for_valid_holding(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="A005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    trade_result = SimpleNamespace(
        stock_name="삼성전자",
        ai_confidence=0.83,
        ai_target_price=75_000,
        ai_stop_loss_price=68_000,
        strategy_type="STABLE_SHORT",
    )
    observed: dict[str, str] = {}

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_open_buy(self, symbol: str):
            observed["repo_symbol"] = symbol
            return trade_result

    async def fake_get_current_price(_symbol: str):
        observed["price_symbol"] = _symbol
        return CurrentPrice(
            symbol=_symbol,
            market=Market.KRX,
            price=73_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    async def fake_news_context(_session, *, symbol: str, name: str):
        observed["news_symbol"] = symbol
        observed["news_name"] = name
        return {
            "news_context_available": True,
            "news_context_tone": "POSITIVE_SUPPORT",
            "news_context_negative_pressure": 0.0,
            "news_context_item_count": 1,
            "news_context_source_codes": ["DART"],
            "news_context_items": [{"source_code": "DART", "title": "공급계약"}],
            "news_context_prompt": "### 최근 뉴스 보조 컨텍스트\n- [POSITIVE] 공급계약",
        }

    monkeypatch.setattr(scheduler, "_build_holding_news_context", fake_news_context)
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: (
            observed.update({"threshold_symbol": _symbol})
            or SimpleNamespace(stop_loss=68_500, take_profit=74_500)
        ),
    )
    monkeypatch.setattr("strategy.holding_policy._calc_hold_days", lambda _tr: 2)
    monkeypatch.setattr("strategy.holding_policy._get_max_hold_days", lambda _strategy, _settings: 5)

    holdings_data, holdings_map, review_required = await scheduler._collect_holdings_data([holding])

    assert review_required == []
    assert holdings_map["005930"] == (holding, trade_result, 73_000)
    assert observed == {
        "price_symbol": "005930",
        "repo_symbol": "005930",
        "threshold_symbol": "005930",
        "news_symbol": "005930",
        "news_name": "삼성전자",
    }
    assert holdings_data[0]["symbol"] == "005930"
    assert holdings_data[0]["stock_name"] == "삼성전자"
    assert round(holdings_data[0]["pnl_rate"], 2) == round((73_000 - 70_000) / 70_000 * 100, 2)
    assert holdings_data[0]["active_stop_loss"] == 68_500
    assert holdings_data[0]["active_take_profit"] == 74_500
    assert holdings_data[0]["news_context_available"] is True
    assert holdings_data[0]["news_context_tone"] == "POSITIVE_SUPPORT"
    assert holdings_data[0]["news_context_item_count"] == 1
    assert "공급계약" in holdings_data[0]["news_context_prompt"]


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

    async def fake_get_pending_orders() -> list:
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
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

    async def fake_get_pending_orders() -> list:
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
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
    confirmed_orders: list[dict] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, pnl_rate=-1.3, current_price=69_500)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_smart_liquidation(_sellable):
        return [holding], []

    class FakeBrokerAdapter:
        async def place_order(self, request):
            place_order_calls.append(request.symbol)
            if len(place_order_calls) == 1:
                return OrderResult(success=False, order_id=None, message="temporary fail")
            return OrderResult(success=True, order_id="SELL-RETRY", message="ok")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_get_pending_orders() -> list:
        return []

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-retry"

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert place_order_calls == ["005930", "005930"]
    assert sleep_calls == [5]
    assert confirmed_orders == [{
        "symbol": "005930",
        "side": "SELL",
        "order_id": "SELL-RETRY",
        "quantity": 2,
        "expected_price": 69_500,
        "exit_reason": "CLOSE_REVIEW",
        "pending_record_id": "pending-sell-retry",
    }]
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

    async def fake_get_pending_orders() -> list:
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fake_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert any("AI 보유 심사 주문 접수: 0건 매도" in message for message in logs)


@pytest.mark.asyncio
async def test_force_liquidation_subtracts_pending_sell_quantity(monkeypatch) -> None:
    scheduler = TradingScheduler()
    place_calls: list[tuple[str, int]] = []
    holding = SimpleNamespace(symbol="215790", name="이노인스트루먼트", quantity=100, pnl_rate=-3.2, current_price=1450)
    pending_order = SimpleNamespace(symbol="215790", side="매도", remaining_qty=60)

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_pending_orders() -> list:
        return [pending_order]

    async def fake_place_market_sell(symbol: str, quantity: int, market=None):
        place_calls.append((symbol, quantity))
        return SimpleNamespace(success=True, order_id="SELL-1", error=None)

    async def fake_log(*args, **kwargs):
        return None

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
    monkeypatch.setattr(scheduler, "_place_market_sell", fake_place_market_sell)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", lambda **kwargs: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)

    await scheduler._force_liquidation()

    assert place_calls == [("215790", 40)]


@pytest.mark.asyncio
async def test_collect_holdings_data_marks_symbol_for_review_when_trade_result_is_missing(monkeypatch) -> None:
    scheduler = TradingScheduler()
    holding = SimpleNamespace(symbol="A005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    metrics: list[dict] = []

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

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return SimpleNamespace(price=73_000)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())

    async def fake_record_execution_metric(**kwargs):
        metrics.append(kwargs)

    monkeypatch.setattr(
        "scheduler.scheduler.observability_service.record_execution_metric",
        fake_record_execution_metric,
    )

    holdings_data, holdings_map, review_required = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert review_required[0]["holding"] == holding
    assert review_required[0]["reason_code"] == "TRADE_RESULT_MISSING"
    assert metrics[0]["metric_type"] == "HOLDINGS_REVIEW"
    assert metrics[0]["metric_name"] == "REVIEW_REQUIRED"
    assert metrics[0]["status"] == "REVIEW_REQUIRED"
    assert metrics[0]["symbol"] == "005930"
    assert metrics[0]["detail"]["source_symbol"] == "A005930"
    assert metrics[0]["detail"]["reason_code"] == "TRADE_RESULT_MISSING"


@pytest.mark.asyncio
async def test_collect_holdings_data_marks_symbol_for_review_on_repository_error(monkeypatch) -> None:
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

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return SimpleNamespace(price=73_000)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())

    holdings_data, holdings_map, review_required = await scheduler._collect_holdings_data([holding])

    assert holdings_data == []
    assert holdings_map == {}
    assert review_required[0]["holding"] == holding
    assert review_required[0]["reason_code"] == "HOLDING_DATA_ERROR"


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
async def test_smart_liquidation_treats_llm_extend_as_hold_and_updates_notes(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    trade_result = SimpleNamespace(
        stock_name="삼성전자",
        strategy_type="STABLE_SHORT",
        ai_confidence=0.82,
        ai_target_price=82_000,
        ai_stop_loss_price=66_000,
        entry_at=None,
        created_at=None,
        notes='{"trade_horizon":"MID"}',
    )

    async def fake_collect_holdings_data(_sellable):
        return (
            [{
                "symbol": "005930",
                "stock_name": "삼성전자",
                "strategy_type": "STABLE_SHORT",
                "pnl_rate": 4.2,
                "hold_days": 15,
                "max_hold_days": 15,
                "confidence": 0.82,
                "target_price": 82_000,
                "stop_loss_price": 66_000,
            }],
            {"005930": (holding, trade_result, 73_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"EXTEND","reason":"추세와 목표가 여유 유지","confidence":0.81}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_apply_extension(*, symbol, trade_result, decision, hold_days):
        from strategy.holding_policy import apply_hold_extension_decision

        update = apply_hold_extension_decision(
            trade_result,
            decision=decision,
            hold_days=hold_days,
            config=SimpleNamespace(
                MAX_HOLD_DAYS_SHORT=5,
                MAX_HOLD_DAYS_MID=15,
                MAX_HOLD_DAYS_LONG=30,
                MAX_HOLD_EXTENSION_DAYS=15,
                MAX_HOLD_TOTAL_DAYS=60,
                MAX_HOLD_DAYS_STABLE=15,
                MAX_HOLD_DAYS_AGGRESSIVE=10,
            ),
        )
        if update:
            trade_result.notes = update.updated_notes
        return update

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr(scheduler, "_apply_hold_extension_decision", fake_apply_extension)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {"decisions": [{"symbol": "005930", "action": "EXTEND", "reason": "추세와 목표가 여유 유지", "confidence": 0.81}]},
    )
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULL")

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    payload = json.loads(trade_result.notes)
    assert to_sell == []
    assert to_hold == [holding]
    assert payload["trade_horizon"] == "LONG"
    assert payload["hold_extension_until_days"] == 30
    assert payload["hold_extension_count"] == 1
    assert "EXTEND→HOLD" in logs[0]
    assert "다음 심사 30일" in logs[0]


@pytest.mark.asyncio
async def test_smart_liquidation_rejects_extend_when_hard_exit_condition_exists(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2, avg_buy_price=70_000)
    trade_result = SimpleNamespace(
        stock_name="삼성전자",
        strategy_type="STABLE_SHORT",
        ai_confidence=0.82,
        ai_target_price=73_000,
        ai_stop_loss_price=66_000,
        entry_at=None,
        created_at=None,
        notes='{"trade_horizon":"MID"}',
    )

    async def fake_collect_holdings_data(_sellable):
        return (
            [{
                "symbol": "005930",
                "stock_name": "삼성전자",
                "strategy_type": "STABLE_SHORT",
                "pnl_rate": 4.2,
                "hold_days": 15,
                "max_hold_days": 15,
                "confidence": 0.82,
                "target_price": 73_000,
                "stop_loss_price": 66_000,
            }],
            {"005930": (holding, trade_result, 73_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"EXTEND","reason":"더 상승 가능","confidence":0.81}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fail_apply_extension(**kwargs):
        raise AssertionError("hard reject should not persist extension")

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr(scheduler, "_apply_hold_extension_decision", fail_apply_extension)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {"decisions": [{"symbol": "005930", "action": "EXTEND", "reason": "더 상승 가능", "confidence": 0.81}]},
    )
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULL")

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == [holding]
    assert to_hold == []
    assert "연장 거부" in logs[0]
    assert "목표가" in logs[0]
    assert trade_result.notes == '{"trade_horizon":"MID"}'


@pytest.mark.asyncio
async def test_smart_liquidation_uses_llm_for_loss_policy_sell_candidate(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    decision_events: list[dict] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_name="삼성전자", strategy_type="STABLE_SHORT")

    async def fake_collect_holdings_data(_sellable):
        return (
            [{
                "symbol": "005930",
                "stock_name": "삼성전자",
                "strategy_type": "STABLE_SHORT",
                "pnl_rate": -5.0,
                "hold_days": 1,
                "max_hold_days": 5,
            }],
            {"005930": (holding, trade_result, 95_000)},
            [],
        )

    async def fake_generate_tier1(prompt, system_prompt=None):
        return (
            '{"decisions":[{"symbol":"005930","action":"HOLD","reason":"추세 유지","confidence":0.71}]}',
            "CODEX",
        )

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="smart-liquidation-event-1")

    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("analysis.llm.prompts.overnight_hold.build_overnight_prompt", lambda data, regime: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "services.holdings_precheck_service.evaluate_overnight_hold",
        lambda *args, **kwargs: SimpleNamespace(action="SELL", reason="손실 과대 (-5.0% < -3%) — 손절 수준 도달"),
    )
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("services.decision_event_service.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "RANGE")

    to_sell, to_hold = await scheduler._smart_liquidation([holding])

    assert to_sell == []
    assert to_hold == [holding]
    assert "AI 신뢰도" in logs[0]
    assert decision_events == []


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
        return None

    class FakeBrokerAdapter:
        async def place_order(self, request):
            return OrderResult(success=True, order_id="SELL-REVIEW", message="ok")

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
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
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
async def test_intraday_holdings_review_returns_early_outside_automated_trading_session(monkeypatch) -> None:
    scheduler = TradingScheduler()
    fetched_holdings = False

    async def fake_get_holdings() -> list:
        nonlocal fetched_holdings
        fetched_holdings = True
        return []

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda: False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)

    await scheduler._intraday_holdings_review()

    assert fetched_holdings is False


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
async def test_intraday_holdings_review_executes_partial_sell(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    sell_orders: list[tuple[str, int]] = []
    confirms: list[dict] = []
    created_tasks: list[object] = []
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=10)
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
            '{"decisions":[{"symbol":"005930","action":"PARTIAL_SELL","reason":"급등 후 일부 수익 보호","confidence":0.81,"partial_exit_pct":40}]}',
            "CODEX",
        )

    async def fake_place_market_sell(symbol, quantity):
        sell_orders.append((symbol, quantity))
        return SimpleNamespace(success=True, order_id="S1", error=None)

    async def fake_confirm_and_record(**kwargs):
        confirms.append(kwargs)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    class DummyTask:
        pass

    def fake_create_task(coro):
        created_tasks.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr(scheduler, "_place_market_sell", fake_place_market_sell)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 0))
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(
        "core.json_utils.parse_llm_json",
        lambda text: {
            "decisions": [
                {
                    "symbol": "005930",
                    "action": "PARTIAL_SELL",
                    "reason": "급등 후 일부 수익 보호",
                    "confidence": 0.81,
                    "partial_exit_pct": 40,
                }
            ]
        },
    )
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", lambda _symbol: __import__("asyncio").sleep(0, result=True))
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "강세 유지")
    monkeypatch.setattr("asyncio.create_task", fake_create_task)

    await scheduler._intraday_holdings_review()

    assert sell_orders == [("005930", 4)]
    assert confirms[0]["quantity"] == 4
    assert confirms[0]["exit_reason"] == "PARTIAL_TAKE_PROFIT"
    assert any("PARTIAL_SELL 매도 성공 (4주)" in message for message in logs)


@pytest.mark.asyncio
async def test_intraday_holdings_review_uses_cache_without_llm(monkeypatch) -> None:
    scheduler = TradingScheduler()
    logs: list[str] = []
    thresholds: list[tuple[str, dict]] = []
    skipped_metrics: list[dict] = []
    decision_events: list[dict] = []
    trade_result = SimpleNamespace(ai_stop_loss_price=None, ai_target_price=None, stock_name="삼성전자", strategy_type="STABLE_SHORT")
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
            [{
                "symbol": "005930",
                "stock_name": "삼성전자",
                "strategy_type": "STABLE_SHORT",
                "avg_price": 70_000,
                "current_price": 72_000,
                "pnl_rate": 2.857,
                "quantity": 2,
                "hold_days": 1,
                "max_hold_days": 5,
                "confidence": 0.71,
                "target_price": 74_500,
                "stop_loss_price": 69_000,
                "active_stop_loss": 69_000,
                "active_take_profit": 74_500,
            }],
            {"005930": (holding, trade_result, 72_000)},
            [],
        )

    async def fail_generate_tier1(prompt, system_prompt=None):
        raise AssertionError("LLM should not be called when holdings review cache hits")

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    async def fake_skip_metric(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_record_event(**kwargs):
        decision_events.append(kwargs)
        return SimpleNamespace(id="decision-event-1")

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_automated_trading_session", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_collect_holdings_data", fake_collect_holdings_data)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 13, 30))
    monkeypatch.setattr(
        "services.holdings_precheck_service.holdings_precheck_service.evaluate",
        lambda **kwargs: SimpleNamespace(should_skip_llm=False, action="HOLD", reason="", source="TEST"),
    )
    monkeypatch.setattr(
        "services.holdings_review_cache_service.holdings_review_cache_service.build_key",
        lambda **kwargs: "cache-key",
    )
    monkeypatch.setattr(
        "services.holdings_review_cache_service.holdings_review_cache_service.get",
        lambda key: {
            "action": "HOLD",
            "reason": "상승 추세 유지",
            "confidence": 0.88,
            "adjusted_stop_loss_price": 69_000,
            "adjusted_take_profit_price": 74_500,
        },
    )
    monkeypatch.setattr("analysis.llm.prompts.holdings_review.build_holdings_review_prompt", lambda *args: "prompt")
    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory.generate_tier1", fail_generate_tier1)
    monkeypatch.setattr("realtime.event_detector.event_detector.set_thresholds", lambda symbol, **kwargs: thresholds.append((symbol, kwargs)))
    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("services.ai_skip_metric_service.ai_skip_metric_service.record", fake_skip_metric)
    monkeypatch.setattr("services.decision_event_service.decision_event_service.record_event", fake_record_event)
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_regime", "BULLISH")
    monkeypatch.setattr("agent.trading_agent.trading_agent._market_context", "강세 유지")

    await scheduler._intraday_holdings_review()

    assert thresholds == [("005930", {"stop_loss": 69_000.0, "take_profit": 74_500.0})]
    assert session.flushed == 1
    assert session.committed == 1
    assert any("캐시" in message for message in logs)
    assert any(item["stage"] == "HOLDINGS_REVIEW_CACHE" and item["reason_code"] == "CACHE_HIT" for item in skipped_metrics)
    assert decision_events == [{
        "cycle_id": None,
        "symbol": "005930",
        "stock_name": "삼성전자",
        "market": "KRX",
        "decision_stage": "HOLDINGS_REVIEW",
        "source": "holdings_review_cache",
        "strategy_type": "STABLE_SHORT",
        "tier1_decision": "HOLD",
        "risk_gate_result": "CACHE_HIT",
        "final_action": "HOLD",
        "confidence": 0.88,
        "reference_price": 72_000.0,
        "quantity": 2,
        "provider": "DETERMINISTIC",
        "model": "HOLDINGS_REVIEW_CACHE",
        "status": "RECORDED",
        "reason": "상승 추세 유지",
        "metadata": {
            "ai_skipped": True,
            "reason_code": "CACHE_HIT",
            "source": "holdings_review_cache",
            "pnl_rate": 2.857,
            "hold_days": 1,
            "max_hold_days": 5,
            "news_context_available": None,
            "news_context_tone": None,
            "news_context_negative_pressure": None,
            "news_context_item_count": None,
            "news_context_source_codes": None,
        },
    }]


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
        return CurrentPrice(
            symbol=symbol,
            market=Market.KRX,
            price=48_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
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
        return None

    class FakeBrokerAdapter:
        async def place_order(self, request):
            return OrderResult(success=False, order_id=None, message="broker reject")

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
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
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
    log_calls: list[tuple[tuple, dict]] = []
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
        return CurrentPrice(
            symbol="005930",
            market=Market.KRX,
            price=67_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

        async def place_order(self, request):
            return OrderResult(success=True, order_id="SELL-GAP", message="ok")

    async def fake_log(*args, **kwargs) -> None:
        log_calls.append((args, kwargs))
        logs.append(args[2])

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", released.append)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", removed_levels.append)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr(
        "util.time_util.now_kst",
        lambda: __import__("datetime").datetime(2026, 5, 13, 9, 5),
    )

    await scheduler._check_overnight_gap()

    assert removed_levels == ["005930"]
    assert released == ["005930"]
    assert confirmed_orders[0]["order_id"] == "SELL-GAP"
    assert confirmed_orders[0]["exit_reason"] == "GAP_CHECK"
    order_logs = [call for call in log_calls if call[0][0] == ActivityType.ORDER]
    assert order_logs[0][0][1] == ActivityPhase.COMPLETE
    assert order_logs[0][1]["symbol"] == "005930"
    assert order_logs[0][1]["detail"]["source"] == "GAP_CHECK"
    assert "갭 하락 손절" in logs[-1]


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
        return CurrentPrice(
            symbol="005930",
            market=Market.KRX,
            price=76_000,
            change=0.0,
            change_rate=0.0,
            volume=0,
            timestamp=__import__("datetime").datetime.now(),
        )

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return await fake_get_current_price(symbol)

    async def fake_log(*args, **kwargs) -> None:
        logs.append(args[2])

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", False)
    monkeypatch.setattr(
        "util.time_util.now_kst",
        lambda: __import__("datetime").datetime(2026, 5, 13, 9, 5),
    )

    await scheduler._check_overnight_gap()

    assert "갭 상승 익절" in logs[0]
    assert "TRADING_ENABLED=false" in logs[0]


@pytest.mark.asyncio
async def test_check_overnight_gap_skips_outside_opening_window(monkeypatch) -> None:
    scheduler = TradingScheduler()
    repo_calls = 0
    price_calls = 0
    holding = SimpleNamespace(symbol="005930", name="삼성전자", quantity=2)

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            nonlocal repo_calls
            repo_calls += 1
            return []

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_fetch_current_price(_symbol: str) -> float:
        nonlocal price_calls
        price_calls += 1
        return 70_000.0

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_fetch_current_price", fake_fetch_current_price)
    monkeypatch.setattr(
        "util.time_util.now_kst",
        lambda: __import__("datetime").datetime(2026, 5, 13, 12, 31),
    )

    await scheduler._check_overnight_gap()

    assert repo_calls == 0
    assert price_calls == 0


@pytest.mark.asyncio
async def test_holdings_check_uses_broker_adapter_for_kiwoom_sell_path(monkeypatch) -> None:
    scheduler = TradingScheduler()
    confirmed_orders: list[dict] = []
    adapter_orders: list = []
    holding = SimpleNamespace(symbol="A005930", name="삼성전자", quantity=2, avg_buy_price=70_000)

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return CurrentPrice(
                symbol=symbol,
                market=market,
                price=73_000,
                change=0.0,
                change_rate=0.0,
                volume=0,
                timestamp=__import__("datetime").datetime.now(),
            )

        async def place_order(self, request):
            adapter_orders.append(request)
            return OrderResult(success=True, order_id="SELL-ADAPTER", message="ok")

    async def fake_update_realtime_subscriptions() -> None:
        return None

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-adapter"

    async def fail_get_current_price(_symbol: str):
        raise AssertionError("mcp current price should not be used")

    async def fail_place_order(**kwargs):
        raise AssertionError("mcp place_order should not be used")

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr(scheduler, "_update_realtime_subscriptions", fake_update_realtime_subscriptions)
    monkeypatch.setattr("util.time_util.now_kst", lambda: __import__("datetime").datetime(2026, 4, 2, 14, 0))
    monkeypatch.setattr(
        "realtime.event_detector.event_detector.get_thresholds",
        lambda _symbol: SimpleNamespace(stop_loss=68_000, take_profit=72_000),
    )
    monkeypatch.setattr("scheduler.scheduler.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fail_get_current_price)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fail_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("asyncio.create_task", lambda coro: (coro.close(), object())[1])

    await scheduler._holdings_check()

    assert confirmed_orders[0]["order_id"] == "SELL-ADAPTER"
    assert confirmed_orders[0]["pending_record_id"] == "pending-sell-adapter"
    assert adapter_orders[0].side == OrderSide.SELL
    assert adapter_orders[0].order_type == OrderType.MARKET
    assert adapter_orders[0].market == Market.KRX


@pytest.mark.asyncio
async def test_force_liquidation_uses_broker_adapter_for_kiwoom_sell_path(monkeypatch) -> None:
    scheduler = TradingScheduler()
    confirmed_orders: list[dict] = []
    adapter_orders: list = []
    holding = SimpleNamespace(symbol="A005930", name="삼성전자", quantity=3, pnl_rate=1.5, current_price=71_000)

    class FakeBrokerAdapter:
        async def place_order(self, request):
            adapter_orders.append(request)
            return OrderResult(success=True, order_id="SELL-FORCE", message="ok")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_get_pending_orders() -> list:
        return []

    async def fake_smart_liquidation(holdings):
        return holdings, []

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-gap"

    async def fail_place_order(**kwargs):
        raise AssertionError("mcp place_order should not be used")

    monkeypatch.setattr("scheduler.market_calendar.market_calendar.is_krx_holiday", lambda: False)
    monkeypatch.setattr("scheduler.scheduler.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("scheduler.scheduler.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("trading.account_manager.account_manager.get_pending_orders", fake_get_pending_orders)
    monkeypatch.setattr(scheduler, "_smart_liquidation", fake_smart_liquidation)
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fail_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)
    monkeypatch.setattr(scheduler, "_trigger_rescan_after_sell", lambda: __import__("asyncio").sleep(0))
    monkeypatch.setattr("asyncio.create_task", lambda coro: (coro.close(), object())[1] if hasattr(coro, "close") else object())

    await scheduler._force_liquidation()

    assert confirmed_orders[0]["order_id"] == "SELL-FORCE"
    assert adapter_orders[0].side == OrderSide.SELL
    assert adapter_orders[0].order_type == OrderType.MARKET
    assert adapter_orders[0].market == Market.KRX


@pytest.mark.asyncio
async def test_check_overnight_gap_uses_broker_adapter_for_kiwoom_sell_path(monkeypatch) -> None:
    scheduler = TradingScheduler()
    confirmed_orders: list[dict] = []
    adapter_orders: list = []
    holding = SimpleNamespace(symbol="A005930", name="삼성전자", quantity=2)
    trade_result = SimpleNamespace(stock_symbol="A005930", ai_stop_loss_price=68_000, ai_target_price=75_000)

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

    class FakeBrokerAdapter:
        async def get_current_price(self, symbol, market):
            return CurrentPrice(
                symbol=symbol,
                market=market,
                price=67_000,
                change=0.0,
                change_rate=0.0,
                volume=0,
                timestamp=__import__("datetime").datetime.now(),
            )

        async def place_order(self, request):
            adapter_orders.append(request)
            return OrderResult(success=True, order_id="SELL-GAP-ADAPTER", message="ok")

    async def fake_get_holdings() -> list:
        return [holding]

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_acquire_sell(_symbol: str) -> bool:
        return True

    async def fake_confirm_and_record(**kwargs) -> None:
        confirmed_orders.append(kwargs)

    async def fake_create_pending_record(**kwargs) -> str:
        return "pending-sell-gap"

    async def fail_get_current_price(_symbol: str):
        raise AssertionError("mcp current price should not be used")

    async def fail_place_order(**kwargs):
        raise AssertionError("mcp place_order should not be used")

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager.get_holdings", fake_get_holdings)
    monkeypatch.setattr("scheduler.scheduler.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("scheduler.scheduler.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("trading.mcp_client.mcp_client.get_current_price", fail_get_current_price)
    monkeypatch.setattr("trading.mcp_client.mcp_client.place_order", fail_place_order)
    monkeypatch.setattr("services.activity_logger.activity_logger.log", fake_log)
    monkeypatch.setattr("scheduler.scheduler.settings.TRADING_ENABLED", True)
    monkeypatch.setattr("agent.trading_agent.trading_agent._acquire_sell", fake_acquire_sell)
    monkeypatch.setattr("agent.trading_agent.trading_agent._release_sell", lambda _symbol: None)
    monkeypatch.setattr("realtime.event_detector.event_detector.remove_levels", lambda _symbol: None)
    monkeypatch.setattr("agent.decision_maker.decision_maker._create_pending_record", fake_create_pending_record)
    monkeypatch.setattr("agent.decision_maker.decision_maker.confirm_and_record", fake_confirm_and_record)
    monkeypatch.setattr(
        "util.time_util.now_kst",
        lambda: __import__("datetime").datetime(2026, 5, 13, 9, 5),
    )

    await scheduler._check_overnight_gap()

    assert confirmed_orders[0]["order_id"] == "SELL-GAP-ADAPTER"
    assert confirmed_orders[0]["symbol"] == "005930"
    assert confirmed_orders[0]["pending_record_id"] == "pending-sell-gap"
    assert adapter_orders[0].symbol == "005930"
    assert adapter_orders[0].side == OrderSide.SELL
    assert adapter_orders[0].order_type == OrderType.MARKET
    assert adapter_orders[0].market == Market.KRX
    async def fake_get_pending_orders() -> list:
        return []

    async def fake_get_pending_orders() -> list:
        return []

    async def fake_get_pending_orders() -> list:
        return []
