import asyncio
from datetime import datetime
import inspect
from types import SimpleNamespace

import pytest

from analysis.chart_analyzer import ChartAnalysisResult
from agent.trading_agent import TradingAgent
from core.events import Event, EventType
from services.tier1_analysis_cache_service import tier1_analysis_cache_service
from trading.models import BuyingPowerInfo


class StubBrokerAdapter:
    async def get_buying_power(self, symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)


def _kst_time(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 2, hour, minute, 0)


def test_analyze_and_trade_accepts_manual_model_override() -> None:
    params = inspect.signature(TradingAgent._analyze_and_trade).parameters
    assert "manual_model_override" in params


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
async def test_run_cycle_skips_when_runtime_reconfiguration_is_active(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())

    monkeypatch.setattr(
        "agent.trading_agent.runtime_reconfiguration_service.is_reconfiguring",
        lambda: True,
    )

    result = await agent.run_cycle()

    assert result == {"skipped": True, "reason": "runtime_reconfiguring"}


@pytest.mark.asyncio
async def test_run_cycle_dispatches_trading_cycle_during_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        observed["manual_model_override"] = manual_model_override
        return {"mode": "trading"}

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        raise AssertionError("after-hours cycle should not be called during market hours")

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.settings.DAY_TRADING_ONLY", False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

    assert result == {"mode": "trading"}
    assert observed == {"manual_provider_override": "CODEX", "manual_model_override": "gpt-5.4"}


@pytest.mark.asyncio
async def test_run_cycle_dispatches_after_hours_cycle_outside_market_hours(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    observed: dict[str, str | None] = {}

    async def fake_trading_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        raise AssertionError("trading cycle should not be called outside market hours")

    async def fake_after_hours_cycle(*, manual_provider_override: str | None = None, manual_model_override: str | None = None) -> dict:
        observed["manual_provider_override"] = manual_provider_override
        observed["manual_model_override"] = manual_model_override
        return {"mode": "after-hours"}

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: False)
    monkeypatch.setattr(agent, "_run_trading_cycle", fake_trading_cycle)
    monkeypatch.setattr(agent, "_run_after_hours_cycle", fake_after_hours_cycle)

    result = await agent.run_cycle(manual_provider_override="CLAUDE_CODE", manual_model_override="claude-sonnet-4-6")

    assert result == {"mode": "after-hours"}
    assert observed == {"manual_provider_override": "CLAUDE_CODE", "manual_model_override": "claude-sonnet-4-6"}


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

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs) -> dict:
        analyzed_payloads.append(
            {
                "stock_info": dict(stock_info),
                "cycle_id": cycle_id,
                "manual_provider_override": kwargs.get("manual_provider_override"),
                "manual_model_override": kwargs.get("manual_model_override"),
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
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 7))

    result = await agent._run_trading_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

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
    assert analyzed_payloads[0]["manual_model_override"] == "gpt-5.4"
    assert analyzed_payloads[0]["portfolio_snapshot"]["total_asset"] == 2_000_000
    assert resume_calls == ["session-1"]
    assert agent._last_session_id == "ended-session"
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("사이클 완료" in args[2] for args, _kwargs in logs)


@pytest.mark.asyncio
async def test_run_trading_cycle_respects_configured_analysis_concurrency(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    active = 0
    max_active = 0
    entered = 0
    first_entered = asyncio.Event()
    release = asyncio.Event()

    async def fake_publish(_event) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        return None

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
            "selected": [
                {"symbol": "005930", "name": "삼성전자", "market": "KRX", "direction": "BUY"},
                {"symbol": "000660", "name": "SK하이닉스", "market": "KRX", "direction": "BUY"},
                {"symbol": "035420", "name": "NAVER", "market": "KRX", "direction": "BUY"},
            ],
            "market_regime": "RANGE",
        }

    async def fake_build_trading_context() -> str:
        return "trade-context"

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=10, available_cash=1_000_000)

    async def fake_analyze_and_trade(*args, **kwargs) -> dict:
        nonlocal active, max_active, entered
        entered += 1
        active += 1
        max_active = max(max_active, active)
        if entered == 1:
            first_entered.set()
        await release.wait()
        active -= 1
        return {"signal": False, "executed": False}

    monkeypatch.setattr("agent.trading_agent.llm_factory.start_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.pause_session", lambda: None)
    monkeypatch.setattr("agent.trading_agent.llm_factory.end_session", lambda: "session-end")
    monkeypatch.setattr("agent.trading_agent.llm_factory.analysis_concurrency_limit", lambda: 1)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-concurrency")
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
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("util.time_util.now_kst", lambda: _kst_time(9, 10))

    task = asyncio.create_task(agent._run_trading_cycle())
    await first_entered.wait()
    await asyncio.sleep(0.05)

    assert entered == 1
    assert max_active == 1

    release.set()
    result = await task

    assert result["scanned"] == 3
    assert result["analyzed"] == 3
    assert max_active == 1


