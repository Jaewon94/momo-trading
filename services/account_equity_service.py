from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from loguru import logger

from core.database import AsyncSessionLocal, run_sqlite_write_with_retry
from repositories.account_day_baseline_repository import AccountDayBaselineRepository
from repositories.account_equity_snapshot_repository import AccountEquitySnapshotRepository
from repositories.trade_result_repository import TradeResultRepository
from scheduler.market_calendar import market_calendar
from trading.broker_factory import get_broker_adapter
from trading.models import AccountBalance, HoldingInfo, PendingOrderInfo
from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
from util.time_util import ensure_kst, now_kst

ACCOUNT_EQUITY_SNAPSHOT_STALE_AFTER_SEC = 600


@dataclass(frozen=True)
class AccountEquityState:
    captured_at: datetime
    trading_date: date
    total_asset: float
    cash: float
    stock_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_rate: float
    holding_count: int
    pending_order_count: int
    detail: dict[str, Any] | None = None


def classify_account_snapshot_freshness(
    *,
    latest_captured_at: datetime | None,
    observed_at: datetime,
    stale_after_sec: int = ACCOUNT_EQUITY_SNAPSHOT_STALE_AFTER_SEC,
) -> dict[str, Any]:
    timestamp = ensure_kst(observed_at)
    if latest_captured_at is None:
        return {
            "snapshot_age_sec": None,
            "snapshot_freshness_status": "MISSING",
            "snapshot_stale_reason": "snapshot_missing",
            "snapshot_stale_message": "오늘 계좌 스냅샷이 아직 없습니다.",
            "snapshot_stale_blocks_buy": True,
            "is_stale": False,
        }

    latest = ensure_kst(latest_captured_at)
    age_sec = max(int((timestamp - latest).total_seconds()), 0)
    if age_sec <= stale_after_sec:
        return {
            "snapshot_age_sec": age_sec,
            "snapshot_freshness_status": "FRESH",
            "snapshot_stale_reason": "",
            "snapshot_stale_message": "",
            "snapshot_stale_blocks_buy": False,
            "is_stale": False,
        }

    session = market_calendar.get_market_session_info(timestamp)
    if not bool(session.get("supports_automated_trading")):
        return {
            "snapshot_age_sec": age_sec,
            "snapshot_freshness_status": "OFF_SESSION_STALE",
            "snapshot_stale_reason": "off_session_auto_trading_disabled",
            "snapshot_stale_message": (
                f"{session.get('label') or '자동매매 비지원 세션'}에서는 정규 자동매매가 비활성이라 "
                "계좌 스냅샷이 오래될 수 있습니다."
            ),
            "snapshot_stale_blocks_buy": False,
            "is_stale": True,
        }

    return {
        "snapshot_age_sec": age_sec,
        "snapshot_freshness_status": "STALE",
        "snapshot_stale_reason": "regular_session_snapshot_stale",
        "snapshot_stale_message": "자동매매 가능 세션에서 계좌 스냅샷이 오래되어 신규 매수를 보류해야 합니다.",
        "snapshot_stale_blocks_buy": True,
        "is_stale": True,
    }


