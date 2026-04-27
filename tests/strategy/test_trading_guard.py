import pytest

from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from strategy.trading_guard import TradingGuard
from tests.conftest import TestAsyncSessionLocal
from util.time_util import now_kst


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_daily_drawdown(monkeypatch):
    guard = TradingGuard()

    async def fake_drawdown(*, portfolio_budget: float) -> float:
        return -3.2

    async def fake_losses() -> int:
        return 1

    async def fake_expectancy(strategy_type: str) -> float | None:
        return 0.1

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.AUTO_RISK_KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)
    monkeypatch.setattr("strategy.trading_guard.settings.TRADING_ENABLED", True)

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert "일손실" in result["reason"]
    assert result["trigger"] == "DAILY_DRAWDOWN"
    assert result["kill_switched"] is True


@pytest.mark.asyncio
async def test_trading_guard_reports_account_equity_drawdown_without_blocking(monkeypatch):
    guard = TradingGuard()

    async def fake_realized_drawdown(*, portfolio_budget: float) -> float:
        return 0.0

    async def fake_account_drawdown() -> dict:
        return {
            "available": True,
            "drawdown_pct": -3.1,
            "asset_delta": -31_000,
            "baseline_total_asset": 1_000_000,
        }

    async def fake_losses() -> int:
        return 0

    async def fake_expectancy(strategy_type: str) -> float | None:
        return 0.1

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_realized_drawdown)
    monkeypatch.setattr(guard, "_get_account_equity_drawdown", fake_account_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "REPORT_ONLY")
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT", 0.5)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is True
    assert result["trigger"] == ""
    assert result["warnings"][0]["trigger"] == "ACCOUNT_EQUITY_DRAWDOWN"
    assert result["warnings"][0]["drawdown_pct"] == pytest.approx(-3.1)


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_account_equity_drawdown(monkeypatch):
    guard = TradingGuard()

    async def fake_realized_drawdown(*, portfolio_budget: float) -> float:
        return 0.0

    async def fake_account_drawdown() -> dict:
        return {
            "available": True,
            "drawdown_pct": -3.1,
            "asset_delta": -31_000,
            "baseline_total_asset": 1_000_000,
        }

    async def fake_losses() -> int:
        return 0

    async def fake_expectancy(strategy_type: str) -> float | None:
        return 0.1

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_realized_drawdown)
    monkeypatch.setattr(guard, "_get_account_equity_drawdown", fake_account_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.AUTO_RISK_KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "KILL_SWITCH")
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT", 0.5)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT", 1.0)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert result["trigger"] == "ACCOUNT_EQUITY_DRAWDOWN"
    assert result["kill_switched"] is True
    assert "계좌 총자산" in result["reason"]


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_before_kill_threshold(monkeypatch):
    guard = TradingGuard()

    async def fake_realized_drawdown(*, portfolio_budget: float) -> float:
        return 0.0

    async def fake_account_drawdown() -> dict:
        return {
            "available": True,
            "drawdown_pct": -0.7,
            "asset_delta": -7_000,
            "baseline_total_asset": 1_000_000,
        }

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_realized_drawdown)
    monkeypatch.setattr(guard, "_get_account_equity_drawdown", fake_account_drawdown)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "KILL_SWITCH")
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT", 0.5)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT", 1.0)

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert result["trigger"] == "ACCOUNT_EQUITY_DRAWDOWN"
    assert result["kill_switched"] is False


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_stale_account_snapshot(monkeypatch):
    guard = TradingGuard()

    async def fake_realized_drawdown(*, portfolio_budget: float) -> float:
        return 0.0

    async def fake_account_drawdown() -> dict:
        return {
            "available": True,
            "drawdown_pct": 0.0,
            "asset_delta": 0.0,
            "baseline_total_asset": 1_000_000,
            "snapshot_freshness_status": "STALE",
            "snapshot_stale_message": "자동매매 가능 세션에서 계좌 스냅샷이 오래되었습니다.",
            "snapshot_stale_blocks_buy": True,
        }

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_realized_drawdown)
    monkeypatch.setattr(guard, "_get_account_equity_drawdown", fake_account_drawdown)
    monkeypatch.setattr("strategy.trading_guard.settings.ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "BLOCK_BUY")

    result = await guard.evaluate_buy_guard(strategy_type="STABLE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert result["trigger"] == "ACCOUNT_EQUITY_DRAWDOWN"
    assert result["kill_switched"] is False
    assert "스냅샷" in result["reason"]


def test_trading_guard_blocks_buy_on_selected_llm_cooldown(monkeypatch):
    guard = TradingGuard()

    monkeypatch.setattr("strategy.trading_guard.settings.BUY_GUARD_LLM_RUNTIME_BLOCK_ENABLED", True)

    class FakeFactory:
        def get_llm_status(self):
            return {
                "tier1": {"provider": "CODEX"},
                "tier2": {"provider": "CODEX"},
                "available_providers": [
                    {
                        "id": "CODEX",
                        "runtime": {
                            "cooldown_active": True,
                            "disabled_for_sec": 121,
                            "last_failure_reason": "Codex CLI timeout (90s)",
                        },
                    }
                ],
            }

    monkeypatch.setattr("analysis.llm.llm_factory.llm_factory", FakeFactory())

    result = guard._evaluate_llm_runtime_health()

    assert result["action"] == "BLOCK"
    assert "CODEX" in result["reason"]
    assert "timeout" in result["reason"]


@pytest.mark.asyncio
async def test_trading_guard_reads_account_equity_drawdown_from_snapshots():
    guard = TradingGuard()
    today = now_kst().date()
    captured_at = now_kst().replace(hour=10, minute=30, second=0, microsecond=0)

    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            session.add(AccountDayBaseline(
                trading_date=today,
                baseline_at=captured_at.replace(hour=9, minute=0),
                baseline_total_asset=1_000_000,
                baseline_cash=300_000,
                baseline_stock_value=700_000,
            ))
            session.add(AccountEquitySnapshot(
                trading_date=today,
                captured_at=captured_at,
                total_asset=970_000,
                cash=250_000,
                stock_value=720_000,
            ))

    drawdown = await guard._get_account_equity_drawdown()

    assert drawdown["available"] is True
    assert drawdown["drawdown_pct"] == pytest.approx(-3.0)
    assert drawdown["asset_delta"] == pytest.approx(-30_000)
    assert drawdown["baseline_total_asset"] == pytest.approx(1_000_000)


@pytest.mark.asyncio
async def test_trading_guard_blocks_buy_on_negative_expectancy(monkeypatch):
    guard = TradingGuard()

    async def fake_drawdown(*, portfolio_budget: float) -> float:
        return -0.3

    async def fake_losses() -> int:
        return 0

    async def fake_expectancy(strategy_type: str) -> float | None:
        return -0.12

    async def fake_account_drawdown() -> dict:
        return {"available": False, "snapshot_stale_blocks_buy": False}

    monkeypatch.setattr(guard, "_get_daily_realized_pnl_pct", fake_drawdown)
    monkeypatch.setattr(guard, "_get_account_equity_drawdown", fake_account_drawdown)
    monkeypatch.setattr(guard, "_get_consecutive_losses", fake_losses)
    monkeypatch.setattr(guard, "_get_strategy_expectancy", fake_expectancy)
    monkeypatch.setattr("strategy.trading_guard.settings.AUTO_RISK_KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_DAILY_DRAWDOWN_PCT", 2.5)
    monkeypatch.setattr("strategy.trading_guard.settings.MAX_CONSECUTIVE_LOSSES", 4)
    monkeypatch.setattr("strategy.trading_guard.settings.MIN_STRATEGY_EXPECTANCY", 0.0)
    monkeypatch.setattr("strategy.trading_guard.settings.TRADING_ENABLED", True)

    result = await guard.evaluate_buy_guard(strategy_type="AGGRESSIVE_SHORT", portfolio_budget=1_000_000)

    assert result["approved"] is False
    assert result["trigger"] == "NEGATIVE_EXPECTANCY"
    assert "기대값" in result["reason"]
