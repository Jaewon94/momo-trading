"""Canonical account PnL summary.

This service keeps realized trade PnL, broker unrealized PnL, and account
asset delta separate so reports do not mix incompatible sources.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from models.trade_result import TradeResult
from util.time_util import now_kst


class PnlTruthService:
    async def build_summary(
        self,
        session: AsyncSession,
        *,
        trading_date: date | None = None,
    ) -> dict:
        target_date = trading_date or now_kst().date()
        realized_pnl, closed_count = await self._fetch_realized_trade_pnl(session, target_date)
        baseline = await self._fetch_baseline(session, target_date)
        snapshot = await self._fetch_latest_snapshot(session, target_date)

        total_asset = float(getattr(snapshot, "total_asset", 0.0) or 0.0) if snapshot else 0.0
        baseline_total_asset = float(getattr(baseline, "baseline_total_asset", 0.0) or 0.0) if baseline else 0.0
        total_asset_delta = total_asset - baseline_total_asset if snapshot and baseline else 0.0
        total_asset_delta_rate = (
            round((total_asset_delta / baseline_total_asset) * 100.0, 2)
            if baseline_total_asset > 0
            else 0.0
        )

        return {
            "trading_date": target_date.isoformat(),
            "sample_status": self._sample_status(closed_count),
            "realized_trade_pnl": float(realized_pnl),
            "closed_trade_count": int(closed_count),
            "unrealized_broker_pnl": float(getattr(snapshot, "total_unrealized_pnl", 0.0) or 0.0) if snapshot else 0.0,
            "unrealized_broker_pnl_rate": float(getattr(snapshot, "total_unrealized_pnl_rate", 0.0) or 0.0) if snapshot else 0.0,
            "total_asset": total_asset,
            "baseline_total_asset": baseline_total_asset,
            "total_asset_delta": float(total_asset_delta),
            "total_asset_delta_rate": total_asset_delta_rate,
            "holding_count": int(getattr(snapshot, "holding_count", 0) or 0) if snapshot else 0,
            "pending_order_count": int(getattr(snapshot, "pending_order_count", 0) or 0) if snapshot else 0,
            "source": {
                "realized_trade_pnl": "trade_results.closed_buy",
                "unrealized_broker_pnl": "account_equity_snapshots.latest",
                "total_asset_delta": "account_day_baselines + account_equity_snapshots.latest",
            },
        }

    async def _fetch_realized_trade_pnl(self, session: AsyncSession, trading_date: date) -> tuple[float, int]:
        stmt = (
            select(func.coalesce(func.sum(TradeResult.pnl), 0.0), func.count(TradeResult.id))
            .where(and_(
                TradeResult.side == "BUY",
                TradeResult.status == "CONFIRMED",
                TradeResult.exit_at.isnot(None),
                func.date(TradeResult.exit_at) == trading_date.isoformat(),
            ))
        )
        realized_pnl, closed_count = (await session.execute(stmt)).one()
        return float(realized_pnl or 0.0), int(closed_count or 0)

    async def _fetch_baseline(self, session: AsyncSession, trading_date: date) -> AccountDayBaseline | None:
        stmt = (
            select(AccountDayBaseline)
            .where(AccountDayBaseline.trading_date == trading_date)
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    async def _fetch_latest_snapshot(self, session: AsyncSession, trading_date: date) -> AccountEquitySnapshot | None:
        stmt = (
            select(AccountEquitySnapshot)
            .where(AccountEquitySnapshot.trading_date == trading_date)
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    def _sample_status(closed_count: int) -> str:
        if closed_count <= 0:
            return "INSUFFICIENT_CLOSED_TRADE_SAMPLE"
        if closed_count < 12:
            return "LOW_CLOSED_TRADE_SAMPLE"
        return "OK"


pnl_truth_service = PnlTruthService()
