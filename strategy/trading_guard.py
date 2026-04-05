"""자동 리스크 킬스위치 + 전략 기대값 게이트"""
from datetime import datetime, time

from sqlalchemy import and_, select

from analysis.feedback.performance_tracker import PerformanceTracker
from core.config import settings
from core.database import AsyncSessionLocal
from models.trade_result import TradeResult


class TradingGuard:
    """매수 전 계좌/전략 상태를 점검해 과도한 손실 구간을 차단한다."""

    async def evaluate_buy_guard(self, strategy_type: str, portfolio_budget: float) -> dict:
        drawdown_pct = await self._get_daily_realized_pnl_pct(portfolio_budget=portfolio_budget)
        max_drawdown = abs(float(settings.MAX_DAILY_DRAWDOWN_PCT or 0))
        if max_drawdown > 0 and drawdown_pct <= -max_drawdown:
            return self._block("DAILY_DRAWDOWN", f"일손실 한도 초과 ({drawdown_pct:.2f}% <= -{max_drawdown:.2f}%)")

        consecutive_losses = await self._get_consecutive_losses()
        max_losses = int(settings.MAX_CONSECUTIVE_LOSSES or 0)
        if max_losses > 0 and consecutive_losses >= max_losses:
            return self._block("CONSECUTIVE_LOSSES", f"연속 손실 한도 도달 ({consecutive_losses}회)")

        expectancy = await self._get_strategy_expectancy(strategy_type)
        min_expectancy = float(settings.MIN_STRATEGY_EXPECTANCY or 0.0)
        if expectancy is not None and expectancy < min_expectancy:
            return self._block("NEGATIVE_EXPECTANCY", f"전략 기대값 하회 ({expectancy:+.4f} < {min_expectancy:+.4f})")

        return {
            "approved": True,
            "reason": "트레이딩 가드 통과",
            "trigger": "",
            "kill_switched": False,
        }

    @staticmethod
    def _block(trigger: str, reason: str) -> dict:
        if settings.AUTO_RISK_KILL_SWITCH_ENABLED:
            settings.TRADING_ENABLED = False
        return {
            "approved": False,
            "reason": f"자동 킬스위치: {reason}",
            "trigger": trigger,
            "kill_switched": bool(settings.AUTO_RISK_KILL_SWITCH_ENABLED),
        }

    async def _get_daily_realized_pnl_pct(self, *, portfolio_budget: float) -> float:
        if portfolio_budget <= 0:
            return 0.0
        today = datetime.now().date()
        start = datetime.combine(today, time.min)
        end = datetime.combine(today, time.max)

        async with AsyncSessionLocal() as session:
            stmt = (
                select(TradeResult.pnl)
                .where(and_(
                    TradeResult.side == "BUY",
                    TradeResult.status == "CONFIRMED",
                    TradeResult.exit_at.isnot(None),
                    TradeResult.exit_at >= start,
                    TradeResult.exit_at <= end,
                ))
            )
            result = await session.execute(stmt)
            total_realized = sum(float(row[0] or 0.0) for row in result.all())
        return (total_realized / portfolio_budget) * 100

    async def _get_consecutive_losses(self) -> int:
        async with AsyncSessionLocal() as session:
            tracker = PerformanceTracker(session)
            return await tracker.get_consecutive_losses()

    async def _get_strategy_expectancy(self, strategy_type: str) -> float | None:
        if not strategy_type:
            return None

        sample_size = max(int(settings.EXPECTANCY_SAMPLE_SIZE or 0), 1)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(TradeResult.pnl)
                .where(and_(
                    TradeResult.side == "BUY",
                    TradeResult.status == "CONFIRMED",
                    TradeResult.strategy_type == strategy_type,
                    TradeResult.exit_at.isnot(None),
                ))
                .order_by(TradeResult.exit_at.desc())
                .limit(sample_size)
            )
            result = await session.execute(stmt)
            pnls = [float(row[0] or 0.0) for row in result.all()]

        if len(pnls) < sample_size:
            return None

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        loss_rate = 1.0 - win_rate
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        return (win_rate * avg_win) + (loss_rate * avg_loss)


trading_guard = TradingGuard()
