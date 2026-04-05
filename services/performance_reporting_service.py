"""성과 검증/리포팅 집계 서비스."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_activity import AgentActivityLog
from models.trade_result import TradeResult


@dataclass
class _TradePoint:
    strategy_type: str
    horizon: str
    pnl: float
    return_pct: float
    exit_at: datetime


class PerformanceReportingService:
    """트레이딩 성과를 수익 검증 관점으로 요약한다."""

    async def build_summary(self, session: AsyncSession, *, days: int = 30) -> dict:
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=max(int(days), 1))

        trades = await self._fetch_closed_trades(session, from_dt=from_dt, to_dt=to_dt)
        risk_counts = await self._fetch_risk_control_counts(session, from_dt=from_dt, to_dt=to_dt)

        overall = self._calc_metrics(trades)
        by_strategy = self._group_metrics(trades, key_fn=lambda item: item.strategy_type or "UNKNOWN")
        by_horizon = self._group_metrics(trades, key_fn=lambda item: item.horizon or "MID")

        return {
            "window": {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "days": max(int(days), 1),
                "trade_count": len(trades),
            },
            "overall": overall,
            "by_strategy": by_strategy,
            "by_horizon": by_horizon,
            "risk_controls": risk_counts,
        }

    async def build_periodic_summary(self, session: AsyncSession, *, period: str = "weekly", size: int = 8) -> dict:
        period_key = (period or "weekly").lower()
        bucket_days = 7 if period_key == "weekly" else 30
        count = max(int(size), 1)
        now = datetime.now()

        buckets = []
        for i in range(count):
            end = now - timedelta(days=bucket_days * i)
            start = end - timedelta(days=bucket_days)
            trades = await self._fetch_closed_trades(session, from_dt=start, to_dt=end)
            buckets.append({
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "metrics": self._calc_metrics(trades),
            })

        return {
            "period": period_key,
            "bucket_days": bucket_days,
            "buckets": list(reversed(buckets)),
        }

    async def _fetch_closed_trades(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> list[_TradePoint]:
        stmt = (
            select(TradeResult)
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.status == "CONFIRMED",
                TradeResult.exit_at.isnot(None),
                TradeResult.exit_at >= from_dt,
                TradeResult.exit_at <= to_dt,
            ))
            .order_by(TradeResult.exit_at.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        items: list[_TradePoint] = []
        for row in rows:
            items.append(_TradePoint(
                strategy_type=str(getattr(row, "strategy_type", "") or ""),
                horizon=self._extract_horizon(row),
                pnl=float(getattr(row, "pnl", 0.0) or 0.0),
                return_pct=float(getattr(row, "return_pct", 0.0) or 0.0),
                exit_at=getattr(row, "exit_at"),
            ))
        return items

    async def _fetch_risk_control_counts(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> dict:
        base = and_(
            AgentActivityLog.created_at >= from_dt,
            AgentActivityLog.created_at <= to_dt,
        )
        cost_gate_stmt = select(func.count(AgentActivityLog.id)).where(and_(
            base,
            AgentActivityLog.activity_type == "RISK_GATE",
            AgentActivityLog.summary.like("%비용 게이트 차단%"),
        ))
        kill_stmt = select(func.count(AgentActivityLog.id)).where(and_(
            base,
            AgentActivityLog.summary.like("%자동 킬스위치%"),
        ))
        return {
            "cost_gate_blocks": int((await session.execute(cost_gate_stmt)).scalar() or 0),
            "kill_switch_blocks": int((await session.execute(kill_stmt)).scalar() or 0),
        }

    def _group_metrics(self, trades: list[_TradePoint], key_fn) -> dict:
        grouped: dict[str, list[_TradePoint]] = defaultdict(list)
        for item in trades:
            grouped[str(key_fn(item))].append(item)
        return {k: self._calc_metrics(v) for k, v in grouped.items()}

    @staticmethod
    def _calc_metrics(trades: list[_TradePoint]) -> dict:
        count = len(trades)
        if count == 0:
            return {
                "trade_count": 0,
                "win_rate": 0.0,
                "expectancy": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "avg_return_pct": 0.0,
                "max_drawdown": 0.0,
            }

        pnls = [t.pnl for t in trades]
        returns = [t.return_pct for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / count
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")

        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)

        return {
            "trade_count": count,
            "win_rate": round(win_rate, 4),
            "expectancy": round(expectancy, 2),
            "profit_factor": round(profit_factor if profit_factor != float("inf") else 999.0, 4),
            "total_pnl": round(sum(pnls), 2),
            "avg_return_pct": round(sum(returns) / len(returns), 4),
            "max_drawdown": round(max_dd, 2),
        }

    @staticmethod
    def _extract_horizon(trade: TradeResult) -> str:
        notes = getattr(trade, "notes", None)
        if notes:
            try:
                parsed = json.loads(notes)
                value = str(parsed.get("trade_horizon", "")).upper().strip()
                if value in {"SHORT", "MID", "LONG"}:
                    return value
            except (TypeError, ValueError):
                pass
        strategy_type = str(getattr(trade, "strategy_type", "")).upper()
        if "AGGRESSIVE" in strategy_type:
            return "SHORT"
        return "MID"


performance_reporting_service = PerformanceReportingService()
