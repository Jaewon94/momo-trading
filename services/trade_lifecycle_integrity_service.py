"""Trade lifecycle integrity checks for post-reset live operation."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
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
        pending_confirm_positions = await self._fetch_pending_confirm_positions(session, now=to_dt)
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
            pending_confirm_positions=pending_confirm_positions,
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
                "label": "체결 확인 실패 기록",
                "status": "OK",
                "actual": failed_count,
                "target": 0,
                "note": "CONFIRM_FAILED는 취소/무체결/복구 종료 상태이며 현재 미해결 불일치는 pending/order reconciliation/open BUY 대사에서 판정합니다.",
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
                "key": "broker_untracked_holdings",
                "label": "DB 미반영 브로커 보유",
                "status": broker_position_check["extra_status"],
                "actual": broker_position_check["extra_count"],
                "target": 0,
                "extra_quantity": broker_position_check["extra_quantity"],
                "details": broker_position_check["extra_details"],
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
                "status": "OK",
                "actual": int(data_quality.get("excluded_reconciliation_close_rows") or 0),
                "target": 0,
                "note": "중립 종료 행은 운영 보정 이력이며 성과 계산에서 제외됩니다. 현재 미해결 보유 불일치는 broker_missing_open_buys에서 판정합니다.",
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
                "broker_untracked_holding_count": broker_position_check["extra_count"],
                "broker_untracked_holding_quantity": broker_position_check["extra_quantity"],
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

    async def _fetch_pending_confirm_positions(self, session: AsyncSession, *, now: datetime) -> dict[str, dict]:
        stmt = select(TradeResult).where(TradeResult.status == "PENDING_CONFIRM")
        rows = list((await session.execute(stmt)).scalars().all())
        pending_by_symbol: dict[str, dict] = {}
        for trade in rows:
            symbol = normalize_krx_symbol(getattr(trade, "stock_symbol", ""))
            if not symbol:
                continue
            side = str(getattr(trade, "side", "") or "").upper()
            quantity = int(getattr(trade, "quantity", 0) or 0)
            if quantity <= 0:
                continue
            event_at = (
                getattr(trade, "entry_at", None)
                or getattr(trade, "exit_at", None)
                or getattr(trade, "created_at", None)
            )
            is_fresh = self._is_fresh_pending_confirm(event_at, side=side, now=now)
            bucket = pending_by_symbol.setdefault(symbol, {
                "stock_symbol": symbol,
                "stock_name": getattr(trade, "stock_name", symbol),
                "total_quantity": 0,
                "fresh_buy_quantity": 0,
                "fresh_sell_quantity": 0,
                "fresh_order_ids": [],
                "stale_order_ids": [],
                "latest_at": None,
            })
            bucket["total_quantity"] += quantity
            if side == "SELL" and is_fresh:
                bucket["fresh_sell_quantity"] += quantity
            elif side == "BUY" and is_fresh:
                bucket["fresh_buy_quantity"] += quantity

            order_id = getattr(trade, "order_id", None)
            if order_id:
                key = "fresh_order_ids" if is_fresh else "stale_order_ids"
                bucket[key].append(str(order_id))
            normalized_event_at = self._normalize_datetime(event_at)
            if normalized_event_at and (
                bucket["latest_at"] is None or normalized_event_at > bucket["latest_at"]
            ):
                bucket["latest_at"] = normalized_event_at
        return pending_by_symbol

    @staticmethod
    def _is_fresh_pending_confirm(event_at: datetime | None, *, side: str, now: datetime) -> bool:
        event_at = TradeLifecycleIntegrityService._normalize_datetime(event_at)
        now = TradeLifecycleIntegrityService._normalize_datetime(now)
        if event_at is None:
            return False
        age_sec = (now - event_at).total_seconds()
        return age_sec >= 0 and age_sec <= TradeLifecycleIntegrityService._pending_confirm_grace_sec(side)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _pending_confirm_grace_sec(side: str) -> float:
        confirm_timeout_sec = float(getattr(settings, "ORDER_CONFIRM_STATUS_TIMEOUT_SEC", 15) or 15)
        buffer_sec = 15.0
        if str(side or "").upper() == "SELL":
            wait_sec = float(getattr(settings, "SELL_ORDER_CONFIRM_WAIT_SEC", 3) or 3)
            return wait_sec + confirm_timeout_sec + buffer_sec

        buy_waits = [
            float(getattr(settings, "BUY_ORDER_CONFIRM_WAIT_SEC_CONSERVATIVE", 90) or 90),
            float(getattr(settings, "BUY_ORDER_CONFIRM_WAIT_SEC_MODERATE", 60) or 60),
            float(getattr(settings, "BUY_ORDER_CONFIRM_WAIT_SEC_AGGRESSIVE", 30) or 30),
        ]
        return max(buy_waits) + confirm_timeout_sec + buffer_sec

    @staticmethod
    def _build_broker_position_check(
        open_buy_positions: list[TradeResult],
        *,
        pending_confirm_positions: dict[str, dict] | None = None,
        broker_position_snapshot: dict | None,
    ) -> dict:
        if broker_position_snapshot is None:
            return {
                "available": False,
                "status": "OK",
                "missing_count": 0,
                "missing_quantity": 0,
                "mismatched_quantity": 0,
                "extra_status": "OK",
                "extra_count": 0,
                "extra_quantity": 0,
                "details": [],
                "extra_details": [],
            }

        if broker_position_snapshot.get("error"):
            return {
                "available": False,
                "status": "WARN",
                "missing_count": 0,
                "missing_quantity": 0,
                "mismatched_quantity": 0,
                "extra_status": "WARN",
                "extra_count": 0,
                "extra_quantity": 0,
                "details": [{"reason": "broker_snapshot_error", "error": broker_position_snapshot.get("error")}],
                "extra_details": [],
            }

        holding_quantities = {
            normalize_krx_symbol(symbol): int(quantity or 0)
            for symbol, quantity in (broker_position_snapshot.get("holding_quantities") or {}).items()
        }
        pending_symbols = {
            normalize_krx_symbol(symbol)
            for symbol in (broker_position_snapshot.get("pending_symbols") or [])
        }
        db_pending_by_symbol = pending_confirm_positions or {}
        db_pending_symbols = set(db_pending_by_symbol.keys())

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
        extra_details = []
        extra_count = 0
        extra_quantity = 0
        for symbol, item in open_by_symbol.items():
            db_qty = int(item["db_open_quantity"] or 0)
            broker_qty = int(holding_quantities.get(symbol, 0) or 0)
            pending = symbol in pending_symbols
            db_pending = db_pending_by_symbol.get(symbol) or {}
            fresh_sell_qty = int(db_pending.get("fresh_sell_quantity") or 0)
            if pending or broker_qty >= db_qty or (fresh_sell_qty > 0 and broker_qty + fresh_sell_qty >= db_qty):
                continue
            gap = db_qty - broker_qty
            item["broker_holding_quantity"] = broker_qty
            item["pending_order_exists"] = pending
            item["fresh_db_pending_sell_quantity"] = fresh_sell_qty
            item["missing_quantity"] = gap
            item["reason"] = "broker_holding_missing" if broker_qty <= 0 else "broker_holding_quantity_mismatch"
            details.append(item)
            missing_count += 1
            missing_quantity += gap if broker_qty <= 0 else 0
            mismatched_quantity += gap if broker_qty > 0 else 0

        for symbol, broker_qty in sorted(holding_quantities.items()):
            if broker_qty <= 0:
                continue
            db_qty = int((open_by_symbol.get(symbol) or {}).get("db_open_quantity", 0) or 0)
            if broker_qty <= db_qty:
                continue
            db_pending = db_pending_by_symbol.get(symbol) or {}
            fresh_buy_qty = int(db_pending.get("fresh_buy_quantity") or 0)
            if symbol in pending_symbols and symbol in db_pending_symbols:
                continue
            if fresh_buy_qty > 0 and broker_qty <= db_qty + fresh_buy_qty:
                continue
            gap = broker_qty - db_qty
            base = open_by_symbol.get(symbol) or {
                "stock_symbol": symbol,
                "stock_name": symbol,
                "trade_ids": [],
            }
            extra_details.append({
                **base,
                "db_open_quantity": db_qty,
                "broker_holding_quantity": broker_qty,
                "broker_pending_order_exists": symbol in pending_symbols,
                "db_pending_confirm_exists": symbol in db_pending_symbols,
                "fresh_db_pending_buy_quantity": fresh_buy_qty,
                "extra_quantity": gap,
                "reason": "broker_holding_exceeds_db_open",
            })
            extra_count += 1
            extra_quantity += gap

        return {
            "available": True,
            "status": "FAIL" if details else "OK",
            "missing_count": missing_count,
            "missing_quantity": missing_quantity,
            "mismatched_quantity": mismatched_quantity,
            "extra_status": "FAIL" if extra_details else "OK",
            "extra_count": extra_count,
            "extra_quantity": extra_quantity,
            "details": details,
            "extra_details": extra_details,
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
