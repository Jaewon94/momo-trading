"""Trade lifecycle integrity checks for post-reset live operation."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from models.trade_result import TradeResult
from services.performance_reporting_service import performance_reporting_service
from services.trade_close_reconciliation_service import trade_close_reconciliation_service
from trading.symbols import normalize_krx_symbol


class TradeLifecycleIntegrityService:
    """Summarizes whether BUY/SELL records are flowing into performance correctly."""

    async def build_report(
        self,
        session: AsyncSession,
        *,
        days: int = 7,
        broker_position_snapshot: dict | None = None,
    ) -> dict:
        window_days = max(int(days or 7), 1)
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=window_days)

        status_counts = await self._fetch_status_counts(session, from_dt=from_dt, to_dt=to_dt)
        open_buy_positions = await self._fetch_open_buy_positions(session)
        open_buy_count = len(open_buy_positions)
        pending_count = await self._count_pending_confirms(session, from_dt=from_dt, to_dt=to_dt)
        failed_count = await self._count_confirm_failed(session, from_dt=from_dt, to_dt=to_dt)
        data_quality = await performance_reporting_service._fetch_closed_trade_data_quality(
            session,
            from_dt=from_dt,
            to_dt=to_dt,
        )
        reset_readiness = await self._fetch_reset_readiness(session)
        close_reconciliation = await trade_close_reconciliation_service.build_dry_run(session, days=window_days)
        unpaired_sell_count = int((close_reconciliation.get("summary") or {}).get("unmatched_sell_count") or 0)
        unmatched_sell_quantity = int((close_reconciliation.get("summary") or {}).get("unmatched_sell_quantity") or 0)
        repairable_sell_count = int((close_reconciliation.get("summary") or {}).get("matched_sell_count") or 0)
        broker_position_check = self._build_broker_position_check(
            open_buy_positions,
            broker_position_snapshot=broker_position_snapshot,
        )

        checks = [
            {
                "key": "account_baseline_seeded",
                "label": "계좌 기준선 생성",
                "status": "OK" if reset_readiness["baseline_count"] > 0 else "WARN",
                "actual": reset_readiness["baseline_count"],
                "target": 1,
            },
            {
                "key": "account_snapshot_seeded",
                "label": "계좌 스냅샷 생성",
                "status": "OK" if reset_readiness["equity_snapshot_count"] > 0 else "WARN",
                "actual": reset_readiness["equity_snapshot_count"],
                "target": 1,
            },
            {
                "key": "pending_confirms",
                "label": "체결 확인 대기",
                "status": "OK" if pending_count == 0 else "WARN",
                "actual": pending_count,
                "target": 0,
            },
            {
                "key": "confirm_failed",
                "label": "체결 확인 실패",
                "status": "OK" if failed_count == 0 else "WARN",
                "actual": failed_count,
                "target": 0,
            },
            {
                "key": "unpaired_sells",
                "label": "BUY lot 미연결 SELL",
                "status": "OK" if unpaired_sell_count == 0 else "FAIL",
                "actual": unpaired_sell_count,
                "target": 0,
                "unmatched_quantity": unmatched_sell_quantity,
            },
            {
                "key": "broker_missing_open_buys",
                "label": "브로커 미보유 열린 BUY",
                "status": broker_position_check["status"],
                "actual": broker_position_check["missing_count"],
                "target": 0,
                "missing_quantity": broker_position_check["missing_quantity"],
                "mismatched_quantity": broker_position_check["mismatched_quantity"],
                "details": broker_position_check["details"],
            },
            {
                "key": "repairable_sells",
                "label": "청산 대사 후보",
                "status": "OK" if repairable_sell_count == 0 else "WARN",
                "actual": repairable_sell_count,
                "target": 0,
            },
            {
                "key": "neutral_closes",
                "label": "중립 종료 제외",
                "status": "OK" if int(data_quality.get("excluded_reconciliation_close_rows") or 0) == 0 else "WARN",
                "actual": int(data_quality.get("excluded_reconciliation_close_rows") or 0),
                "target": 0,
            },
        ]
        overall_status = self._overall_status(checks)
        return {
            "status": overall_status,
            "window": {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "days": window_days,
            },
            "summary": {
                "open_buy_count": open_buy_count,
                "pending_confirm_count": pending_count,
                "confirm_failed_count": failed_count,
                "account_baseline_count": reset_readiness["baseline_count"],
                "account_equity_snapshot_count": reset_readiness["equity_snapshot_count"],
                "latest_account_baseline_at": reset_readiness["latest_baseline_at"],
                "latest_account_snapshot_at": reset_readiness["latest_snapshot_at"],
                "latest_account_total_asset": reset_readiness["latest_total_asset"],
                "closed_trade_rows": int(data_quality.get("closed_trade_rows") or 0),
                "performance_trade_count": int(data_quality.get("performance_trade_count") or 0),
                "excluded_reconciliation_close_rows": int(data_quality.get("excluded_reconciliation_close_rows") or 0),
                "unpaired_sell_count": unpaired_sell_count,
                "unmatched_sell_quantity": unmatched_sell_quantity,
                "repairable_sell_count": repairable_sell_count,
                "broker_position_check_available": broker_position_check["available"],
                "broker_missing_open_buy_count": broker_position_check["missing_count"],
                "broker_missing_open_buy_quantity": broker_position_check["missing_quantity"],
                "broker_mismatched_open_buy_quantity": broker_position_check["mismatched_quantity"],
            },
            "status_counts": status_counts,
            "checks": checks,
            "close_reconciliation_summary": close_reconciliation.get("summary") or {},
        }

    async def _fetch_reset_readiness(self, session: AsyncSession) -> dict:
        baseline_count_stmt = select(func.count(AccountDayBaseline.id))
        snapshot_count_stmt = select(func.count(AccountEquitySnapshot.id))
        latest_baseline_stmt = (
            select(AccountDayBaseline)
            .order_by(AccountDayBaseline.baseline_at.desc())
            .limit(1)
        )
        latest_snapshot_stmt = (
            select(AccountEquitySnapshot)
            .order_by(AccountEquitySnapshot.captured_at.desc())
            .limit(1)
        )
        baseline_count = int((await session.execute(baseline_count_stmt)).scalar() or 0)
        snapshot_count = int((await session.execute(snapshot_count_stmt)).scalar() or 0)
        latest_baseline = (await session.execute(latest_baseline_stmt)).scalar_one_or_none()
        latest_snapshot = (await session.execute(latest_snapshot_stmt)).scalar_one_or_none()
        return {
            "baseline_count": baseline_count,
            "equity_snapshot_count": snapshot_count,
            "latest_baseline_at": latest_baseline.baseline_at.isoformat() if latest_baseline else None,
            "latest_snapshot_at": latest_snapshot.captured_at.isoformat() if latest_snapshot else None,
            "latest_total_asset": float(latest_snapshot.total_asset or 0.0) if latest_snapshot else 0.0,
        }

    async def _fetch_status_counts(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> list[dict]:
        stmt = (
            select(
                TradeResult.side,
                TradeResult.status,
                func.count(TradeResult.id),
                func.coalesce(func.sum(TradeResult.quantity), 0),
                func.coalesce(func.sum(TradeResult.pnl), 0.0),
            )
            .where(or_(
                and_(TradeResult.entry_at.isnot(None), TradeResult.entry_at >= from_dt, TradeResult.entry_at <= to_dt),
                and_(TradeResult.exit_at.isnot(None), TradeResult.exit_at >= from_dt, TradeResult.exit_at <= to_dt),
            ))
            .group_by(TradeResult.side, TradeResult.status)
            .order_by(TradeResult.side.asc(), TradeResult.status.asc())
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "side": str(side or ""),
                "status": str(status or ""),
                "count": int(count or 0),
                "quantity": int(quantity or 0),
                "pnl": round(float(pnl or 0.0), 2),
            }
            for side, status, count, quantity, pnl in rows
        ]

    async def _fetch_open_buy_positions(self, session: AsyncSession) -> list[TradeResult]:
        stmt = select(TradeResult).where(and_(
            TradeResult.side == "BUY",
            TradeResult.status == "CONFIRMED",
            TradeResult.exit_at.is_(None),
        )).order_by(TradeResult.entry_at.asc(), TradeResult.created_at.asc())
        return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    def _build_broker_position_check(
        open_buy_positions: list[TradeResult],
        *,
        broker_position_snapshot: dict | None,
    ) -> dict:
        if broker_position_snapshot is None:
            return {
                "available": False,
                "status": "OK",
                "missing_count": 0,
                "missing_quantity": 0,
                "mismatched_quantity": 0,
                "details": [],
            }

        if broker_position_snapshot.get("error"):
            return {
                "available": False,
                "status": "WARN",
                "missing_count": 0,
                "missing_quantity": 0,
                "mismatched_quantity": 0,
                "details": [{"reason": "broker_snapshot_error", "error": broker_position_snapshot.get("error")}],
            }

        holding_quantities = {
            normalize_krx_symbol(symbol): int(quantity or 0)
            for symbol, quantity in (broker_position_snapshot.get("holding_quantities") or {}).items()
        }
        pending_symbols = {
            normalize_krx_symbol(symbol)
            for symbol in (broker_position_snapshot.get("pending_symbols") or [])
        }

        open_by_symbol: dict[str, dict] = {}
        for trade in open_buy_positions:
            symbol = normalize_krx_symbol(getattr(trade, "stock_symbol", ""))
            if not symbol:
                continue
            bucket = open_by_symbol.setdefault(symbol, {
                "stock_symbol": symbol,
                "stock_name": getattr(trade, "stock_name", symbol),
                "db_open_quantity": 0,
                "broker_holding_quantity": 0,
                "pending_order_exists": False,
                "trade_ids": [],
            })
            bucket["db_open_quantity"] += int(getattr(trade, "quantity", 0) or 0)
            bucket["trade_ids"].append(getattr(trade, "id", None))

        details = []
        missing_count = 0
        missing_quantity = 0
        mismatched_quantity = 0
        for symbol, item in open_by_symbol.items():
            db_qty = int(item["db_open_quantity"] or 0)
            broker_qty = int(holding_quantities.get(symbol, 0) or 0)
            pending = symbol in pending_symbols
            if pending or broker_qty >= db_qty:
                continue
            gap = db_qty - broker_qty
            item["broker_holding_quantity"] = broker_qty
            item["pending_order_exists"] = pending
            item["missing_quantity"] = gap
            item["reason"] = "broker_holding_missing" if broker_qty <= 0 else "broker_holding_quantity_mismatch"
            details.append(item)
            missing_count += 1
            missing_quantity += gap if broker_qty <= 0 else 0
            mismatched_quantity += gap if broker_qty > 0 else 0

        return {
            "available": True,
            "status": "FAIL" if details else "OK",
            "missing_count": missing_count,
            "missing_quantity": missing_quantity,
            "mismatched_quantity": mismatched_quantity,
            "details": details,
        }

    async def _count_pending_confirms(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> int:
        stmt = select(func.count(TradeResult.id)).where(and_(
            TradeResult.status == "PENDING_CONFIRM",
            or_(
                and_(TradeResult.entry_at.isnot(None), TradeResult.entry_at >= from_dt, TradeResult.entry_at <= to_dt),
                and_(TradeResult.exit_at.isnot(None), TradeResult.exit_at >= from_dt, TradeResult.exit_at <= to_dt),
            ),
        ))
        return int((await session.execute(stmt)).scalar() or 0)

    async def _count_confirm_failed(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> int:
        stmt = select(func.count(TradeResult.id)).where(and_(
            TradeResult.status == "CONFIRM_FAILED",
            or_(
                and_(TradeResult.entry_at.isnot(None), TradeResult.entry_at >= from_dt, TradeResult.entry_at <= to_dt),
                and_(TradeResult.exit_at.isnot(None), TradeResult.exit_at >= from_dt, TradeResult.exit_at <= to_dt),
            ),
        ))
        return int((await session.execute(stmt)).scalar() or 0)

    @staticmethod
    def _overall_status(checks: list[dict]) -> str:
        statuses = {str(item.get("status") or "OK") for item in checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "OK"


trade_lifecycle_integrity_service = TradeLifecycleIntegrityService()
