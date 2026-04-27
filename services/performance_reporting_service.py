"""성과 검증/리포팅 집계 서비스."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.agent_activity import AgentActivityLog
from models.trade_result import TradeResult
from services.pnl_truth_service import pnl_truth_service
from trading.broker_factory import get_broker_adapter

_TRADE_BASELINE_RESET = {
    "active": True,
    "effective_date": "2026-04-06",
    "label": "2026-04-06 기준선 리셋 이후 데이터",
    "summary": "현재 브로커 계좌 상태와 복구된 열린 BUY lot를 기준선으로 사용 중",
    "details": [
        "현재 보유 종목/수량, 미체결 주문, 잔고는 브로커 응답 기준으로 해석",
        "과거 실현손익/매도 완료 이력은 로컬 DB 유실 전 구간을 완전 복구하지 않음",
    ],
}


@dataclass
class _TradePoint:
    strategy_type: str
    horizon: str
    pnl: float
    return_pct: float
    exit_at: datetime
    news_negative_pressure: float | None = None
    news_enriched: bool = False
    entry_price: float = 0.0
    quantity: int = 0
    estimated_cost_bps: float | None = None


@dataclass
class _ShadowPoint:
    strategy_type: str
    horizon: str
    actual_decision: str
    baseline_decision: str
    blocked_by_news: bool
    negative_pressure: float | None = None
    threshold: float | None = None
    created_at: datetime | None = None


class PerformanceReportingService:
    """트레이딩 성과를 수익 검증 관점으로 요약한다."""

    async def build_summary(self, session: AsyncSession, *, days: int = 30) -> dict:
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=max(int(days), 1))

        trades = await self._fetch_closed_trades(session, from_dt=from_dt, to_dt=to_dt)
        shadow_points = await self._fetch_shadow_points(session, from_dt=from_dt, to_dt=to_dt)
        risk_counts = await self._fetch_risk_control_counts(session, from_dt=from_dt, to_dt=to_dt)

        overall = self._calc_metrics(trades)
        by_strategy = self._group_metrics(trades, key_fn=lambda item: item.strategy_type or "UNKNOWN")
        by_horizon = self._group_metrics(trades, key_fn=lambda item: item.horizon or "MID")
        shadow = self._calc_shadow_context(shadow_points)
        pnl_truth = await pnl_truth_service.build_summary(session)

        return {
            "baseline": self._build_baseline_snapshot(),
            "window": {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "days": max(int(days), 1),
                "trade_count": len(trades),
            },
            "overall": overall,
            "by_strategy": by_strategy,
            "by_horizon": by_horizon,
            "comparisons": self._calc_trade_comparisons(trades),
            "risk_controls": risk_counts,
            "news_context": self._calc_news_context(trades),
            "current_account": await self._build_live_account_snapshot(),
            "pnl_truth": pnl_truth,
            "metric_contract": self._build_metric_contract(pnl_truth),
            "shadow": shadow,
            "rollout": self._build_rollout_status(
                overall=overall,
                shadow=shadow,
                comparisons=self._calc_trade_comparisons(trades),
                min_sample_size=max(int(getattr(settings, "NEWS_ROLLOUT_MIN_SAMPLE_SIZE", 12) or 12), 1),
                min_profit_factor=float(getattr(settings, "NEWS_ROLLOUT_MIN_PROFIT_FACTOR", 1.1) or 1.1),
                min_expectancy=float(getattr(settings, "NEWS_ROLLOUT_MIN_EXPECTANCY", 0.0) or 0.0),
                max_drawdown_limit=-abs(float(getattr(settings, "NEWS_ROLLOUT_MAX_DRAWDOWN_KRW", 500000.0) or 500000.0)),
            ),
        }

    @staticmethod
    def _build_metric_contract(pnl_truth: dict) -> dict:
        return {
            "overall_source": "trade_results.closed_buy",
            "account_pnl_source": "pnl_truth",
            "overall_deprecated_for_account_pnl": True,
            "sample_status": str(
                (pnl_truth or {}).get("account_pnl_sample_status")
                or (pnl_truth or {}).get("sample_status")
                or "UNKNOWN"
            ),
            "closed_trade_sample_status": str((pnl_truth or {}).get("sample_status") or "UNKNOWN"),
            "pnl_reconciliation_status": str((pnl_truth or {}).get("pnl_reconciliation_status") or "UNKNOWN"),
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
            shadow_points = await self._fetch_shadow_points(session, from_dt=start, to_dt=end)
            buckets.append({
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "metrics": self._calc_metrics(trades),
                "news_context": self._calc_news_context(trades),
                "shadow": self._calc_shadow_context(shadow_points),
            })

        return {
            "period": period_key,
            "bucket_days": bucket_days,
            "baseline": self._build_baseline_snapshot(),
            "buckets": list(reversed(buckets)),
        }

    @staticmethod
    async def _build_live_account_snapshot() -> dict:
        try:
            adapter = get_broker_adapter()
            balance, holdings, pending_orders = await __import__("asyncio").gather(
                adapter.get_balance(),
                adapter.get_holdings(),
                adapter.get_pending_orders(),
            )
            return {
                "synced": True,
                "total_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
                "cash": float(getattr(balance, "cash", 0.0) or 0.0),
                "stock_value": float(getattr(balance, "stock_value", 0.0) or 0.0),
                "unrealized_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
                "unrealized_pnl_rate": float(getattr(balance, "total_pnl_rate", 0.0) or 0.0),
                "holding_count": len(holdings or []),
                "pending_order_count": len(pending_orders or []),
            }
        except Exception as exc:
            return {
                "synced": False,
                "total_asset": 0.0,
                "cash": 0.0,
                "stock_value": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_rate": 0.0,
                "holding_count": 0,
                "pending_order_count": 0,
                "warning": str(exc)[:160],
            }

    def build_trade_comparison_from_results(self, trades: list[TradeResult]) -> dict:
        points = [self._trade_point_from_result(row) for row in trades if getattr(row, "exit_at", None) is not None]
        return self._calc_trade_comparisons(points)

    @staticmethod
    def _build_baseline_snapshot() -> dict:
        return {
            "active": bool(_TRADE_BASELINE_RESET["active"]),
            "effective_date": str(_TRADE_BASELINE_RESET["effective_date"]),
            "label": str(_TRADE_BASELINE_RESET["label"]),
            "summary": str(_TRADE_BASELINE_RESET["summary"]),
            "details": list(_TRADE_BASELINE_RESET["details"]),
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
        return [self._trade_point_from_result(row) for row in rows]

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
        news_gate_stmt = select(func.count(AgentActivityLog.id)).where(and_(
            base,
            AgentActivityLog.summary.like("%뉴스 게이트 차단%"),
        ))
        news_recheck_stmt = select(func.count(AgentActivityLog.id)).where(and_(
            base,
            AgentActivityLog.summary.like("%신규 뉴스 감지 → 관련 종목 재검증%"),
        ))
        return {
            "cost_gate_blocks": int((await session.execute(cost_gate_stmt)).scalar() or 0),
            "kill_switch_blocks": int((await session.execute(kill_stmt)).scalar() or 0),
            "news_gate_blocks": int((await session.execute(news_gate_stmt)).scalar() or 0),
            "news_rechecks": int((await session.execute(news_recheck_stmt)).scalar() or 0),
        }

    async def _fetch_shadow_points(self, session: AsyncSession, *, from_dt: datetime, to_dt: datetime) -> list[_ShadowPoint]:
        if not bool(getattr(settings, "NEWS_SHADOW_ENABLED", True)):
            return []

        stmt = (
            select(AgentActivityLog)
            .where(and_(
                AgentActivityLog.created_at >= from_dt,
                AgentActivityLog.created_at <= to_dt,
                AgentActivityLog.summary.like("%Shadow A/B%"),
            ))
            .order_by(AgentActivityLog.created_at.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        points: list[_ShadowPoint] = []
        for row in rows:
            parsed = self._parse_shadow_detail(getattr(row, "detail", None))
            if not parsed:
                continue
            points.append(_ShadowPoint(
                strategy_type=str(parsed.get("strategy_type") or "UNKNOWN"),
                horizon=str(parsed.get("horizon") or "MID").upper(),
                actual_decision=str(parsed.get("actual_decision") or "").upper(),
                baseline_decision=str(parsed.get("baseline_decision") or "").upper(),
                blocked_by_news=bool(parsed.get("blocked_by_news")),
                negative_pressure=self._coerce_float(parsed.get("negative_pressure")),
                threshold=self._coerce_float(parsed.get("threshold")),
                created_at=getattr(row, "created_at", None),
            ))
        return points

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
                "estimated_cost_total": 0.0,
                "net_pnl_after_cost": 0.0,
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
        estimated_cost_total = sum(
            ((item.entry_price * item.quantity) * (float(item.estimated_cost_bps) / 10000.0))
            for item in trades
            if item.entry_price > 0 and item.quantity > 0 and item.estimated_cost_bps is not None
        )

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
            "estimated_cost_total": round(estimated_cost_total, 2),
            "net_pnl_after_cost": round(sum(pnls) - estimated_cost_total, 2),
            "avg_return_pct": round(sum(returns) / len(returns), 4),
            "max_drawdown": round(max_dd, 2),
        }

    @staticmethod
    def _calc_news_context(trades: list[_TradePoint]) -> dict:
        enriched = [item for item in trades if item.news_enriched or item.news_negative_pressure is not None]
        values = [
            float(item.news_negative_pressure)
            for item in enriched
            if item.news_negative_pressure is not None
        ]
        if not enriched:
            return {
                "trade_count": 0,
                "avg_negative_pressure": 0.0,
            }
        return {
            "trade_count": len(enriched),
            "avg_negative_pressure": round(sum(values) / len(values), 4) if values else 0.0,
        }

    @staticmethod
    def _calc_shadow_context(points: list[_ShadowPoint]) -> dict:
        if not points:
            return {
                "candidate_count": 0,
                "actual_buy_count": 0,
                "baseline_buy_count": 0,
                "buy_delta": 0,
                "blocked_by_news_count": 0,
                "avg_negative_pressure": 0.0,
                "block_rate": 0.0,
            }

        values = [
            float(item.negative_pressure)
            for item in points
            if item.negative_pressure is not None
        ]
        blocked = sum(1 for item in points if item.blocked_by_news)
        actual_buys = sum(1 for item in points if item.actual_decision == "BUY")
        baseline_buys = sum(1 for item in points if item.baseline_decision == "BUY")
        candidate_count = len(points)
        return {
            "candidate_count": candidate_count,
            "actual_buy_count": actual_buys,
            "baseline_buy_count": baseline_buys,
            "buy_delta": actual_buys - baseline_buys,
            "blocked_by_news_count": blocked,
            "avg_negative_pressure": round(sum(values) / len(values), 4) if values else 0.0,
            "block_rate": round(blocked / candidate_count, 4) if candidate_count else 0.0,
        }

    def _calc_trade_comparisons(self, trades: list[_TradePoint]) -> dict:
        news_enriched = [item for item in trades if item.news_enriched or item.news_negative_pressure is not None]
        plain = [item for item in trades if not item.news_enriched and item.news_negative_pressure is None]

        news_metrics = self._calc_metrics(news_enriched)
        plain_metrics = self._calc_metrics(plain)

        return {
            "news_enriched": news_metrics,
            "plain": plain_metrics,
            "delta": {
                "expectancy": round(float(news_metrics.get("expectancy", 0.0) or 0.0) - float(plain_metrics.get("expectancy", 0.0) or 0.0), 2),
                "profit_factor": round(float(news_metrics.get("profit_factor", 0.0) or 0.0) - float(plain_metrics.get("profit_factor", 0.0) or 0.0), 4),
                "net_pnl_after_cost": round(float(news_metrics.get("net_pnl_after_cost", 0.0) or 0.0) - float(plain_metrics.get("net_pnl_after_cost", 0.0) or 0.0), 2),
            },
        }

    @staticmethod
    def _build_rollout_status(
        *,
        overall: dict,
        shadow: dict,
        comparisons: dict | None = None,
        min_sample_size: int,
        min_profit_factor: float,
        min_expectancy: float,
        max_drawdown_limit: float,
    ) -> dict:
        trade_count = int(overall.get("trade_count") or 0)
        expectancy = float(overall.get("expectancy") or 0.0)
        profit_factor = float(overall.get("profit_factor") or 0.0)
        max_drawdown = float(overall.get("max_drawdown") or 0.0)
        shadow_candidates = int(shadow.get("candidate_count") or 0)
        blocked = int(shadow.get("blocked_by_news_count") or 0)
        actual_buys = int(shadow.get("actual_buy_count") or 0)
        baseline_buys = int(shadow.get("baseline_buy_count") or 0)
        comparisons = comparisons or {}
        comparison_delta = comparisons.get("delta") or {}
        comparison_news = comparisons.get("news_enriched") or {}
        comparison_plain = comparisons.get("plain") or {}
        comparison_ready = (
            int(comparison_news.get("trade_count") or 0) > 0
            and int(comparison_plain.get("trade_count") or 0) > 0
        )
        sample_passed = trade_count >= min_sample_size and shadow_candidates >= min_sample_size
        expectancy_passed = expectancy >= min_expectancy
        pf_passed = profit_factor >= min_profit_factor
        drawdown_passed = max_drawdown > max_drawdown_limit
        comparison_expectancy_delta = float(comparison_delta.get("expectancy") or 0.0)
        comparison_net_pnl_delta = float(comparison_delta.get("net_pnl_after_cost") or 0.0)
        comparison_passed = (
            not comparison_ready
            or (
                comparison_expectancy_delta >= 0
                and comparison_net_pnl_delta >= 0
            )
        )

        checks = [
            {
                "key": "sample",
                "label": "표본",
                "passed": sample_passed,
                "actual": f"실거래 {trade_count}건 / Shadow {shadow_candidates}건",
                "target": f"각 {min_sample_size}건 이상",
            },
            {
                "key": "expectancy",
                "label": "기대값",
                "passed": expectancy_passed,
                "actual": f"{expectancy:.2f}",
                "target": f"{min_expectancy:.2f} 이상",
            },
            {
                "key": "profit_factor",
                "label": "PF",
                "passed": pf_passed,
                "actual": f"{profit_factor:.2f}",
                "target": f"{min_profit_factor:.2f} 이상",
            },
            {
                "key": "drawdown",
                "label": "MDD",
                "passed": drawdown_passed,
                "actual": f"{max_drawdown:,.0f}원",
                "target": f"{max_drawdown_limit:,.0f}원 초과",
            },
        ]
        if comparison_ready:
            checks.extend([
                {
                    "key": "comparison_expectancy",
                    "label": "뉴스 E 비교",
                    "passed": comparison_expectancy_delta >= 0,
                    "actual": f"{comparison_expectancy_delta:+.2f}",
                    "target": "0.00 이상",
                },
                {
                    "key": "comparison_net_pnl",
                    "label": "비용차감 비교",
                    "passed": comparison_net_pnl_delta >= 0,
                    "actual": f"{comparison_net_pnl_delta:+,.0f}원",
                    "target": "0원 이상",
                },
            ])

        details = [
            f"Shadow 후보 {shadow_candidates}건 · 실제 BUY {actual_buys}건 · 기준 BUY {baseline_buys}건",
            f"뉴스 차단 {blocked}건 · 차단율 {round((blocked / shadow_candidates) * 100, 1) if shadow_candidates else 0.0:.1f}%",
            f"기대값 {expectancy:.2f} · PF {profit_factor:.2f} · MDD {max_drawdown:,.0f}원",
        ]
        if comparison_ready:
            details.append(
                "뉴스 반영 거래 비교 "
                f"E {comparison_expectancy_delta:+.2f} · 비용차감 {comparison_net_pnl_delta:+,.0f}원"
            )
        else:
            details.append("뉴스 반영 거래 비교는 아직 표본 부족")

        if not sample_passed:
            return {
                "status": "HOLDOUT",
                "reason": f"표본 부족: 실거래 {trade_count}건 / shadow {shadow_candidates}건",
                "details": details,
                "checks": checks,
            }
        if not expectancy_passed or not pf_passed or not drawdown_passed:
            return {
                "status": "ROLLBACK",
                "reason": (
                    f"롤백 권장: 기대값 {expectancy:.2f}, PF {profit_factor:.2f}, MDD {max_drawdown:,.0f}원"
                ),
                "details": details,
                "checks": checks,
            }
        if not comparison_passed:
            return {
                "status": "KEEP",
                "reason": (
                    "현 설정 유지: 뉴스 반영 거래가 일반 거래 대비 아직 열위 "
                    f"(E {comparison_expectancy_delta:+.2f}, 비용차감 {comparison_net_pnl_delta:+,.0f}원)"
                ),
                "details": details,
                "checks": checks,
            }
        if blocked > 0:
            return {
                "status": "PROMOTE",
                "reason": (
                    f"비중 확대 권장: 기대값 {expectancy:.2f}, PF {profit_factor:.2f}, 뉴스 차단 {blocked}건"
                ),
                "details": details,
                "checks": checks,
            }
        return {
            "status": "KEEP",
            "reason": f"현 설정 유지: 기대값 {expectancy:.2f}, PF {profit_factor:.2f}",
            "details": details,
            "checks": checks,
        }

    @staticmethod
    def _parse_shadow_detail(detail: str | None) -> dict | None:
        if not detail:
            return None
        try:
            parsed = json.loads(detail)
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        if parsed.get("kind") != "NEWS_SHADOW_AB":
            return None
        return parsed

    @staticmethod
    def _coerce_float(value) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

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

    @staticmethod
    def _extract_news_negative_pressure(trade: TradeResult) -> float | None:
        notes = getattr(trade, "notes", None)
        if not notes:
            return None
        try:
            parsed = json.loads(notes)
        except (TypeError, ValueError):
            return None
        value = parsed.get("news_negative_pressure")
        if value is None:
            value = parsed.get("news_context_negative_pressure")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_news_enriched(trade: TradeResult) -> bool:
        notes = getattr(trade, "notes", None)
        if not notes:
            return False
        try:
            parsed = json.loads(notes)
        except (TypeError, ValueError):
            return False
        if parsed.get("news_negative_pressure") is not None:
            return True
        if parsed.get("news_context_available") is True:
            return True
        try:
            if int(parsed.get("news_context_item_count") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
        items = parsed.get("news_context_items")
        if isinstance(items, list) and items:
            return True
        source_codes = parsed.get("news_context_source_codes")
        return isinstance(source_codes, list) and bool(source_codes)

    @staticmethod
    def _extract_estimated_cost_bps(trade: TradeResult) -> float | None:
        notes = getattr(trade, "notes", None)
        if not notes:
            return None
        try:
            parsed = json.loads(notes)
        except (TypeError, ValueError):
            return None
        value = parsed.get("estimated_cost_bps")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _trade_point_from_result(self, row: TradeResult) -> _TradePoint:
        return _TradePoint(
            strategy_type=str(getattr(row, "strategy_type", "") or ""),
            horizon=self._extract_horizon(row),
            pnl=float(getattr(row, "pnl", 0.0) or 0.0),
            return_pct=float(getattr(row, "return_pct", 0.0) or 0.0),
            exit_at=getattr(row, "exit_at"),
            news_negative_pressure=self._extract_news_negative_pressure(row),
            news_enriched=self._extract_news_enriched(row),
            entry_price=float(getattr(row, "entry_price", 0.0) or 0.0),
            quantity=int(getattr(row, "quantity", 0) or 0),
            estimated_cost_bps=self._extract_estimated_cost_bps(row),
        )


performance_reporting_service = PerformanceReportingService()
