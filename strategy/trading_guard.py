"""자동 리스크 킬스위치 + 전략 기대값 게이트"""
from datetime import datetime, time

from sqlalchemy import and_, select

from analysis.feedback.performance_tracker import PerformanceTracker
from core.config import settings
from core.database import AsyncSessionLocal
from models.trade_result import TradeResult
from services.pnl_truth_service import pnl_truth_service
from services.runtime_settings_service import runtime_settings_service


class TradingGuard:
    """매수 전 계좌/전략 상태를 점검해 과도한 손실 구간을 차단한다."""

    async def evaluate_buy_guard(
        self,
        strategy_type: str,
        portfolio_budget: float,
        *,
        candidate_change_rate: float | None = None,
        candidate_pattern: str | None = None,
        intraday_direction: str | None = None,
        intraday_vwap_position: str | None = None,
        intraday_volume_trend: str | None = None,
        today_trade_count: int = 0,
        current_holding_count: int = 0,
    ) -> dict:
        drawdown_pct = await self._get_daily_realized_pnl_pct(portfolio_budget=portfolio_budget)
        max_drawdown = abs(float(settings.MAX_DAILY_DRAWDOWN_PCT or 0))
        if max_drawdown > 0 and drawdown_pct <= -max_drawdown:
            return await self._block(
                "DAILY_DRAWDOWN",
                f"일손실 한도 초과 ({drawdown_pct:.2f}% <= -{max_drawdown:.2f}%)",
            )

        warnings = []
        account_guard = await self._evaluate_account_equity_drawdown(max_drawdown=max_drawdown)
        if account_guard["action"] == "BLOCK":
            return await self._reject("ACCOUNT_EQUITY_DRAWDOWN", account_guard["reason"])
        if account_guard["action"] == "KILL_SWITCH":
            return await self._block("ACCOUNT_EQUITY_DRAWDOWN", account_guard["reason"])
        if account_guard["action"] == "WARN":
            warnings.append(account_guard["warning"])

        llm_guard = self._evaluate_llm_runtime_health()
        if llm_guard["action"] == "BLOCK":
            return await self._reject("LLM_RUNTIME_UNHEALTHY", llm_guard["reason"])

        consecutive_losses = await self._get_consecutive_losses()
        max_losses = int(settings.MAX_CONSECUTIVE_LOSSES or 0)
        if max_losses > 0 and consecutive_losses >= max_losses:
            loss_streak_guard = self._evaluate_loss_streak_recovery(
                consecutive_losses=consecutive_losses,
                max_losses=max_losses,
                candidate_change_rate=candidate_change_rate,
                candidate_pattern=candidate_pattern,
                intraday_direction=intraday_direction,
                intraday_vwap_position=intraday_vwap_position,
                intraday_volume_trend=intraday_volume_trend,
                today_trade_count=today_trade_count,
                current_holding_count=current_holding_count,
            )
            if loss_streak_guard["action"] == "ALLOW":
                warnings.append(loss_streak_guard["warning"])
            else:
                return await self._reject(
                    loss_streak_guard["trigger"],
                    loss_streak_guard["reason"],
                )

        expectancy = await self._get_strategy_expectancy(strategy_type)
        min_expectancy = float(settings.MIN_STRATEGY_EXPECTANCY or 0.0)
        if expectancy is not None and expectancy < min_expectancy:
            expectancy_guard = await self._evaluate_negative_expectancy(
                expectancy=expectancy,
                min_expectancy=min_expectancy,
            )
            if expectancy_guard["action"] == "ALLOW":
                warnings.append(expectancy_guard["warning"])
            elif expectancy_guard["action"] == "BLOCK":
                return await self._reject("NEGATIVE_EXPECTANCY", expectancy_guard["reason"])
            elif expectancy_guard["action"] == "KILL_SWITCH":
                return await self._block("NEGATIVE_EXPECTANCY", expectancy_guard["reason"])

        return {
            "approved": True,
            "reason": "트레이딩 가드 통과",
            "trigger": "",
            "kill_switched": False,
            "warnings": warnings,
        }

    @staticmethod
    async def _block(trigger: str, reason: str) -> dict:
        if settings.AUTO_RISK_KILL_SWITCH_ENABLED:
            await runtime_settings_service.update_settings({"TRADING_ENABLED": False})
        return {
            "approved": False,
            "reason": f"자동 킬스위치: {reason}",
            "trigger": trigger,
            "kill_switched": bool(settings.AUTO_RISK_KILL_SWITCH_ENABLED),
            "warnings": [],
        }

    async def _evaluate_negative_expectancy(self, *, expectancy: float, min_expectancy: float) -> dict:
        mode = str(getattr(settings, "STRATEGY_EXPECTANCY_GUARD_MODE", "REDUCE_SIZE") or "REDUCE_SIZE").upper()
        reason = f"전략 기대값 하회 ({expectancy:+.4f} < {min_expectancy:+.4f})"
        if mode == "OFF":
            return {"action": "ALLOW", "warning": {"trigger": "NEGATIVE_EXPECTANCY", "reason": reason}}
        if mode == "KILL_SWITCH":
            return {"action": "KILL_SWITCH", "reason": reason}
        if mode == "BLOCK_BUY":
            return {"action": "BLOCK", "reason": reason}

        multiplier = min(max(float(getattr(settings, "NEGATIVE_EXPECTANCY_SIZE_MULTIPLIER", 0.5) or 0.5), 0.05), 1.0)
        return {
            "action": "ALLOW",
            "warning": {
                "trigger": "NEGATIVE_EXPECTANCY",
                "reason": reason,
                "expectancy": expectancy,
                "min_expectancy": min_expectancy,
                "position_size_multiplier": multiplier,
            },
        }

    def _evaluate_loss_streak_recovery(
        self,
        *,
        consecutive_losses: int,
        max_losses: int,
        candidate_change_rate: float | None,
        candidate_pattern: str | None,
        intraday_direction: str | None,
        intraday_vwap_position: str | None,
        intraday_volume_trend: str | None,
        today_trade_count: int,
        current_holding_count: int,
    ) -> dict:
        mode = str(getattr(settings, "LOSS_STREAK_RECOVERY_MODE", "BLOCK_BUY") or "BLOCK_BUY").upper()
        reason = f"연속 손실 한도 도달 ({consecutive_losses}회 >= {max_losses}회)"
        probation_cautions: list[dict] = []

        if mode == "OFF":
            return {
                "action": "ALLOW",
                "warning": {
                    "trigger": "CONSECUTIVE_LOSSES",
                    "reason": f"{reason}, 복구 모드 OFF",
                    "recovery_mode": mode,
                    "consecutive_losses": consecutive_losses,
                },
            }

        if mode == "SHADOW":
            return {
                "action": "ALLOW",
                "warning": {
                    "trigger": "CONSECUTIVE_LOSSES_SHADOW",
                    "reason": f"{reason}, shadow 관측만 수행",
                    "recovery_mode": mode,
                    "consecutive_losses": consecutive_losses,
                    "max_losses": max_losses,
                },
            }

        if mode == "BLOCK_BUY":
            return {
                "action": "BLOCK",
                "trigger": "CONSECUTIVE_LOSSES",
                "reason": reason,
            }

        if mode == "PROBATION":
            max_daily_buys = int(getattr(settings, "LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS", 1) or 0)
            if max_daily_buys <= 0:
                return {
                    "action": "BLOCK",
                    "trigger": "CONSECUTIVE_LOSSES_PROBATION",
                    "reason": f"{reason}, probation 일일 매수 한도 0회",
                }
            if today_trade_count >= max_daily_buys:
                return {
                    "action": "BLOCK",
                    "trigger": "CONSECUTIVE_LOSSES_PROBATION",
                    "reason": f"{reason}, probation 일일 매수 한도 도달 ({today_trade_count}/{max_daily_buys})",
                }

            min_change = float(getattr(settings, "LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT", 0.0) or 0.0)
            max_change = float(getattr(settings, "LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT", 0.0) or 0.0)
            if candidate_change_rate is not None:
                if min_change > 0 and candidate_change_rate < min_change:
                    return {
                        "action": "BLOCK",
                        "trigger": "CONSECUTIVE_LOSSES_PROBATION",
                        "reason": f"{reason}, probation 모멘텀 부족 ({candidate_change_rate:.2f}% < {min_change:.2f}%)",
                    }
                if max_change > 0 and candidate_change_rate > max_change:
                    return {
                        "action": "BLOCK",
                        "trigger": "CONSECUTIVE_LOSSES_PROBATION",
                        "reason": f"{reason}, probation 과열 제외 ({candidate_change_rate:.2f}% > {max_change:.2f}%)",
                    }

            pattern = str(candidate_pattern or "").upper()
            if "UPTREND" in pattern:
                probation_cautions.append({
                    "code": "RECENT_LOSS_PATTERN",
                    "reason": f"최근 손실 반복 패턴 주의 ({candidate_pattern})",
                })

            intra_direction = str(intraday_direction or "").upper()
            vwap_position = str(intraday_vwap_position or "").upper()
            volume_trend = str(intraday_volume_trend or "").upper()
            weak_parts = [
                part for part in [
                    f"분봉 {intra_direction}" if intra_direction == "BEARISH" else "",
                    vwap_position if vwap_position == "BELOW_VWAP" else "",
                    f"거래량 {volume_trend}" if volume_trend == "DECREASING" else "",
                ]
                if part
            ]
            if len(weak_parts) >= 2:
                return {
                    "action": "BLOCK",
                    "trigger": "CONSECUTIVE_LOSSES_PROBATION",
                    "reason": f"{reason}, probation 장중 확인 부족 ({', '.join(weak_parts)})",
                }
            if weak_parts:
                probation_cautions.append({
                    "code": "WEAK_INTRADAY_COMPONENT",
                    "reason": f"장중 확인 일부 약함 ({', '.join(weak_parts)})",
                })

        multiplier = min(
            max(float(getattr(settings, "LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER", 0.2) or 0.2), 0.01),
            1.0,
        )
        caution_text = ""
        if mode == "PROBATION" and probation_cautions:
            caution_text = " · " + " / ".join(item["reason"] for item in probation_cautions)
        return {
            "action": "ALLOW",
            "warning": {
                "trigger": "CONSECUTIVE_LOSSES",
                "reason": f"{reason}, {mode} 복구 모드로 축소 진입{caution_text}",
                "recovery_mode": mode,
                "consecutive_losses": consecutive_losses,
                "max_losses": max_losses,
                "position_size_multiplier": multiplier,
                "max_order_krw": int(getattr(settings, "LOSS_STREAK_RECOVERY_MAX_ORDER_KRW", 0) or 0),
                "max_position_pct": float(getattr(settings, "LOSS_STREAK_RECOVERY_MAX_POSITION_PCT", 0.0) or 0.0),
                "current_holding_count": current_holding_count,
                "probation_cautions": probation_cautions if mode == "PROBATION" else [],
                "candidate_change_rate": candidate_change_rate,
                "candidate_pattern": candidate_pattern,
                "intraday_direction": intraday_direction,
                "intraday_vwap_position": intraday_vwap_position,
                "intraday_volume_trend": intraday_volume_trend,
            },
        }

    @staticmethod
    async def _reject(trigger: str, reason: str) -> dict:
        return {
            "approved": False,
            "reason": f"트레이딩 가드 차단: {reason}",
            "trigger": trigger,
            "kill_switched": False,
            "warnings": [],
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

    async def _evaluate_account_equity_drawdown(self, *, max_drawdown: float) -> dict:
        mode = str(getattr(settings, "ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE", "REPORT_ONLY") or "REPORT_ONLY").upper()
        if mode == "OFF":
            return {"action": "ALLOW"}

        account_drawdown = await self._get_account_equity_drawdown()
        if bool(account_drawdown.get("snapshot_stale_blocks_buy")):
            status = str(account_drawdown.get("snapshot_freshness_status") or "STALE")
            message = str(
                account_drawdown.get("snapshot_stale_message")
                or "계좌 스냅샷이 최신이 아니어서 신규 매수를 보류합니다."
            )
            return {
                "action": "BLOCK",
                "reason": f"계좌 스냅샷 최신성 부족({status}): {message}",
            }

        if not account_drawdown.get("available"):
            return {"action": "ALLOW"}

        drawdown_pct = float(account_drawdown.get("drawdown_pct") or 0.0)
        block_threshold = self._positive_threshold(
            getattr(settings, "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT", 0.0),
            fallback=max_drawdown,
        )
        kill_threshold = self._positive_threshold(
            getattr(settings, "ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT", 0.0),
            fallback=max(block_threshold, max_drawdown),
        )
        report_threshold = block_threshold or max_drawdown

        if report_threshold <= 0 or drawdown_pct > -report_threshold:
            return {"action": "ALLOW"}

        reason = (
            f"계좌 총자산 일중 손실 한도 초과 "
            f"({drawdown_pct:.2f}% <= -{report_threshold:.2f}%, "
            f"{float(account_drawdown.get('asset_delta') or 0.0):+,.0f}원)"
        )
        warning = {
            "trigger": "ACCOUNT_EQUITY_DRAWDOWN",
            "reason": reason,
            "drawdown_pct": drawdown_pct,
            "asset_delta": float(account_drawdown.get("asset_delta") or 0.0),
            "baseline_total_asset": float(account_drawdown.get("baseline_total_asset") or 0.0),
        }

        if mode == "REPORT_ONLY":
            return {"action": "WARN", "warning": warning}
        if mode == "KILL_SWITCH" and kill_threshold > 0 and drawdown_pct <= -kill_threshold:
            return {"action": "KILL_SWITCH", "reason": reason}
        if mode in {"BLOCK_BUY", "KILL_SWITCH"}:
            return {"action": "BLOCK", "reason": reason}
        return {"action": "WARN", "warning": warning}

    @staticmethod
    def _positive_threshold(value: float | int | None, *, fallback: float) -> float:
        threshold = abs(float(value or 0.0))
        if threshold > 0:
            return threshold
        return abs(float(fallback or 0.0))

    def _evaluate_llm_runtime_health(self) -> dict:
        if not bool(getattr(settings, "BUY_GUARD_LLM_RUNTIME_BLOCK_ENABLED", True)):
            return {"action": "ALLOW"}

        try:
            from analysis.llm.llm_factory import llm_factory

            status = llm_factory.get_llm_status()
        except Exception:
            return {"action": "ALLOW"}

        providers = {
            str(item.get("id") or "").upper(): item
            for item in status.get("available_providers", [])
            if isinstance(item, dict)
        }
        selected = {
            str((status.get("tier1") or {}).get("provider") or "").upper(),
            str((status.get("tier2") or {}).get("provider") or "").upper(),
        }
        selected.discard("")

        for provider_id in selected:
            runtime = (providers.get(provider_id) or {}).get("runtime") or {}
            if not isinstance(runtime, dict):
                continue
            if runtime.get("cooldown_active"):
                reason = runtime.get("last_failure_reason") or "최근 LLM 호출 실패"
                remaining = int(runtime.get("disabled_for_sec") or 0)
                return {
                    "action": "BLOCK",
                    "reason": f"{provider_id} 런타임 cooldown 중 신규 매수 보류 ({remaining}s 남음): {reason}",
                }
        return {"action": "ALLOW"}

    async def _get_account_equity_drawdown(self) -> dict:
        async with AsyncSessionLocal() as session:
            summary = await pnl_truth_service.build_summary(session)

        baseline_total_asset = float(summary.get("baseline_total_asset") or 0.0)
        total_asset = float(summary.get("total_asset") or 0.0)
        if baseline_total_asset <= 0 or total_asset <= 0:
            return {
                "available": False,
                "drawdown_pct": 0.0,
                "asset_delta": 0.0,
                "baseline_total_asset": baseline_total_asset,
                "snapshot_freshness_status": summary.get("snapshot_freshness_status"),
                "snapshot_stale_blocks_buy": summary.get("snapshot_stale_blocks_buy"),
                "snapshot_stale_message": summary.get("snapshot_stale_message"),
            }

        asset_delta = float(summary.get("total_asset_delta") or 0.0)
        return {
            "available": True,
            "drawdown_pct": (asset_delta / baseline_total_asset) * 100.0,
            "asset_delta": asset_delta,
            "baseline_total_asset": baseline_total_asset,
            "latest_snapshot_at": summary.get("latest_snapshot_at"),
            "snapshot_age_sec": summary.get("snapshot_age_sec"),
            "snapshot_freshness_status": summary.get("snapshot_freshness_status"),
            "snapshot_stale_blocks_buy": summary.get("snapshot_stale_blocks_buy"),
            "snapshot_stale_message": summary.get("snapshot_stale_message"),
        }

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