class AccountEquityService:
    def __init__(
        self,
        *,
        session_factory=AsyncSessionLocal,
        now_func: Callable[[], datetime] = now_kst,
    ) -> None:
        self._session_factory = session_factory
        self._now = now_func

    def build_state(
        self,
        balance: AccountBalance,
        *,
        holdings: list[HoldingInfo] | None = None,
        pending_orders: list[PendingOrderInfo] | None = None,
        captured_at: datetime | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AccountEquityState:
        timestamp = ensure_kst(captured_at or self._now())
        return AccountEquityState(
            captured_at=timestamp,
            trading_date=timestamp.date(),
            total_asset=float(getattr(balance, "total_asset", 0.0) or 0.0),
            cash=float(getattr(balance, "cash", 0.0) or 0.0),
            stock_value=float(getattr(balance, "stock_value", 0.0) or 0.0),
            total_unrealized_pnl=float(getattr(balance, "total_pnl", 0.0) or 0.0),
            total_unrealized_pnl_rate=float(getattr(balance, "total_pnl_rate", 0.0) or 0.0),
            holding_count=len(holdings or []),
            pending_order_count=len(pending_orders or []),
            detail=detail,
        )

    async def ensure_day_baseline(
        self,
        state: AccountEquityState,
        *,
        baseline_source: str = "UNKNOWN",
    ) -> AccountDayBaseline:
        async def _persist() -> AccountDayBaseline:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = AccountDayBaselineRepository(session)
                    existing = await repo.get_by_trading_date(state.trading_date)
                    if existing is not None:
                        return existing
                    entry = AccountDayBaseline(
                        trading_date=state.trading_date,
                        baseline_at=state.captured_at,
                        baseline_total_asset=state.total_asset,
                        baseline_cash=state.cash,
                        baseline_stock_value=state.stock_value,
                        baseline_total_unrealized_pnl=state.total_unrealized_pnl,
                        baseline_holding_count=state.holding_count,
                        baseline_pending_order_count=state.pending_order_count,
                        baseline_source=str(baseline_source or "UNKNOWN"),
                    )
                    await repo.create(entry)
                    return entry

        return await run_sqlite_write_with_retry(_persist)

    async def record_snapshot(
        self,
        state: AccountEquityState,
        *,
        session_phase: str = "INTRADAY",
        baseline_source: str | None = None,
    ) -> AccountEquitySnapshot:
        await self.ensure_day_baseline(
            state,
            baseline_source=baseline_source or session_phase,
        )

        async def _persist() -> AccountEquitySnapshot:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = AccountEquitySnapshotRepository(session)
                    entry = AccountEquitySnapshot(
                        trading_date=state.trading_date,
                        captured_at=state.captured_at,
                        session_phase=str(session_phase or "INTRADAY"),
                        total_asset=state.total_asset,
                        cash=state.cash,
                        stock_value=state.stock_value,
                        total_unrealized_pnl=state.total_unrealized_pnl,
                        total_unrealized_pnl_rate=state.total_unrealized_pnl_rate,
                        holding_count=state.holding_count,
                        pending_order_count=state.pending_order_count,
                        detail=self._serialize_detail(state.detail),
                    )
                    await repo.create(entry)
                    return entry

        return await run_sqlite_write_with_retry(_persist)

    async def capture_and_record_current(
        self,
        *,
        session_phase: str = "INTRADAY",
        detail: dict[str, Any] | None = None,
        baseline_source: str | None = None,
    ) -> AccountEquitySnapshot:
        adapter = get_broker_adapter()
        balance, holdings, pending_orders = await asyncio.gather(
            adapter.get_balance(),
            adapter.get_holdings(),
            adapter.get_pending_orders(),
        )
        state = self.build_state(
            balance,
            holdings=holdings,
            pending_orders=pending_orders,
            detail=detail,
        )
        return await self.record_snapshot(
            state,
            session_phase=session_phase,
            baseline_source=baseline_source or session_phase,
        )

    async def build_balance_payload(
        self,
        balance: AccountBalance,
        *,
        captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = ensure_kst(captured_at or self._now())
        payload = {
            "total_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
            "cash": float(getattr(balance, "cash", 0.0) or 0.0),
            "stock_value": float(getattr(balance, "stock_value", 0.0) or 0.0),
            "total_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
            "total_pnl_rate": float(getattr(balance, "total_pnl_rate", 0.0) or 0.0),
        }
        try:
            payload["session_metrics"] = await self._build_session_metrics(balance, captured_at=timestamp)
        except Exception as exc:
            logger.warning("계좌 세션 메트릭 계산 실패: {}", str(exc))
            payload["session_metrics"] = self._build_empty_metrics(
                balance,
                captured_at=timestamp,
                reason="metrics_error",
            )
        return payload

    async def _build_session_metrics(
        self,
        balance: AccountBalance,
        *,
        captured_at: datetime,
    ) -> dict[str, Any]:
        timestamp = ensure_kst(captured_at)
        trading_date = timestamp.date()
        async with self._session_factory() as session:
            baseline_repo = AccountDayBaselineRepository(session)
            snapshot_repo = AccountEquitySnapshotRepository(session)
            trade_repo = TradeResultRepository(session)

            baseline = await baseline_repo.get_by_trading_date(trading_date)
            latest_snapshot = await snapshot_repo.get_latest_by_trading_date(trading_date)
            high_asset, low_asset = await snapshot_repo.get_asset_range_for_date(trading_date)
            realized_today_pnl = sum(
                float(getattr(item, "pnl", 0.0) or 0.0)
                for item in await trade_repo.get_completed_by_date(trading_date)
            )

        if baseline is None:
            return self._build_empty_metrics(
                balance,
                captured_at=timestamp,
                reason="baseline_missing",
                realized_today_pnl=realized_today_pnl,
            )

        current_asset = float(getattr(balance, "total_asset", 0.0) or 0.0)
        current_exposure_krw = float(getattr(balance, "stock_value", 0.0) or 0.0)
        current_exposure_pct = (current_exposure_krw / current_asset * 100.0) if current_asset > 0 else 0.0
        broker_unrealized_pnl = float(getattr(balance, "total_pnl", 0.0) or 0.0)
        baseline_asset = float(getattr(baseline, "baseline_total_asset", 0.0) or 0.0)
        asset_delta = current_asset - baseline_asset
        asset_delta_rate = (asset_delta / baseline_asset * 100.0) if baseline_asset > 0 else 0.0
        daily_unrealized_delta = asset_delta - realized_today_pnl
        cash_or_snapshot_delta = asset_delta - realized_today_pnl - broker_unrealized_pnl
        intraday_high_asset = max(
            value for value in [current_asset, self._optional_float(high_asset), baseline_asset] if value is not None
        )
        intraday_low_asset = min(
            value for value in [current_asset, self._optional_float(low_asset), baseline_asset] if value is not None
        )
        latest_captured_at = ensure_kst(getattr(latest_snapshot, "captured_at", None)) if latest_snapshot else None
        snapshot_freshness = classify_account_snapshot_freshness(
            latest_captured_at=latest_captured_at,
            observed_at=timestamp,
        )

        return {
            "available": True,
            "reason": None,
            "trading_date": trading_date.isoformat(),
            "baseline_at": ensure_kst(baseline.baseline_at).isoformat(),
            "baseline_total_asset": baseline_asset,
            "asset_delta": asset_delta,
            "asset_delta_rate": asset_delta_rate,
            "realized_today_pnl": realized_today_pnl,
            "broker_unrealized_pnl": broker_unrealized_pnl,
            "daily_unrealized_delta": daily_unrealized_delta,
            "cash_or_snapshot_delta": cash_or_snapshot_delta,
            "current_exposure_krw": current_exposure_krw,
            "current_exposure_pct": current_exposure_pct,
            "market_exposure": current_exposure_krw > 0,
            **self._build_session_risk_summary(
                current_exposure_krw=current_exposure_krw,
                broker_unrealized_pnl=broker_unrealized_pnl,
                cash_or_snapshot_delta=cash_or_snapshot_delta,
            ),
            "intraday_high_asset": intraday_high_asset,
            "intraday_low_asset": intraday_low_asset,
            "latest_snapshot_at": latest_captured_at.isoformat() if latest_captured_at is not None else None,
            **snapshot_freshness,
        }

    def _build_empty_metrics(
        self,
        balance: AccountBalance,
        *,
        captured_at: datetime,
        reason: str,
        realized_today_pnl: float = 0.0,
    ) -> dict[str, Any]:
        current_asset = float(getattr(balance, "total_asset", 0.0) or 0.0)
        current_exposure_krw = float(getattr(balance, "stock_value", 0.0) or 0.0)
        broker_unrealized_pnl = float(getattr(balance, "total_pnl", 0.0) or 0.0)
        timestamp = ensure_kst(captured_at)
        return {
            "available": False,
            "reason": reason,
            "trading_date": timestamp.date().isoformat(),
            "baseline_at": None,
            "baseline_total_asset": 0.0,
            "asset_delta": 0.0,
            "asset_delta_rate": 0.0,
            "realized_today_pnl": realized_today_pnl,
            "broker_unrealized_pnl": broker_unrealized_pnl,
            "daily_unrealized_delta": 0.0,
            "cash_or_snapshot_delta": 0.0,
            "current_exposure_krw": current_exposure_krw,
            "current_exposure_pct": (current_exposure_krw / current_asset * 100.0) if current_asset > 0 else 0.0,
            "market_exposure": current_exposure_krw > 0,
            **self._build_session_risk_summary(
                current_exposure_krw=current_exposure_krw,
                broker_unrealized_pnl=broker_unrealized_pnl,
                cash_or_snapshot_delta=0.0,
            ),
            "intraday_high_asset": current_asset,
            "intraday_low_asset": current_asset,
            "latest_snapshot_at": None,
            "snapshot_age_sec": None,
            "snapshot_freshness_status": "MISSING",
            "snapshot_stale_reason": "metrics_unavailable",
            "snapshot_stale_message": "세션 메트릭을 계산할 수 없어 계좌 스냅샷 최신성을 판단하지 못했습니다.",
            "snapshot_stale_blocks_buy": True,
            "is_stale": False,
        }

    @staticmethod
    def _build_session_risk_summary(
        *,
        current_exposure_krw: float,
        broker_unrealized_pnl: float,
        cash_or_snapshot_delta: float,
    ) -> dict[str, str]:
        tolerance = 1.0
        if current_exposure_krw <= tolerance:
            if abs(cash_or_snapshot_delta) > tolerance:
                return {
                    "risk_label": "CASH_OR_SNAPSHOT_VARIANCE",
                    "risk_message": "현재 보유 노출은 없고, 장시작 대비 차이는 현금/정산/스냅샷성 변동으로 분리됩니다.",
                }
            return {
                "risk_label": "NO_EXPOSURE",
                "risk_message": "현재 보유 노출이 없어 시장 가격 변동 리스크는 낮습니다.",
            }
        if broker_unrealized_pnl < -tolerance:
            return {
                "risk_label": "EXPOSED_LOSS",
                "risk_message": "보유 평가손실이 있어 가격 변동 리스크가 열려 있습니다.",
            }
        if broker_unrealized_pnl > tolerance:
            return {
                "risk_label": "EXPOSED_PROFIT",
                "risk_message": "보유 평가이익이 있으나 가격 변동 리스크는 열려 있습니다.",
            }
        return {
            "risk_label": "EXPOSED_FLAT",
            "risk_message": "보유 노출은 있으나 평가손익은 중립권입니다.",
        }

    @staticmethod
    def _serialize_detail(detail: dict[str, Any] | None) -> str | None:
        if not detail:
            return None
        return json.dumps(detail, ensure_ascii=False, default=str)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


account_equity_service = AccountEquityService()