@pytest.mark.asyncio
async def test_tier1_analysis_retries_once_when_first_response_is_unparseable(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    responses = iter([
        ("not-json", "CODEX"),
        ('{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}', "CODEX"),
    ])
    parse_calls = []

    async def fake_generate_tier1(*args, **kwargs):
        return next(responses)

    def fake_parse_json(text: str):
        parse_calls.append(text)
        if text == "not-json":
            return None
        return {
            "recommendation": "BUY",
            "confidence": 0.7,
            "reason": "ok",
            "target_price": 12000,
            "stop_loss_price": 11000,
        }

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier1", fake_generate_tier1)
    monkeypatch.setattr(agent, "_parse_json", fake_parse_json)
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier1_analysis(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        chart_result=SimpleNamespace(indicators_text="", patterns_text="", trend_text=""),
        price_data={},
    )

    assert result is not None
    assert result["recommendation"] == "BUY"
    assert result["provider"] == "CODEX"
    assert parse_calls == ["not-json", '{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}']


@pytest.mark.asyncio
async def test_tier1_analysis_uses_manual_provider_override_when_present(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_manual(*args, **kwargs):
        captured["provider_override"] = kwargs.get("manual_provider_override")
        captured["model_override"] = kwargs.get("manual_model_override")
        return '{"recommendation":"BUY","confidence":0.7,"reason":"ok","target_price":12000,"stop_loss_price":11000}', "CLAUDE_CODE"

    async def fail_generate_tier1(*args, **kwargs):
        raise AssertionError("generate_tier1 should not be used when manual override is provided")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier1", fail_generate_tier1)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "recommendation": "BUY",
        "confidence": 0.7,
        "reason": "ok",
        "target_price": 12000,
        "stop_loss_price": 11000,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier1_analysis(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        chart_result=SimpleNamespace(indicators_text="", patterns_text="", trend_text=""),
        price_data={},
        manual_provider_override="CLAUDE_CODE",
        manual_model_override="haiku",
    )

    assert result is not None
    assert result["provider"] == "CLAUDE_CODE"
    assert captured == {
        "provider_override": "CLAUDE_CODE",
        "model_override": "haiku",
    }


@pytest.mark.asyncio
async def test_tier2_review_uses_tier_provider_without_manual_override(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_tier2(*args, **kwargs):
        captured["symbol"] = kwargs.get("symbol")
        captured["cycle_id"] = kwargs.get("cycle_id")
        return '{"approved":true,"reason":"ok","suggested_quantity":10}', "CLAUDE_CODE"

    async def fail_generate_manual(*args, **kwargs):
        raise AssertionError("generate_manual should not be used without manual override")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier2", fake_generate_tier2)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fail_generate_manual)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "approved": True,
        "reason": "ok",
        "suggested_quantity": 10,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier2_review(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        strategy_type="STABLE_SHORT",
        tier1_analysis={"recommendation": "BUY"},
        cycle_id="cycle-tier2",
    )

    assert result is not None
    assert result["provider"] == "CLAUDE_CODE"
    assert captured == {
        "symbol": "005930",
        "cycle_id": "cycle-tier2",
    }


@pytest.mark.asyncio
async def test_tier2_review_uses_manual_provider_override_when_present(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    captured = {}

    async def fake_generate_manual(*args, **kwargs):
        captured["provider_override"] = kwargs.get("manual_provider_override")
        captured["model_override"] = kwargs.get("manual_model_override")
        return '{"approved":true,"reason":"ok","suggested_quantity":10}', "CODEX"

    async def fail_generate_tier2(*args, **kwargs):
        raise AssertionError("generate_tier2 should not be used when manual override is provided")

    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_manual", fake_generate_manual)
    monkeypatch.setattr("agent.trading_agent.llm_factory.generate_tier2", fail_generate_tier2)
    monkeypatch.setattr(agent, "_parse_json", lambda _text: {
        "approved": True,
        "reason": "ok",
        "suggested_quantity": 10,
    })
    monkeypatch.setattr(agent, "_validate_llm_prices", lambda parsed, _price: parsed)

    result = await agent._tier2_review(
        symbol="005930",
        name="삼성전자",
        current_price=11500.0,
        strategy_type="STABLE_SHORT",
        tier1_analysis={"recommendation": "BUY"},
        manual_provider_override="CODEX",
        manual_model_override="gpt-5-codex",
    )

    assert result is not None
    assert result["provider"] == "CODEX"
    assert captured == {
        "provider_override": "CODEX",
        "model_override": "gpt-5-codex",
    }


@pytest.mark.asyncio
async def test_analyze_and_trade_forwards_manual_model_override(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    forwarded: dict[str, str | None] = {}

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000, "change": 0, "change_rate": 0, "volume": 1_000}, error=None)
        empty_resp = SimpleNamespace(success=False, data={}, error="no-data")
        return price_resp, empty_resp, empty_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        forwarded["tier1_provider"] = kwargs.get("manual_provider_override")
        forwarded["tier1_model"] = kwargs.get("manual_model_override")
        return {
            "recommendation": "BUY",
            "confidence": 0.81,
            "reason": "테스트",
            "target_price": 72_000,
            "stop_loss_price": 68_000,
            "provider": "CODEX",
        }

    async def fake_tier2_review(*args, **kwargs) -> dict:
        forwarded["tier2_provider"] = kwargs.get("manual_provider_override")
        forwarded["tier2_model"] = kwargs.get("manual_model_override")
        return {"approved": False, "reason": "테스트", "provider": "CODEX"}

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fake_tier2_review)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        "cycle-manual-model",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": ["005930"], "holding_count": 1, "today_trade_count": 0},
        manual_provider_override="CODEX",
        manual_model_override="gpt-5.4",
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert forwarded == {
        "tier1_provider": "CODEX",
        "tier1_model": "gpt-5.4",
        "tier2_provider": "CODEX",
        "tier2_model": "gpt-5.4",
    }


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

    async def fail_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
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
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fail_buying_power)
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
async def test_analyze_and_trade_skips_tier1_when_pre_analysis_gate_blocks_bearish_candidate(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    def fake_chart_analyze(*args, **kwargs) -> ChartAnalysisResult:
        return ChartAnalysisResult(signal_summary={"direction": "BEARISH", "confidence": 0.8})

    async def fail_tier1_analysis(*args, **kwargs):
        raise AssertionError("Tier1 should not be called when PreAnalysisGate blocks the candidate")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr("agent.trading_agent.chart_analyzer.analyze", fake_chart_analyze)
    monkeypatch.setattr(agent, "_tier1_analysis", fail_tier1_analysis)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"},
        "cycle-pre-analysis-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert any("사전 게이트 차단" in args[2] for args, _kwargs in logs)
    assert skipped_metrics == [
        {
            "stage": "PRE_ANALYSIS_GATE",
            "reason_code": "BEARISH_PRE_GATE",
            "skipped_tier": "TIER1",
            "cycle_id": "cycle-pre-analysis-gate",
            "symbol": "005930",
            "detail": {"direction": "BEARISH", "confidence": 0.8},
        }
    ]


@pytest.mark.asyncio
async def test_analyze_and_trade_skips_tier2_when_deterministic_final_gate_blocks_low_confidence(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    agent._active_trading_rules = {"param_overrides": {"ALL": {"min_confidence": 0.7}}}
    agent._market_regime = "SIDEWAYS"

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        return {
            "recommendation": "BUY",
            "confidence": 0.6,
            "reason": "테스트",
            "target_price": 72_000,
            "stop_loss_price": 68_000,
            "provider": "CODEX",
        }

    async def fail_tier2_review(*args, **kwargs):
        raise AssertionError("Tier2 should not be called when DeterministicFinalGate blocks the candidate")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fail_tier2_review)

    result = await agent._analyze_and_trade(
        {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT", "_buying_power": {"success": True, "max_qty": 10}},
        "cycle-deterministic-final-gate",
        portfolio_snapshot={"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0},
        dynamic_limits={"min_buy_quantity": 1},
    )

    assert result == {"symbol": "005930", "signal": False, "executed": False}
    assert any("신뢰도 게이트 차단" in args[2] for args, _kwargs in logs)
    assert skipped_metrics
    assert skipped_metrics[0]["stage"] == "DETERMINISTIC_FINAL_GATE"
    assert skipped_metrics[0]["reason_code"] == "CONFIDENCE_GATE"
    assert skipped_metrics[0]["skipped_tier"] == "TIER2"


@pytest.mark.asyncio
async def test_analyze_and_trade_reuses_tier1_cache_for_same_symbol_conditions(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=StubBrokerAdapter())
    logs = []
    skipped_metrics = []
    tier1_calls = 0
    tier1_analysis_cache_service.clear()

    async def fake_log(*args, **kwargs) -> None:
        logs.append((args, kwargs))

    async def fake_record_ai_skip(**kwargs) -> None:
        skipped_metrics.append(kwargs)

    async def fake_fetch_symbol_market_data(_symbol: str):
        price_resp = SimpleNamespace(success=True, data={"price": 70_000}, error=None)
        daily_resp = SimpleNamespace(
            success=True,
            data={"prices": [{"open": 70_000, "high": 71_000, "low": 69_000, "close": 70_000, "volume": 1_000}]},
            error=None,
        )
        minute_resp = SimpleNamespace(success=False, data={}, error="no-minute")
        return price_resp, daily_resp, minute_resp

    async def fake_tier1_analysis(*args, **kwargs) -> dict:
        nonlocal tier1_calls
        tier1_calls += 1
        return {
            "recommendation": "HOLD",
            "confidence": 0.65,
            "reason": "테스트 캐시",
            "provider": "CODEX",
        }

    async def fail_tier2_review(*args, **kwargs):
        raise AssertionError("Tier2 should not be called for HOLD")

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.ai_skip_metric_service.record", fake_record_ai_skip)
    monkeypatch.setattr(agent, "_fetch_symbol_market_data", fake_fetch_symbol_market_data)
    monkeypatch.setattr(agent, "_tier1_analysis", fake_tier1_analysis)
    monkeypatch.setattr(agent, "_tier2_review", fail_tier2_review)

    payload = {"symbol": "005930", "name": "삼성전자", "strategy_type": "STABLE_SHORT"}
    snapshot = {"cash": 1_000_000, "holding_symbols": [], "holding_count": 0, "today_trade_count": 0}

    first = await agent._analyze_and_trade(payload, "cycle-tier1-cache-1", portfolio_snapshot=snapshot)
    second = await agent._analyze_and_trade(payload, "cycle-tier1-cache-2", portfolio_snapshot=snapshot)

    assert first == {"symbol": "005930", "signal": False, "executed": False}
    assert second == {"symbol": "005930", "signal": False, "executed": False}
    assert tier1_calls == 1
    assert any("Tier1 캐시 재사용" in args[2] for args, _kwargs in logs)
    assert any(item["stage"] == "TIER1_CACHE" and item["reason_code"] == "CACHE_HIT" for item in skipped_metrics)


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

    async def fake_buying_power(_symbol: str, price: float | None = None, market=None) -> BuyingPowerInfo:
        return BuyingPowerInfo(success=True, max_qty=0, available_cash=0)

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
    monkeypatch.setattr(agent._broker_adapter, "get_buying_power", fake_buying_power)
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

    result = await agent._run_after_hours_cycle(manual_provider_override="CODEX", manual_model_override="gpt-5.4")

    assert result == {"mode": "AFTER_HOURS", "review_generated": True}
    assert generate_manual_calls[0]["manual_provider_override"] == "CODEX"
    assert generate_manual_calls[0]["manual_model_override"] == "gpt-5.4"
    assert saved_reports and saved_reports[0][1]["today_review"] == "좋음"
    assert end_session_calls == ["end"]
    assert agent._last_session_id is None
    assert [event.type for event in events] == [EventType.AGENT_CYCLE_START, EventType.AGENT_CYCLE_END]
    assert any("장 마감 리뷰 완료" in args[2] for args, _kwargs in logs)
