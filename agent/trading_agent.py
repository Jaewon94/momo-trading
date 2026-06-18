"""AI Trading Agent 메인 루프 - 장중: 스캔→판단→분석→매매 / 장외: 성과 리뷰→피드백 학습"""
import asyncio
import json
import time as _time
from collections.abc import Callable

import pandas as pd
from loguru import logger

from agent.decision_maker import decision_maker
from agent.market_scanner import market_scanner
from agent.order_reservation import OrderReservationDecision, OrderReservationLedger
from analysis.chart_analyzer import ChartAnalysisResult, chart_analyzer
from analysis.feedback.context_builder import FeedbackContextBuilder
from analysis.llm.llm_factory import llm_factory
from analysis.llm.prompts.daily_plan import DAILY_PLAN_PROMPT, DAILY_PLAN_SYSTEM
from analysis.llm.prompts.final_review import FINAL_REVIEW_PROMPT, FINAL_REVIEW_SYSTEM
from analysis.llm.prompts.stock_analysis import STOCK_ANALYSIS_PROMPT, STOCK_ANALYSIS_SYSTEM
from core.config import settings
from core.database import AsyncSessionLocal
from core.events import Event, EventType, event_bus
from realtime.event_detector import event_detector
from scheduler.market_calendar import market_calendar
from services.activity_logger import activity_logger
from services.ai_skip_metric_service import ai_skip_metric_service
from services.decision_event_service import decision_event_service
from services.deterministic_final_gate_service import deterministic_final_gate_service
from services.deterministic_prompt_context_service import deterministic_prompt_context_service
from services.deterministic_tier1_fast_gate_service import deterministic_tier1_fast_gate_service
from services.news_gate_rollout_service import news_gate_rollout_service
from services.news_context_service import news_context_service
from services.pre_analysis_gate_service import pre_analysis_gate_service
from services.runtime_reconfiguration_service import runtime_reconfiguration_service
from services.tier1_analysis_cache_service import tier1_analysis_cache_service
from strategy.aggressive_short import AggressiveShortStrategy
from strategy.base import strategy_profile_metadata
from strategy.exposure_policy import ExposureAlignmentDecision, resolve_aggressive_exposure_alignment
from strategy.horizon_scan_policy import horizon_scan_profile, normalize_scan_horizon
from strategy.policy.engine import TradingPolicyEngine
from strategy.policy.trace import (
    with_policy_trace,
)
from strategy.risk_manager import risk_manager
from strategy.signal import TradeSignal
from strategy.stable_short import StableShortStrategy
from strategy.trade_horizon import TradeHorizon, decide_trade_horizon
from strategy.position_exit_policy import (
    is_loss_protective_stop,
    is_profit_protection_stop,
    soft_loss_stop_min_hold_block_reason,
    staged_stop_loss_exit_decision,
    strategic_exit_min_hold_block_reason,
    trade_horizon_from_result,
    trade_notes_dict,
)
from services.news_signal_service import news_signal_service
from trading.adapters.base import BrokerAdapter
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType, LLMTier, Market, OrderSide, OrderType, SignalAction, SignalUrgency
from trading.models import MCPResponse, OrderRequest
from trading.symbols import normalize_krx_symbol


class TradingAgent:
    """
    AI 트레이딩 에이전트 — 장 시간에 맞춰 자동 운영

    장중: WebSocket 실시간 시세 → 이벤트 감지 → 즉시 분석/매매
    장외: 오늘 성과 리뷰 + 피드백 학습
    """

    def __init__(self, broker_adapter: BrokerAdapter | None = None):
        self.strategies = {
            "STABLE_SHORT": StableShortStrategy(),
            "AGGRESSIVE_SHORT": AggressiveShortStrategy(),
        }
        self._broker_adapter = broker_adapter or get_broker_adapter()
        self.policy_engine = TradingPolicyEngine(
            pre_gate_service=pre_analysis_gate_service,
            fast_gate_service=deterministic_tier1_fast_gate_service,
            final_gate_service=deterministic_final_gate_service,
            news_rollout_service=news_gate_rollout_service,
            news_service=news_signal_service,
            session_factory=AsyncSessionLocal,
            exposure_alignment_resolver=resolve_aggressive_exposure_alignment,
            risk_manager_service=risk_manager,
        )
        self._running = False
        self._active_trading_rules: dict = {}  # 활성 트레이딩 규칙 (프리마켓에서 로드)
        self._cycle_lock = asyncio.Lock()  # 사이클 동시 실행 방지
        self._last_cycle_time = None
        # 실시간 이벤트 중복 분석 방지 (종목별 쿨다운)
        self._analyzing: set[str] = set()
        self._cooldowns: dict[str, float] = {}  # symbol -> last_trigger_time
        self.EVENT_COOLDOWN_SEC = 60  # 동일 종목 재분석 최소 간격 (초)
        # 사이클 내 시장 컨텍스트 캐시 (Tier1/Tier2에 전달)
        self._market_context: str = ""
        # 시장 국면 (전략/리스크에 전달)
        self._market_regime: str = ""
        # 데이트레이딩 컨텍스트 캐시 (시간/손익/매매성적)
        self._trading_context: str = ""
        # 데이트레이딩 일일 기준 자산 (손익 계산용)
        self._daily_start_balance: float = 0.0
        # Claude Code 세션 ID (장중 → 장외 이어받기용)
        self._last_session_id: str | None = None
        # 종목코드 → 종목명 캐시 (WebSocket 이벤트에서 종목명 표시용)
        self._symbol_names: dict[str, str] = {}
        # 주문 가능 현금 캐시와 동시성 보호
        self._available_cash: float = 0.0
        self._cash_lock = asyncio.Lock()
        # 이중 매도 방지: 매도 진행 중인 종목 잠금
        self._selling: set[str] = set()
        self._sell_lock = asyncio.Lock()

    async def start(self) -> None:
        """에이전트 시작 - 실시간 이벤트 구독"""
        self._running = True
        event_bus.subscribe(EventType.VOLUME_SPIKE, self._on_market_event)
        event_bus.subscribe(EventType.PRICE_SURGE, self._on_market_event)
        event_bus.subscribe(EventType.PRICE_DROP, self._on_market_event)
        event_bus.subscribe(EventType.STOP_LOSS_HIT, self._on_stop_loss)
        event_bus.subscribe(EventType.TAKE_PROFIT_HIT, self._on_take_profit)
        event_bus.subscribe(EventType.NEW_NEWS_ITEM, self._on_news_item)
        logger.debug("AI Trading Agent 시작 — 실시간 이벤트 구독 활성화")

    async def stop(self) -> None:
        """에이전트 중지"""
        self._running = False
        self._analyzing.clear()
        self._selling.clear()
        logger.debug("AI Trading Agent 중지")

    async def _acquire_sell(self, symbol: str) -> bool:
        """매도 잠금 획득 — 이미 매도 중이면 False"""
        symbol = normalize_krx_symbol(symbol)
        async with self._sell_lock:
            if symbol in self._selling:
                logger.debug("[{}] 이미 매도 진행 중 → 중복 매도 차단", symbol)
                return False
            self._selling.add(symbol)
            return True

    def _release_sell(self, symbol: str) -> None:
        """매도 잠금 해제"""
        self._selling.discard(normalize_krx_symbol(symbol))

    async def _take_profit_min_hold_block_reason(self, symbol: str) -> str | None:
        try:
            from repositories.trade_result_repository import TradeResultRepository
            from util.time_util import now_kst

            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                trade_result = await repo.get_open_buy(symbol)
            if not trade_result:
                return None

            horizon = trade_horizon_from_result(trade_result)
            return strategic_exit_min_hold_block_reason(
                trade_result,
                settings=settings,
                horizon=horizon,
                exit_scope="profit",
                observed_at=now_kst(),
            )
        except Exception as exc:
            logger.warning("익절 최소 보유시간 확인 실패 ({}): {}", symbol, str(exc))
            return None

    async def _stop_loss_min_hold_block_reason(
        self,
        symbol: str,
        *,
        stop_loss_price: float,
        current_price: float,
    ) -> str | None:
        try:
            from repositories.trade_result_repository import TradeResultRepository
            from util.time_util import now_kst

            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                trade_result = await repo.get_open_buy(symbol)
            if not trade_result:
                return None

            entry_price = self._optional_float(getattr(trade_result, "entry_price", None)) or 0.0
            horizon = trade_horizon_from_result(trade_result)
            default_stop_pct = self._default_stop_loss_pct(horizon)
            observed_at = now_kst()
            pnl_rate = None
            if entry_price > 0 and current_price > 0:
                pnl_rate = (current_price - entry_price) / entry_price * 100

            if is_profit_protection_stop(stop_loss_price, entry_price):
                if pnl_rate is not None and pnl_rate <= default_stop_pct:
                    return None
                return strategic_exit_min_hold_block_reason(
                    trade_result,
                    settings=settings,
                    horizon=horizon,
                    exit_scope="profit",
                    observed_at=observed_at,
                )

            if is_loss_protective_stop(stop_loss_price, entry_price) and pnl_rate is not None:
                return soft_loss_stop_min_hold_block_reason(
                    trade_result,
                    settings=settings,
                    horizon=horizon,
                    pnl_rate=pnl_rate,
                    default_stop_loss_pct=default_stop_pct,
                    observed_at=observed_at,
                )

            return None
        except Exception as exc:
            logger.warning("손절 이벤트 최소 보유시간 확인 실패 ({}): {}", symbol, str(exc))
            return None

    def _resolve_name(self, symbol: str) -> str:
        """종목코드 → 종목명 반환 (캐시에 없으면 코드 그대로)"""
        normalized = normalize_krx_symbol(symbol)
        return self._symbol_names.get(symbol) or self._symbol_names.get(normalized) or normalized

    async def _record_ai_skip_decision_event(
        self,
        *,
        stock_info: dict,
        cycle_id: str | None,
        decision_stage: str,
        source: str,
        reason_code: str,
        final_action: str,
        reference_price: float | None,
        reason: str,
        tier1_decision: str = "SKIP",
        confidence: float | None = None,
        metadata: dict | None = None,
    ) -> None:
        """AI skip gate도 후보별 forward return 라벨링 대상으로 남긴다."""
        try:
            symbol = normalize_krx_symbol(str(stock_info.get("symbol", "")))
            await decision_event_service.record_event(
                cycle_id=cycle_id,
                symbol=symbol,
                stock_name=str(stock_info.get("name") or symbol),
                market=str(stock_info.get("market") or "KRX"),
                decision_stage=decision_stage,
                source=source,
                strategy_type=str(stock_info.get("strategy_type") or ""),
                scanner_score=stock_info.get("scanner_score") or stock_info.get("score"),
                tier1_decision=tier1_decision,
                risk_gate_result=reason_code,
                final_action=final_action,
                confidence=confidence if confidence is not None else stock_info.get("confidence"),
                reference_price=reference_price,
                provider="DETERMINISTIC",
                model=source.upper(),
                status="RECORDED",
                reason=reason,
                metadata={
                    "ai_skipped": True,
                    "reason_code": reason_code,
                    "source": source,
                    "stock_info": {
                        "trigger": stock_info.get("trigger"),
                        "strategy_type": stock_info.get("strategy_type"),
                    },
                    **(metadata or {}),
                },
            )
        except Exception as exc:
            logger.debug("AI skip decision event 기록 실패 (무시): {}", str(exc))

    @staticmethod
    def _deterministic_tier1_fast_gate_mode() -> str:
        """Return OFF/SHADOW/ENFORCE while preserving the legacy boolean setting."""
        configured = str(getattr(settings, "DETERMINISTIC_TIER1_FAST_GATE_MODE", "") or "").upper()
        if configured in {"OFF", "SHADOW", "ENFORCE"}:
            return configured
        return "ENFORCE" if bool(getattr(settings, "DETERMINISTIC_TIER1_FAST_GATE_ENABLED", True)) else "OFF"

    async def _record_tier1_fast_gate_shadow_decision(
        self,
        *,
        stock_info: dict,
        cycle_id: str | None,
        fast_gate,
        reference_price: float | None,
    ) -> None:
        """Record deterministic Tier1 gate output without changing live decisions."""
        try:
            symbol = normalize_krx_symbol(str(stock_info.get("symbol", "")))
            action = str(getattr(fast_gate, "action", "") or "").upper()
            code = str(getattr(fast_gate, "code", "") or "UNKNOWN").upper()
            detail = dict(getattr(fast_gate, "detail", {}) or {})
            await decision_event_service.record_event(
                cycle_id=cycle_id,
                symbol=symbol,
                stock_name=str(stock_info.get("name") or symbol),
                market=str(stock_info.get("market") or "KRX"),
                decision_stage="DETERMINISTIC_TIER1_FAST_GATE_SHADOW",
                source="deterministic_tier1_fast_gate",
                strategy_type=str(stock_info.get("strategy_type") or ""),
                scanner_score=stock_info.get("scanner_score") or stock_info.get("score"),
                tier1_decision=action or None,
                risk_gate_result=code,
                final_action=f"SHADOW_{action or 'UNKNOWN'}",
                confidence=stock_info.get("confidence"),
                reference_price=reference_price,
                provider="DETERMINISTIC",
                model="deterministic_tier1_fast_gate",
                status="RECORDED",
                reason=str(getattr(fast_gate, "reason", "") or ""),
                metadata=with_policy_trace(
                    {
                        "ai_shadow": True,
                        "shadow_policy": "TIER1_FAST_GATE",
                        "would_skip_tier1": bool(getattr(fast_gate, "should_skip_tier1", False)),
                        "score": getattr(fast_gate, "score", None),
                        "reason_code": code,
                        **detail,
                    },
                    self.policy_engine.decision_from_tier1_fast_gate(fast_gate, mode="SHADOW"),
                ),
            )
        except Exception as exc:
            logger.debug("Tier1 fast gate shadow decision event 기록 실패 (무시): {}", str(exc))

    async def run_cycle(
        self,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
        scan_horizon: str | None = None,
    ) -> dict:
        """에이전트 1회 실행 사이클 — 장중이면 매매, 장외면 리뷰"""
        if runtime_reconfiguration_service.is_reconfiguring():
            logger.warning("런타임 설정 적용 중 — 신규 사이클 트리거 무시")
            return {"skipped": True, "reason": "runtime_reconfiguring"}

        if self._cycle_lock.locked():
            logger.warning("사이클 이미 실행 중 — 중복 트리거 무시")
            return {"skipped": True, "reason": "cycle_already_running"}

        async with self._cycle_lock:
            if market_calendar.is_krx_trading_hours():
                # 데이트레이딩 모드: 매수 마감 시간 이후 신규 매수 차단
                # 스윙 모드: 오버나이트 보유 가능 → 장 마감(15:20)까지 매수 허용
                if settings.DAY_TRADING_ONLY:
                    from datetime import time as _time
                    from util.time_util import now_kst
                    cutoff = _time(settings.BUY_CUTOFF_HOUR, settings.BUY_CUTOFF_MINUTE)
                    if now_kst().time() >= cutoff:
                        logger.debug("매수 마감 시간({}) 경과 → 신규 매매 사이클 스킵", cutoff)
                        await activity_logger.log(
                            ActivityType.CYCLE, ActivityPhase.COMPLETE,
                            f"\u23f0 매수 마감({cutoff.strftime('%H:%M')}) — "
                            "신규 매수 차단, 보유종목 모니터링만 유지",
                        )
                        self._last_cycle_time = now_kst()
                        return {"skipped": True, "reason": "buy_cutoff"}
                trading_cycle_kwargs = {
                    "manual_provider_override": manual_provider_override,
                    "manual_model_override": manual_model_override,
                }
                if scan_horizon is not None:
                    trading_cycle_kwargs["scan_horizon"] = scan_horizon
                return await self._run_trading_cycle(**trading_cycle_kwargs)
            else:
                return await self._run_after_hours_cycle(
                    manual_provider_override=manual_provider_override,
                    manual_model_override=manual_model_override,
                )

    async def wait_until_idle(
        self,
        *,
        timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.1,
    ) -> bool:
        deadline = _time.time() + max(float(timeout_sec), 0.0)
        interval = max(float(poll_interval_sec), 0.01)

        while True:
            cycle_idle = (
                not self._cycle_lock.locked()
                and not self._analyzing
                and not self._selling
            )
            if cycle_idle and not decision_maker.has_inflight_confirms():
                return True
            if _time.time() >= deadline:
                # 사이클은 끝났지만 체결확인 태스크가 남아 있으면 잔여 시간으로 한 번 더 드레인 시도
                if cycle_idle and decision_maker.has_inflight_confirms():
                    return await decision_maker.wait_for_inflight_confirms(timeout_sec=interval)
                return False
            await asyncio.sleep(interval)

    async def _run_trading_cycle(
        self,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
        scan_horizon: str | None = None,
    ) -> dict:
        """장중 사이클: 스캔 → 분석 → 매매"""
        scan_horizon_key = normalize_scan_horizon(scan_horizon)
        scan_profile = horizon_scan_profile(scan_horizon_key)
        # 사용 중인 provider가 Claude인 경우 세션 시작, 아니면 no-op
        llm_factory.start_session()

        cycle_id = activity_logger.start_cycle()
        cycle_timer = activity_logger.timer()

        logger.info("=== Agent 장중 사이클 시작 ({}) ===", scan_profile.label)
        await event_bus.publish(Event(
            type=EventType.AGENT_CYCLE_START, source="trading_agent",
        ))
        await activity_logger.log(
            ActivityType.CYCLE, ActivityPhase.START,
            f"\U0001f504 장중 매매 사이클 시작 ({scan_horizon_key})",
            cycle_id=cycle_id,
        )

        results = {
            "scan_horizon": scan_horizon_key,
            "scan_horizon_label": scan_profile.label,
            "scanned": 0,
            "analyzed": 0,
            "signals": 0,
            "executed": 0,
            "selected_symbols": [],
        }

        # AI 자율 한도 결정
        dynamic_limits = None
        if settings.AI_RISK_TUNING_ENABLED:
            try:
                from strategy.ai_risk_tuner import ai_risk_tuner
                dynamic_limits = await ai_risk_tuner.compute_limits(
                    risk_appetite=settings.RISK_APPETITE,
                    cycle_id=cycle_id,
                )
            except Exception as e:
                logger.warning("AI 한도 결정 실패, 기본값 사용: {}", str(e))

        try:
            # 0. 포트폴리오 스냅샷 (스캔 전 현금 확인, MCP 1회)
            snapshot = {
                "cash": 0, "total_asset": 0,
                "holding_count": 0, "today_trade_count": 0,
            }
            try:
                snapshot = await self._build_portfolio_snapshot()
            except RuntimeError:
                from util.time_util import now_kst

                logger.error("계좌 조회 실패 → 매매 사이클 중단")
                await activity_logger.log(
                    ActivityType.CYCLE, ActivityPhase.ERROR,
                    "🛑 계좌 조회 실패 → 매매 사이클 중단 (데이터 신뢰성 보호)",
                    cycle_id=cycle_id,
                )
                self._last_cycle_time = now_kst()
                return results
            except Exception as e:
                logger.warning("포트폴리오 스냅샷 조회 실패, 기본값 사용: {}", str(e))

            if self._daily_start_balance == 0 and snapshot["total_asset"] > 0:
                self._daily_start_balance = snapshot["total_asset"]

            # 현금 부족 판정 → 매수만 차단, 스캔+매도 분석은 계속 진행
            eff_min_order_amount = (
                (dynamic_limits.get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
                 if dynamic_limits else settings.MIN_BUY_QUANTITY)
                * 1000
            )
            min_price_ref = snapshot.get("min_holding_price", 0)
            buy_blocked = False
            if min_price_ref > 0 and snapshot["cash"] < min_price_ref:
                buy_blocked = True
                logger.info(
                    "현금 부족 → 매수 차단, 매도 분석 계속: {:,.0f}원 < 최소 보유주가 {:,.0f}원",
                    snapshot["cash"], min_price_ref,
                )
                await activity_logger.log(
                    ActivityType.CYCLE, ActivityPhase.PROGRESS,
                    f"💰 현금 부족 → 매수 차단, 매도 분석 계속 ({snapshot['cash']:,.0f}원 < 최소 보유주가 {min_price_ref:,.0f}원)",
                    cycle_id=cycle_id,
                )

            # 1. 시장 스캔 + 종목 선별 (통합 1회 LLM 호출)
            scan_result = await market_scanner.scan(
                cycle_id=cycle_id,
                dynamic_limits=dynamic_limits,
                horizon=scan_horizon_key,
            )
            candidates = scan_result.get("selected", [])
            results["scanned"] = len(candidates)

            if not candidates:
                from util.time_util import now_kst

                logger.debug("스캔 결과 선정 종목 없음, 사이클 종료")
                await activity_logger.log(
                    ActivityType.CYCLE, ActivityPhase.COMPLETE,
                    "\u2705 사이클 종료: 선정 종목 없음",
                    cycle_id=cycle_id,
                    execution_time_ms=activity_logger.elapsed_ms(cycle_timer),
                )
                self._last_cycle_time = now_kst()
                return results

            # 종목명 캐시 갱신 (스캔 결과)
            for c in candidates:
                sym = c.get("symbol", "")
                nm = c.get("name", "")
                if sym and nm and nm != sym:
                    self._symbol_names[sym] = nm

            # 1b. 시장 국면 + 컨텍스트 빌드 (Tier1/Tier2/전략/리스크에 전달)
            self._market_regime = scan_result.get("market_regime", "")
            self._market_context = self._build_market_context(scan_result)

            # 1c. 데이트레이딩 컨텍스트 빌드 (시간/손익/매매성적)
            self._trading_context = await self._build_trading_context()

            # 선정 종목은 분석/매매 대상으로 유지하고, 실시간 감시는 더 넓은 후보군을 사용한다.
            monitor_candidates = self._build_monitor_candidates(scan_result, candidates)
            results["selected_symbols"] = self._symbols_from_candidates(candidates)
            results["monitor_symbols"] = self._symbols_from_candidates(monitor_candidates)

            # AI가 결정한 모니터링 임계값을 event_detector에 설정
            self._apply_scan_thresholds(monitor_candidates)

            # 2. 후보 종목별 심층 분석 + 전략 평가 + 매매 (병렬)
            # 세션 일시 중지 → 각 종목 분석은 독립 호출 (병렬 가능)
            # 스크리닝 맥락은 self._market_context로 프롬프트에 전달됨
            paused_sid = llm_factory.pause_session()

            semaphore = asyncio.Semaphore(llm_factory.analysis_concurrency_limit())
            executed_count = 0
            reservation_ledger = OrderReservationLedger(starting_cash=snapshot.get("cash", 0))

            holding_syms = {
                normalize_krx_symbol(item) for item in snapshot.get("holding_symbols", [])
            }

            async def _analyze_with_limit(stock_info: dict) -> dict:
                nonlocal executed_count
                async with semaphore:
                    # 매도 방향 또는 보유종목은 매수가능 검사 면제
                    direction = stock_info.get("direction", "BUY")
                    symbol = stock_info.get("symbol", "")
                    is_holding = symbol in holding_syms
                    min_qty = (
                        (dynamic_limits or {}).get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
                    )

                    if direction != "SELL" and not is_holding:
                        if buy_blocked:
                            return {"skipped": True, "reason": "현금 부족 (매수 차단)"}
                        bp = await self._broker_adapter.get_buying_power(symbol)
                        if bp.success and bp.max_qty < min_qty:
                            logger.info(
                                "[{}] 매수가능수량 부족으로 스킵: {}주 < 최소 {}주",
                                symbol, bp.max_qty, min_qty,
                            )
                            return {"skipped": True, "reason": f"매수가능수량 부족 ({bp.max_qty}주)"}
                        stock_info["_buying_power"] = bp.model_dump()

                    r = await self._analyze_and_trade(
                        stock_info, cycle_id,
                        dynamic_limits=dynamic_limits,
                        portfolio_snapshot=snapshot,
                        order_reservation_ledger=reservation_ledger,
                        executed_count_ref=lambda: executed_count,
                        manual_provider_override=manual_provider_override,
                        manual_model_override=manual_model_override,
                    )
                    if r.get("executed"):
                        executed_count += 1
                    return r

            all_results = await asyncio.gather(
                *[_analyze_with_limit(s) for s in candidates],
                return_exceptions=True,
            )

            # 병렬 분석 완료 → 세션 재개 (리포트/후속 처리용)
            if paused_sid:
                llm_factory.resume_session(paused_sid)

            for i, r in enumerate(all_results):
                if isinstance(r, Exception):
                    sym = candidates[i].get("symbol", "?")
                    logger.error("종목 분석 오류 ({}): {}", sym, str(r))
                    await activity_logger.log(
                        ActivityType.TIER1_ANALYSIS, ActivityPhase.ERROR,
                        f"\u274c [{sym}] 분석 오류: {str(r)[:100]}",
                        cycle_id=cycle_id,
                        symbol=sym,
                        error_message=str(r),
                    )
                elif isinstance(r, dict):
                    results["analyzed"] += 1
                    if r.get("signal"):
                        results["signals"] += 1
                    if r.get("executed"):
                        results["executed"] += 1

        except Exception as e:
            err_msg = str(e) or repr(e)
            logger.error("Agent 사이클 오류 ({}): {}", type(e).__name__, err_msg)
            await activity_logger.log(
                ActivityType.CYCLE, ActivityPhase.ERROR,
                f"\u274c 사이클 오류: [{type(e).__name__}] {err_msg[:100]}",
                cycle_id=cycle_id,
                error_message=err_msg,
            )

        from util.time_util import now_kst
        self._last_cycle_time = now_kst()
        elapsed = activity_logger.elapsed_ms(cycle_timer)

        await event_bus.publish(Event(
            type=EventType.AGENT_CYCLE_END, data=results, source="trading_agent",
        ))
        await activity_logger.log(
            ActivityType.CYCLE, ActivityPhase.COMPLETE,
            f"\u2705 사이클 완료: 분석 {results['analyzed']}건, "
            f"추천 {results['signals']}건, 소요 {elapsed / 1000:.1f}초",
            cycle_id=cycle_id,
            detail=results,
            execution_time_ms=elapsed,
        )
        # 세션 종료 (세션 ID 보존 — 장외 사이클에서 재개 가능)
        self._last_session_id = llm_factory.end_session()

        logger.info("=== Agent 장중 사이클 종료: {} ===", results)
        return results

    async def _fetch_symbol_market_data(
        self,
        symbol: str,
        daily_count: int = 60,
    ) -> tuple[MCPResponse, MCPResponse, MCPResponse]:
        """브로커 어댑터를 통해 종목 분석용 시세/차트 데이터를 조회한다."""
        resolved_daily_count = max(int(daily_count or 60), 20)
        quote_result, daily_result, minute_result = await asyncio.gather(
            self._broker_adapter.get_current_price(symbol, Market.KRX),
            self._broker_adapter.get_daily_candles(symbol, count=resolved_daily_count, market=Market.KRX),
            self._broker_adapter.get_intraday_candles(symbol, interval="5", market=Market.KRX),
            return_exceptions=True,
        )
        return (
            self._wrap_quote_result(quote_result),
            self._wrap_candle_result(daily_result, time_key="date"),
            self._wrap_candle_result(minute_result, time_key="time"),
        )

    @staticmethod
    def _wrap_quote_result(result: object) -> MCPResponse:
        if isinstance(result, Exception):
            return MCPResponse(success=False, error=str(result))
        return MCPResponse(success=True, data=result.model_dump(mode="json"))

    @staticmethod
    def _wrap_candle_result(result: object, *, time_key: str) -> MCPResponse:
        if isinstance(result, Exception):
            return MCPResponse(success=False, error=str(result))
        return MCPResponse(success=True, data={
            "prices": [
                {
                    time_key: candle.time_key,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in result
            ]
        })

    async def _build_portfolio_snapshot(self) -> dict:
        """브로커 어댑터 기준 포트폴리오 스냅샷을 만든다."""
        balance, holdings = await asyncio.gather(
            self._broker_adapter.get_balance(),
            self._broker_adapter.get_holdings(),
        )
        if not balance.is_valid:
            raise RuntimeError("계좌 조회 실패")
        holding_symbols = [normalize_krx_symbol(holding.symbol) for holding in holdings]
        holding_quantities = {
            normalize_krx_symbol(holding.symbol): int(getattr(holding, "quantity", 0) or 0)
            for holding in holdings
        }
        snapshot = {
            "cash": balance.cash,
            "total_asset": balance.total_asset,
            "stock_value": getattr(balance, "stock_value", 0.0),
            "current_exposure_pct": (
                (float(getattr(balance, "stock_value", 0.0) or 0.0) / float(balance.total_asset) * 100.0)
                if float(balance.total_asset or 0.0) > 0
                else 0.0
            ),
            "holding_count": len(holdings),
            "today_trade_count": await self._get_today_trade_count(),
            "holding_symbols": holding_symbols,
            "holding_quantities": holding_quantities,
        }
        async with self._cash_lock:
            self._available_cash = balance.cash
        return snapshot

    @staticmethod
    def _resolve_sell_quantity_from_snapshot(
        signal: TradeSignal,
        portfolio_snapshot: dict | None = None,
    ) -> int:
        symbol = normalize_krx_symbol(getattr(signal, "symbol", ""))
        holding_quantities = (portfolio_snapshot or {}).get("holding_quantities") or {}
        try:
            holding_qty = int(holding_quantities.get(symbol, 0) or 0)
        except (TypeError, ValueError):
            holding_qty = 0
        return max(holding_qty, 0)

    async def _lookup_current_price(self, symbol: str, market: str | Market = Market.KRX) -> float:
        """현재 브로커 어댑터 기준 실시간 현재가 조회"""
        try:
            market_enum = market if isinstance(market, Market) else Market(str(market).upper())
        except ValueError:
            market_enum = Market.KRX

        quote = await self._broker_adapter.get_current_price(symbol, market_enum)
        return float(quote.price or 0.0)

    async def _execute_exit_order(
        self,
        *,
        symbol: str,
        expected_price: float,
        exit_reason: str,
        quantity: int | None = None,
    ):
        """보유 수량 기준 시장가 매도 실행"""
        symbol = normalize_krx_symbol(symbol)
        holdings = await self._broker_adapter.get_holdings()
        holding = next(
            (item for item in holdings if normalize_krx_symbol(item.symbol) == symbol),
            None,
        )
        if not holding or holding.quantity <= 0:
            return None
        sell_quantity = int(holding.quantity if quantity is None else quantity)
        sell_quantity = min(max(sell_quantity, 0), int(holding.quantity))
        if sell_quantity <= 0:
            return None

        order_result = await self._broker_adapter.place_order(
            OrderRequest(
                symbol=symbol,
                market=Market.KRX,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=sell_quantity,
            )
        )
        if order_result.success and order_result.order_id:
            await decision_maker.confirm_and_record(
                symbol=symbol,
                side="SELL",
                order_id=order_result.order_id,
                quantity=sell_quantity,
                expected_price=expected_price,
                exit_reason=exit_reason,
            )
        return order_result

    @staticmethod
    def _target_horizon_hint(stock_info: dict) -> str | None:
        """Return scanner-supplied target horizon only when a candidate explicitly has one."""
        raw = (
            stock_info.get("target_horizon_hint")
            or stock_info.get("scan_horizon")
            or stock_info.get("target_horizon")
        )
        if raw is None or str(raw).strip() == "":
            return None
        return normalize_scan_horizon(str(raw))

    def _decide_candidate_horizon(
        self,
        *,
        stock_info: dict,
        strategy_type: str,
        price_resp: MCPResponse,
        analysis: dict,
    ) -> tuple[str, str]:
        """Use MID/LONG scanner intent when explicit; otherwise keep the existing horizon decider."""
        hinted_horizon = self._target_horizon_hint(stock_info)
        if hinted_horizon in {TradeHorizon.MID, TradeHorizon.LONG}:
            return hinted_horizon, "scan_profile"

        decided = decide_trade_horizon(
            strategy_type=strategy_type,
            trigger=str(stock_info.get("trigger", "")),
            change_rate=float(price_resp.data.get("change_rate", 0.0) if price_resp.data else 0.0),
            confidence=float(analysis.get("confidence", 0.0) or 0.0),
            market_regime=self._market_regime,
        )
        return decided, "trade_horizon_decider"

    async def _analyze_and_trade(
        self, stock_info: dict, cycle_id: str,
        dynamic_limits: dict | None = None,
        portfolio_snapshot: dict | None = None,
        order_reservation_ledger: OrderReservationLedger | None = None,
        executed_count_ref: Callable | None = None,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
    ) -> dict:
        """개별 종목 분석 → 전략 평가 → 매매 결정"""
        symbol = stock_info.get("symbol", "")
        name = stock_info.get("name", symbol)
        strategy_type = stock_info.get("strategy_type", "STABLE_SHORT")
        target_horizon_hint = self._target_horizon_hint(stock_info)
        analysis_horizon = target_horizon_hint or TradeHorizon.SHORT
        analysis_horizon_profile = horizon_scan_profile(analysis_horizon)

        # 종목명 캐시 갱신
        if symbol and name and name != symbol:
            self._symbol_names[symbol] = name

        result = {"symbol": symbol, "signal": False, "executed": False}

        # 피드백 하드 룰: 명시적 차단 모드에서만 LLM 분석 전에 매수 후보를 보류한다.
        try:
            async with AsyncSessionLocal() as session:
                from analysis.feedback.performance_tracker import PerformanceTracker
                tracker = PerformanceTracker(session)
                consecutive = await tracker.get_consecutive_losses()
                max_losses = int(getattr(settings, "MAX_CONSECUTIVE_LOSSES", 0) or 0)
                recovery_mode = str(
                    getattr(settings, "LOSS_STREAK_RECOVERY_MODE", "BLOCK_BUY") or "BLOCK_BUY"
                ).upper()
                if max_losses > 0 and consecutive >= max_losses:
                    direction = stock_info.get("direction", "BUY")
                    snap_holdings = [
                        normalize_krx_symbol(item)
                        for item in (portfolio_snapshot or {}).get("holding_symbols", [])
                    ]
                    if direction != "SELL" and symbol not in snap_holdings:
                        if recovery_mode == "BLOCK_BUY":
                            logger.warning(
                                "[손실 복구 가드] 연속 {}회 손실 → 매수 보류({}): {}",
                                consecutive,
                                recovery_mode,
                                symbol,
                            )
                            await activity_logger.log(
                                ActivityType.RISK_GATE, ActivityPhase.SKIP,
                                f"🛑 연속 {consecutive}회 손실 → 매수 보류 ({recovery_mode})",
                                cycle_id=cycle_id, symbol=symbol,
                            )
                            return result
                        logger.info(
                            "[손실 복구 가드] 연속 {}회 손실, {} 모드로 리스크 검사까지 진행: {}",
                            consecutive,
                            recovery_mode,
                            symbol,
                        )
                    else:
                        logger.debug(
                            "[손실 복구 가드] 연속 {}회 손실이지만 매도/보유종목 분석 허용: {}",
                            consecutive,
                            symbol,
                        )
        except Exception:
            pass

        if analysis_horizon_profile.daily_candle_count == 60:
            price_resp, daily_resp, minute_resp = await self._fetch_symbol_market_data(symbol)
        else:
            price_resp, daily_resp, minute_resp = await self._fetch_symbol_market_data(
                symbol,
                daily_count=analysis_horizon_profile.daily_candle_count,
            )

        current_price = 0
        if price_resp.success and price_resp.data:
            current_price = float(price_resp.data.get("price", price_resp.data.get("current_price", 0)))
        else:
            logger.warning("[{}] 현재가 조회 실패: {}", symbol, price_resp.error or "응답 없음")

        # 3b. DataFrame 변환 + 차트 종합 분석
        daily_df = pd.DataFrame()
        minute_df = None
        chart_result = ChartAnalysisResult()

        if daily_resp.success and daily_resp.data:
            daily_items = daily_resp.data.get("prices", daily_resp.data.get("items", []))
            if daily_items:
                daily_df = pd.DataFrame(daily_items)
                for col in ["open", "high", "low", "close"]:
                    if col in daily_df.columns:
                        daily_df[col] = pd.to_numeric(daily_df[col], errors="coerce")
                if "volume" in daily_df.columns:
                    daily_df["volume"] = pd.to_numeric(daily_df["volume"], errors="coerce")
            else:
                logger.warning("[{}] 일봉 응답은 성공이나 prices 비어있음", symbol)
        else:
            logger.warning("[{}] 일봉 조회 실패: {}", symbol, daily_resp.error or "응답 없음")

        if minute_resp.success and minute_resp.data:
            minute_items = minute_resp.data.get("prices", [])
            if minute_items:
                minute_df = pd.DataFrame(minute_items)
                for col in ["open", "high", "low", "close"]:
                    if col in minute_df.columns:
                        minute_df[col] = pd.to_numeric(minute_df[col], errors="coerce")
                if "volume" in minute_df.columns:
                    minute_df["volume"] = pd.to_numeric(minute_df["volume"], errors="coerce")

        if not daily_df.empty:
            chart_result = chart_analyzer.analyze(daily_df, minute_df)

        pre_gate_eval = self.policy_engine.evaluate_pre_analysis_gate(
            symbol=symbol,
            current_price=current_price,
            daily_df=daily_df,
            chart_result=chart_result,
            portfolio_snapshot=portfolio_snapshot,
            dynamic_limits=dynamic_limits,
        )
        pre_gate = pre_gate_eval.value
        # BEARISH_PRE_GATE(강한 하락 추세 하드 차단)는 단기 추세 관점이므로 SHORT에만 적용한다.
        # MID/LONG는 하락 추세 눌림목이 진입 기회일 수 있어 하드 차단 대신 LLM 판단까지 넘긴다.
        # (현금부족·데이터부족·지표불량 등 다른 차단 사유는 호라이즌 무관하게 유지)
        pre_gate_bearish_bypass = (
            not pre_gate.approved
            and pre_gate.code == "BEARISH_PRE_GATE"
            and analysis_horizon != TradeHorizon.SHORT
        )
        if pre_gate_bearish_bypass:
            logger.info(
                "[{}] BEARISH_PRE_GATE 우회 (호라이즌 {} → 단기 하락추세 하드차단 생략, LLM 분석 진행)",
                symbol, analysis_horizon,
            )
        if not pre_gate.approved and not pre_gate_bearish_bypass:
            pre_gate_policy = pre_gate_eval.decision
            if pre_gate.code == "INSUFFICIENT_CASH":
                available_cash = pre_gate.detail.get("available_cash", 0.0)
                min_buy_cost = pre_gate.detail.get("min_buy_cost", 0.0)
                logger.info(
                    "[{}] 현금 부족 → Tier1 스킵: {:,.0f}원 < {:,.0f}원/주",
                    symbol, available_cash, min_buy_cost,
                )
                message = (
                    f"💰 [{name}] 현금 부족으로 Tier1 스킵 "
                    f"({available_cash:,.0f}원 < {min_buy_cost:,.0f}원)"
                )
            elif pre_gate.code == "MISSING_CORE_MARKET_DATA":
                logger.warning("[{}] 현재가·일봉 모두 없음 → 분석 스킵", symbol)
                message = f"⚠️ [{name}] 데이터 부족으로 분석 스킵 (현재가·일봉 조회 실패)"
            elif pre_gate.code == "BEARISH_PRE_GATE":
                confidence = float(pre_gate.detail.get("confidence", 0.0) or 0.0)
                logger.info(
                    "[{}] 강한 하락 추세 → Tier1 스킵: 신뢰도 {:.0%}",
                    symbol, confidence,
                )
                message = (
                    f"📉 [{name}] 사전 게이트 차단 "
                    f"(강한 하락 추세, 신뢰도 {confidence:.0%})"
                )
            else:
                logger.info("[{}] PreAnalysisGate 차단: {}", symbol, pre_gate.code)
                message = f"⛔ [{name}] 사전 게이트 차단 ({pre_gate.code})"

            await activity_logger.log(
                ActivityType.TIER1_ANALYSIS, ActivityPhase.SKIP,
                message,
                cycle_id=cycle_id, symbol=symbol,
                detail=with_policy_trace(
                    {"pre_analysis_gate": pre_gate.code, **pre_gate.detail},
                    pre_gate_policy,
                ),
            )
            await ai_skip_metric_service.record(
                stage="PRE_ANALYSIS_GATE",
                reason_code=pre_gate.code,
                skipped_tier="TIER1",
                cycle_id=cycle_id,
                symbol=symbol,
                detail=pre_gate.detail,
            )
            await self._record_ai_skip_decision_event(
                stock_info=stock_info,
                cycle_id=cycle_id,
                decision_stage="PRE_ANALYSIS_GATE",
                source="pre_analysis_gate",
                reason_code=pre_gate.code,
                final_action="SKIP",
                reference_price=current_price,
                reason=message,
                metadata=with_policy_trace(pre_gate.detail, pre_gate_policy),
            )
            return result

        indicators = chart_result.indicators

        fast_gate = None  # IC 분석을 위해 통과한 trade의 notes에도 score를 저장한다
        fast_gate_mode = self._deterministic_tier1_fast_gate_mode()
        # Fast Gate는 장중 단기 지표(장중 VWAP·장중 거래량·당일 등락률·14:45 막판 매수 차단)로
        # 채점하므로 SHORT 후보에만 적용한다. MID/LONG는 이런 단기 신호로 거르면 눌림목 진입을
        # 차단하게 되므로 게이트를 건너뛰고 LLM 분석까지 모두 통과시킨다.
        # (MID/LONG 스캔은 빈도·후보가 적어 LLM 비용 영향이 미미하다.)
        if fast_gate_mode != "OFF" and analysis_horizon == TradeHorizon.SHORT:
            fast_gate_eval = self.policy_engine.evaluate_tier1_fast_gate(
                mode=fast_gate_mode,
                symbol=symbol,
                stock_info=stock_info,
                current_price=current_price,
                daily_df=daily_df,
                minute_df=minute_df,
                chart_result=chart_result,
                portfolio_snapshot=portfolio_snapshot,
                market_regime=self._market_regime,
                ignore_enabled=fast_gate_mode == "SHADOW",
            )
            fast_gate = fast_gate_eval.value
            fast_gate_policy = fast_gate_eval.decision
            if fast_gate_mode == "SHADOW":
                await self._record_tier1_fast_gate_shadow_decision(
                    stock_info=stock_info,
                    cycle_id=cycle_id,
                    fast_gate=fast_gate,
                    reference_price=current_price,
                )
            elif fast_gate.should_skip_tier1:
                await activity_logger.log(
                    ActivityType.TIER1_ANALYSIS,
                    ActivityPhase.SKIP,
                    f"⚡ [{name}] deterministic Tier1 fast gate: HOLD → LLM 스킵 "
                    f"(score {fast_gate.score:.1f}) | {fast_gate.reason[:100]}",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    detail=with_policy_trace(
                        {"deterministic_tier1_fast_gate": fast_gate.code, **fast_gate.detail},
                        fast_gate_policy,
                    ),
                    llm_tier="TIER1",
                    confidence=0,
                )
                await ai_skip_metric_service.record(
                    stage="DETERMINISTIC_TIER1_FAST_GATE",
                    reason_code=fast_gate.code,
                    skipped_tier="TIER1",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    detail=fast_gate.detail,
                )
                await self._record_ai_skip_decision_event(
                    stock_info=stock_info,
                    cycle_id=cycle_id,
                    decision_stage="DETERMINISTIC_TIER1_FAST_GATE",
                    source="deterministic_tier1_fast_gate",
                    reason_code=fast_gate.code,
                    final_action="HOLD",
                    reference_price=current_price,
                    reason=fast_gate.reason,
                    metadata=with_policy_trace(fast_gate.detail, fast_gate_policy),
                )
                return result

        # 3c. 피드백 컨텍스트 빌드
        feedback_context = "매매 이력 없음"
        try:
            async with AsyncSessionLocal() as session:
                builder = FeedbackContextBuilder(session)
                rsi_val = indicators.get("rsi_14")
                feedback_context = await builder.build_full_context(
                    strategy_type=strategy_type,
                    symbol=symbol,
                    current_rsi=rsi_val,
                )
        except Exception as e:
            logger.warning("피드백 컨텍스트 빌드 실패: {}", str(e))

        news_context_payload: dict = {}
        news_context_text = (
            f"### {analysis_horizon} 뉴스 보조 컨텍스트\n"
            "- 뉴스 컨텍스트 조회 전. 뉴스는 중립으로 간주하세요."
        )
        try:
            async with AsyncSessionLocal() as session:
                news_context_payload = await news_context_service.build_for_symbol(
                    session,
                    symbol=symbol,
                    name=name,
                    horizon=analysis_horizon,
                    max_items=analysis_horizon_profile.news_prompt_items,
                    lookback_hours=analysis_horizon_profile.news_lookback_hours,
                )
                news_context_text = str(news_context_payload.get("prompt") or news_context_text)
        except Exception as e:
            logger.warning("뉴스 보조 컨텍스트 빌드 실패 ({}): {}", symbol, str(e))
            news_context_payload = {
                "available": False,
                "tone": "CONTEXT_ERROR",
                "confidence_hint": 0.0,
                "items": [],
            }
            news_context_text = (
                f"### {analysis_horizon} 뉴스 보조 컨텍스트\n"
                "- 뉴스 컨텍스트 조회 실패. 뉴스는 중립으로 간주하고 차트/수급 중심으로 판단하세요."
            )

        cache_key = tier1_analysis_cache_service.build_key(
            symbol=symbol,
            strategy_type=strategy_type,
            current_price=current_price,
            chart_result=chart_result,
            portfolio_snapshot=portfolio_snapshot,
            market_regime=self._market_regime,
            feedback_context=feedback_context,
            news_context=news_context_text,
        )
        cache_allowed = not manual_provider_override and not manual_model_override
        analysis = tier1_analysis_cache_service.get(cache_key) if cache_allowed else None
        t1_elapsed = 0
        if analysis:
            await activity_logger.log(
                ActivityType.TIER1_ANALYSIS, ActivityPhase.COMPLETE,
                f"\U0001f4ca [{name}] Tier1 캐시 재사용: {analysis.get('recommendation', '')} "
                f"| 신뢰도 {(analysis.get('confidence') or 0):.0%}",
                cycle_id=cycle_id, symbol=symbol,
                detail={
                    "tier1_analysis_cache": "HIT",
                    "recommendation": analysis.get("recommendation"),
                    "confidence": analysis.get("confidence") or 0,
                },
                llm_provider=analysis.get("provider"),
                llm_tier="TIER1",
                execution_time_ms=0,
                confidence=analysis.get("confidence") or 0,
            )
            await ai_skip_metric_service.record(
                stage="TIER1_CACHE",
                reason_code="CACHE_HIT",
                skipped_tier="TIER1",
                cycle_id=cycle_id,
                symbol=symbol,
                detail={
                    "recommendation": analysis.get("recommendation"),
                    "confidence": analysis.get("confidence") or 0,
                },
            )
        else:
            # 3d. Tier 1 AI 심층 분석
            t1_timer = activity_logger.timer()
            await activity_logger.log(
                ActivityType.TIER1_ANALYSIS, ActivityPhase.START,
                f"\U0001f4ca [{name}] Tier1 분석 시작",
                cycle_id=cycle_id, symbol=symbol,
            )

            analysis = await self._tier1_analysis(
                symbol,
                name,
                current_price,
                chart_result,
                price_resp.data or {},
                feedback_context,
                market_context=self._market_context,
                trading_context=self._trading_context,
                news_context=news_context_text,
                deterministic_context=deterministic_prompt_context_service.build_tier1_context(
                    symbol=symbol,
                    strategy_type=strategy_type,
                    current_price=current_price,
                    chart_result=chart_result,
                    portfolio_snapshot=portfolio_snapshot,
                    market_regime=self._market_regime,
                    dynamic_limits=dynamic_limits,
                    target_horizon=target_horizon_hint,
                ),
                cycle_id=cycle_id,
                manual_provider_override=manual_provider_override,
                manual_model_override=manual_model_override,
            )
            t1_elapsed = activity_logger.elapsed_ms(t1_timer)
            if cache_allowed:
                tier1_analysis_cache_service.put(cache_key, analysis)

        if not analysis:
            await activity_logger.log(
                ActivityType.TIER1_ANALYSIS, ActivityPhase.COMPLETE,
                f"\U0001f4ca [{name}] Tier1: 분석 실패 (응답 파싱 불가)",
                cycle_id=cycle_id, symbol=symbol,
                llm_tier="TIER1",
                execution_time_ms=t1_elapsed,
            )
            return result

        analysis = self._normalize_tier1_decision(
            analysis,
            symbol=symbol,
            portfolio_snapshot=portfolio_snapshot,
        )
        recommendation = analysis.get("recommendation", "HOLD")

        # 스캔 파이프라인 SELL: 미보유 종목만 스킵, 보유 종목은 Tier2 리뷰 진행
        if recommendation == "SELL":
            is_holding = symbol in [
                normalize_krx_symbol(item)
                for item in (portfolio_snapshot or {}).get("holding_symbols", [])
            ]
            if not is_holding:
                reason = analysis.get("reason") or "AI SELL 추천"
                await activity_logger.log(
                    ActivityType.TIER1_ANALYSIS, ActivityPhase.COMPLETE,
                    f"\U0001f4ca [{name}] Tier1: SELL → 미보유 종목 매도 스킵 | {reason[:100]}",
                    cycle_id=cycle_id, symbol=symbol,
                    detail={
                        "recommendation": "SELL",
                        "reason": reason,
                        "confidence": analysis.get("confidence") or 0,
                    },
                    llm_provider=analysis.get("provider"),
                    llm_tier="TIER1",
                    execution_time_ms=t1_elapsed,
                    confidence=analysis.get("confidence") or 0,
                )
                return result
            # 보유종목 SELL → Tier2 리뷰 진행
            logger.info("[{}] 보유종목 SELL 추천 → Tier2 리뷰 진행", symbol)

        if recommendation == "HOLD":
            reason = analysis.get("reason") or analysis.get("summary", "판단 근거 없음")
            is_holding = symbol in [
                normalize_krx_symbol(item)
                for item in (portfolio_snapshot or {}).get("holding_symbols", [])
            ]
            active_thresholds = {}
            if is_holding:
                holding_horizon = decide_trade_horizon(
                    strategy_type=strategy_type,
                    trigger=str(stock_info.get("trigger", "")),
                    change_rate=float(price_resp.data.get("change_rate", 0.0) if price_resp.data else 0.0),
                    confidence=float(analysis.get("confidence", 0.0) or 0.0),
                    market_regime=self._market_regime,
                )
                active_thresholds = self._apply_trade_thresholds(
                    symbol,
                    analysis,
                    {},
                    current_price=current_price,
                    horizon=holding_horizon,
                    preserve_tighter_stop_loss=True,
                )
                protected_thresholds = await self._persist_open_position_thresholds(
                    symbol,
                    active_thresholds,
                    current_price=current_price,
                    horizon=holding_horizon,
                )
                if protected_thresholds != active_thresholds:
                    active_thresholds = protected_thresholds
                    event_detector.set_thresholds(symbol, **active_thresholds)
            position_action = str(analysis.get("position_action") or "HOLD").upper()
            threshold_suffix = ""
            if active_thresholds:
                threshold_suffix = " | 임계값 " + ", ".join(
                    f"{key}={float(value):,.0f}" if key != "trailing_stop_pct" else f"{key}={float(value):.1f}%"
                    for key, value in active_thresholds.items()
                )
            await activity_logger.log(
                ActivityType.TIER1_ANALYSIS, ActivityPhase.COMPLETE,
                f"\U0001f4ca [{name}] Tier1: {position_action} → "
                f"{'보유 관리' if is_holding else '스킵'} | {reason[:100]}{threshold_suffix}",
                cycle_id=cycle_id, symbol=symbol,
                detail={
                    "recommendation": "HOLD",
                    "entry_action": analysis.get("entry_action"),
                    "position_action": position_action,
                    "reason": reason,
                    "confidence": analysis.get("confidence") or 0,
                    "target_price": analysis.get("target_price"),
                    "stop_loss_price": analysis.get("stop_loss_price"),
                    "trailing_stop_pct": analysis.get("trailing_stop_pct"),
                    "active_thresholds": active_thresholds,
                    "key_factors": analysis.get("key_factors", []),
                },
                llm_provider=analysis.get("provider"),
                llm_tier="TIER1",
                execution_time_ms=t1_elapsed,
                confidence=analysis.get("confidence") or 0,
            )
            return result

        await activity_logger.log(
            ActivityType.TIER1_ANALYSIS, ActivityPhase.COMPLETE,
            f"\U0001f4ca [{name}] Tier1 완료: {analysis.get('recommendation', '')} "
            f"| 신뢰도 {(analysis.get('confidence') or 0):.0%}",
            cycle_id=cycle_id, symbol=symbol,
            detail={
                "recommendation": analysis.get("recommendation"),
                "reason": analysis.get("reason") or analysis.get("summary", ""),
                "target_price": analysis.get("target_price"),
                "stop_loss": analysis.get("stop_loss_price"),
            },
            llm_provider=analysis.get("provider"),
            llm_tier="TIER1",
            execution_time_ms=t1_elapsed,
            confidence=analysis.get("confidence"),
        )

        final_gate_eval = self.policy_engine.evaluate_final_gate(
            symbol=symbol,
            strategy_type=strategy_type,
            analysis=analysis,
            current_price=current_price,
            market_regime=self._market_regime,
            portfolio_snapshot=portfolio_snapshot,
            dynamic_limits=dynamic_limits,
            active_rules=self._active_trading_rules,
            buying_power=stock_info.get("_buying_power"),
        )
        final_gate = final_gate_eval.value
        if not final_gate.approved:
            final_gate_policy = final_gate_eval.decision
            if final_gate.code == "CONFIDENCE_GATE":
                confidence = float(final_gate.detail.get("confidence", 0.0) or 0.0)
                effective_min_conf = float(final_gate.detail.get("effective_min_confidence", 0.0) or 0.0)
                rule_min_conf = float(final_gate.detail.get("rule_min_confidence", 0.0) or 0.0)
                market_regime = str(final_gate.detail.get("market_regime", "") or "")
                adj_note = ""
                if market_regime and rule_min_conf and rule_min_conf != effective_min_conf:
                    adj_note = f" (국면 {market_regime}: {rule_min_conf:.0%}→{effective_min_conf:.0%})"
                message = (
                    f"🚫 [{name}] 신뢰도 게이트 차단: {confidence:.0%} < "
                    f"실효 최소 {effective_min_conf:.0%}{adj_note}"
                )
                activity_type = ActivityType.TRADING_RULE
            elif final_gate.code == "RR_RATIO_GATE":
                message = (
                    f"🚫 [{name}] RR 비율 검증 실패: "
                    f"코드 계산 {float(final_gate.detail.get('code_rr', 0.0) or 0.0):.2f}:1 "
                    f"< 최소 {float(final_gate.detail.get('min_rr', 0.0) or 0.0)}:1 "
                    f"(target={float(final_gate.detail.get('target_price', 0.0) or 0.0):,.0f}, "
                    f"stop={float(final_gate.detail.get('stop_loss_price', 0.0) or 0.0):,.0f}, "
                    f"현재가={float(final_gate.detail.get('current_price', 0.0) or 0.0):,.0f})"
                )
                activity_type = ActivityType.TRADING_RULE
            elif final_gate.code == "RR_UNDEFINED_GATE":
                message = f"🚫 [{name}] 손절가=현재가 → RR 계산 불가, 차단"
                activity_type = ActivityType.TRADING_RULE
            elif final_gate.code == "STOP_LOSS_REQUIRED_GATE":
                message = f"🚫 [{name}] 손절가 미설정 차단 (require_stop_loss_logging 규칙)"
                activity_type = ActivityType.TRADING_RULE
            elif final_gate.code == "BUYING_POWER_GATE":
                max_qty = int(final_gate.detail.get("max_qty", 0) or 0)
                min_buy_qty = int(final_gate.detail.get("min_buy_quantity", 0) or 0)
                message = (
                    f"💰 [{name}] 매수가능수량 부족 → Tier2 스킵 "
                    f"(가능 {max_qty}주 < 최소 {min_buy_qty}주)"
                )
                activity_type = ActivityType.RISK_GATE
            else:
                message = f"🚫 [{name}] DeterministicFinalGate 차단 ({final_gate.code})"
                activity_type = ActivityType.TRADING_RULE

            await activity_logger.log(
                activity_type, ActivityPhase.SKIP,
                message,
                cycle_id=cycle_id, symbol=symbol,
                detail=with_policy_trace(
                    {"deterministic_final_gate": final_gate.code, **final_gate.detail},
                    final_gate_policy,
                ),
            )
            await ai_skip_metric_service.record(
                stage="DETERMINISTIC_FINAL_GATE",
                reason_code=final_gate.code,
                skipped_tier="TIER2",
                cycle_id=cycle_id,
                symbol=symbol,
                detail=final_gate.detail,
            )
            await self._record_ai_skip_decision_event(
                stock_info=stock_info,
                cycle_id=cycle_id,
                decision_stage="DETERMINISTIC_FINAL_GATE",
                source="deterministic_final_gate",
                reason_code=final_gate.code,
                final_action="SKIP",
                reference_price=current_price,
                reason=message,
                tier1_decision=str(analysis.get("recommendation") or "UNKNOWN").upper(),
                confidence=analysis.get("confidence"),
                metadata={
                    **final_gate.detail,
                    "target_horizon_hint": target_horizon_hint,
                    "policy_trace": with_policy_trace({}, final_gate_policy)["policy_trace"],
                    "tier1_analysis": {
                        "recommendation": analysis.get("recommendation"),
                        "confidence": analysis.get("confidence"),
                        "target_price": analysis.get("target_price"),
                        "stop_loss_price": analysis.get("stop_loss_price"),
                    },
                },
            )
            return result

        if analysis.get("recommendation") == "BUY":
            pre_horizon, pre_horizon_source = self._decide_candidate_horizon(
                stock_info=stock_info,
                strategy_type=strategy_type,
                price_resp=price_resp,
                analysis=analysis,
            )
            tier1_cost_eval = self.policy_engine.evaluate_tier1_cost_gate(
                analysis=analysis,
                current_price=current_price,
                horizon=pre_horizon,
            )
            tier1_cost_gate = tier1_cost_eval.value
            if not tier1_cost_gate["approved"]:
                tier1_cost_policy = tier1_cost_eval.decision
                await activity_logger.log(
                    ActivityType.RISK_GATE, ActivityPhase.SKIP,
                    f"🚫 [{name}] 비용 게이트 사전 차단: {tier1_cost_gate['reason']}",
                    cycle_id=cycle_id, symbol=symbol,
                    detail=with_policy_trace(tier1_cost_gate, tier1_cost_policy),
                )
                await ai_skip_metric_service.record(
                    stage="TIER1_COST_GATE",
                    reason_code="LOW_EDGE_AFTER_COST",
                    skipped_tier="TIER2",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    detail=tier1_cost_gate,
                )
                await self._record_ai_skip_decision_event(
                    stock_info=stock_info,
                    cycle_id=cycle_id,
                    decision_stage="TIER1_COST_GATE",
                    source="tier1_cost_gate",
                    reason_code="LOW_EDGE_AFTER_COST",
                    final_action="SKIP",
                    reference_price=current_price,
                    reason=str(tier1_cost_gate.get("reason") or ""),
                    tier1_decision=str(analysis.get("recommendation") or "UNKNOWN").upper(),
                    confidence=analysis.get("confidence"),
                    metadata={
                        **tier1_cost_gate,
                        "target_horizon_hint": target_horizon_hint,
                        "horizon_decision_source": pre_horizon_source,
                        "policy_trace": with_policy_trace({}, tier1_cost_policy)["policy_trace"],
                        "tier1_analysis": {
                            "recommendation": analysis.get("recommendation"),
                            "confidence": analysis.get("confidence"),
                            "target_price": analysis.get("target_price"),
                            "stop_loss_price": analysis.get("stop_loss_price"),
                        },
                    },
                )
                return result

        # 3d. Tier 2 최종 검토 (모든 BUY에 대해 필수 실행)
        t2_timer = activity_logger.timer()
        await activity_logger.log(
            ActivityType.TIER2_REVIEW, ActivityPhase.START,
            f"\U0001f9e0 [{name}] Tier2 최종 검토 시작",
            cycle_id=cycle_id, symbol=symbol,
        )
        projected_horizon, horizon_decision_source = self._decide_candidate_horizon(
            stock_info=stock_info,
            strategy_type=strategy_type,
            price_resp=price_resp,
            analysis=analysis,
        )

        final = await self._tier2_review(
            symbol, name, current_price, strategy_type, analysis,
            feedback_context=feedback_context,
            chart_result=chart_result,
            dynamic_limits=dynamic_limits,
            trade_horizon=projected_horizon,
            market_context=self._market_context,
            trading_context=self._trading_context,
            news_context=news_context_text,
            portfolio_snapshot=portfolio_snapshot,
            deterministic_context=deterministic_prompt_context_service.build_tier2_context(
                symbol=symbol,
                strategy_type=strategy_type,
                current_price=current_price,
                tier1_analysis=analysis,
                portfolio_snapshot=portfolio_snapshot,
                market_regime=self._market_regime,
                dynamic_limits=dynamic_limits,
                active_rules=self._active_trading_rules,
                buying_power=stock_info.get("_buying_power"),
                target_horizon=target_horizon_hint,
            ),
            cycle_id=cycle_id,
            manual_provider_override=manual_provider_override,
            manual_model_override=manual_model_override,
        )
        t2_elapsed = activity_logger.elapsed_ms(t2_timer)

        if not final or not final.get("approved"):
            reason = final.get("reason", "") if final else "응답 없음"
            await activity_logger.log(
                ActivityType.TIER2_REVIEW, ActivityPhase.COMPLETE,
                f"\U0001f9e0 [{name}] Tier2: 미승인 - {reason[:80]}",
                cycle_id=cycle_id, symbol=symbol,
                llm_provider=final.get("provider") if final else None,
                llm_tier="TIER2",
                execution_time_ms=t2_elapsed,
            )
            logger.debug("Tier 2 검토 미승인: {} - {}", symbol, reason)
            return result

        await activity_logger.log(
            ActivityType.TIER2_REVIEW, ActivityPhase.COMPLETE,
            f"\U0001f9e0 [{name}] Tier2: \u2705 승인"
            + (f" | 수량 {final.get('suggested_quantity')}주" if final.get("suggested_quantity") else ""),
            cycle_id=cycle_id, symbol=symbol,
            detail={
                "approved": True,
                "reason": final.get("reason", ""),
                "suggested_quantity": final.get("suggested_quantity"),
                "entry_price": final.get("entry_price"),
                "target_price": final.get("target_price"),
                "trade_horizon": projected_horizon,
                "target_horizon_hint": target_horizon_hint,
                "horizon_decision_source": horizon_decision_source,
            },
            llm_provider=final.get("provider"),
            llm_tier="TIER2",
            execution_time_ms=t2_elapsed,
        )

        # 4. 전략 적용 — Tier2 승인 시 AI 결정을 우선, 전략은 보조
        strategy = self.strategies.get(strategy_type)

        # Tier2가 수량/가격까지 제시한 경우 → AI 결정으로 직접 시그널 생성
        if final.get("suggested_quantity") and final.get("entry_price"):
            t2_action = final.get("action", analysis.get("recommendation", "BUY"))
            action = SignalAction.BUY if t2_action.upper() in ("BUY", "CAUTIOUS BUY") else SignalAction.SELL
            trade_horizon = projected_horizon

            stop_loss_price = final.get("stop_loss_price")
            if not stop_loss_price:
                sl_pct = self._default_stop_loss_pct(trade_horizon)
                stop_loss_price = final["entry_price"] * (1 + sl_pct / 100)

            target_price = final.get("target_price")
            if not target_price:
                tp_pct = self._default_take_profit_pct(trade_horizon)
                target_price = final["entry_price"] * (1 + tp_pct / 100)

            metadata = strategy_profile_metadata(strategy_type)
            metadata["trade_horizon"] = trade_horizon
            metadata["scan_horizon"] = stock_info.get("scan_horizon") or target_horizon_hint
            metadata["target_horizon_hint"] = target_horizon_hint
            metadata["horizon_decision_source"] = horizon_decision_source
            signal = TradeSignal(
                symbol=symbol,
                stock_id=stock_info.get("stock_id", ""),
                action=action,
                strength=analysis.get("confidence", 0.7),
                suggested_price=final["entry_price"],
                suggested_quantity=final["suggested_quantity"],
                target_price=target_price,
                stop_loss_price=stop_loss_price,
                urgency=SignalUrgency.IMMEDIATE,
                strategy_type=strategy_type,
                reason=final.get("reason", "Tier2 승인"),
                confidence=analysis.get("confidence", 0.7),
                metadata=metadata,
            )

            result["signal"] = True
            await activity_logger.log(
                ActivityType.STRATEGY_EVAL, ActivityPhase.COMPLETE,
                f"\U0001f4c8 [{name}] Tier2 승인 기반 시그널: {action.value} "
                f"{signal.suggested_quantity}주 @{signal.suggested_price:,.0f}원",
                cycle_id=cycle_id, symbol=symbol,
            )
        else:
            # Tier2가 구체적 수량/가격을 제시하지 않은 경우 → 전략 평가로 폴백
            analysis_for_strategy = {
                **analysis,
                "indicators": indicators,
                "chart_result": chart_result,
                "symbol": symbol,
                "stock_id": stock_info.get("stock_id", ""),
                "current_price": current_price,
                "target_horizon_hint": target_horizon_hint,
                "horizon_decision_source": horizon_decision_source,
            }

            if not strategy:
                return result

            signal = await strategy.evaluate(analysis_for_strategy, market_regime=self._market_regime)
            if not signal or signal.action == SignalAction.HOLD:
                await activity_logger.log(
                    ActivityType.STRATEGY_EVAL, ActivityPhase.COMPLETE,
                    f"\U0001f4c8 [{name}] 전략 평가: HOLD → 스킵",
                    cycle_id=cycle_id, symbol=symbol,
                )
                return result

            result["signal"] = True
            await activity_logger.log(
                ActivityType.STRATEGY_EVAL, ActivityPhase.COMPLETE,
                f"\U0001f4c8 [{name}] 전략({strategy_type}): {signal.action.value} "
                f"{signal.suggested_quantity or 0}주 @{(signal.suggested_price or 0):,.0f}원",
                cycle_id=cycle_id, symbol=symbol,
            )

            # Tier 2에서 제안한 값이 있으면 적용
            signal.metadata = signal.metadata or {}
            if final.get("suggested_quantity"):
                signal.suggested_quantity = final["suggested_quantity"]
            if final.get("entry_price"):
                signal.suggested_price = final["entry_price"]
            if final.get("target_price"):
                signal.target_price = final["target_price"]
            if final.get("stop_loss_price"):
                signal.stop_loss_price = final["stop_loss_price"]
            if "trade_horizon" not in signal.metadata:
                signal.metadata["trade_horizon"] = projected_horizon
            signal.metadata.setdefault("scan_horizon", stock_info.get("scan_horizon") or target_horizon_hint)
            signal.metadata.setdefault("target_horizon_hint", target_horizon_hint)
            signal.metadata.setdefault("horizon_decision_source", horizon_decision_source)
            if signal.action == SignalAction.BUY and signal.suggested_price:
                trade_horizon = str(signal.metadata.get("trade_horizon") or projected_horizon)
                if not final.get("stop_loss_price"):
                    sl_pct = self._default_stop_loss_pct(trade_horizon)
                    signal.stop_loss_price = signal.suggested_price * (1 + sl_pct / 100)
                if not final.get("target_price"):
                    tp_pct = self._default_take_profit_pct(trade_horizon)
                    signal.target_price = signal.suggested_price * (1 + tp_pct / 100)

        # 호라이즌 정합: MID/LONG는 AI 손절/익절이 호라이즌 기본보다 타이트/가까우면 기본까지 넓힌다.
        # (예: MID인데 -3.7% 손절 → -7%로 확대, +7% 익절 → +12%로 확대) SHORT는 그대로 둔다.
        if signal.action == SignalAction.BUY and signal.suggested_price:
            _bound_horizon = str((signal.metadata or {}).get("trade_horizon") or projected_horizon)
            signal.stop_loss_price = self._bound_stop_loss_to_horizon(
                signal.stop_loss_price, signal.suggested_price, _bound_horizon
            )
            signal.target_price = self._bound_take_profit_to_horizon(
                signal.target_price, signal.suggested_price, _bound_horizon
            )
            # 바운딩 결과를 final에도 반영한다. event_detector 임계값(threshold_tier2)과
            # 기록용 ai_stop_loss_price가 final에서 값을 읽으므로, 여기서 동기화하지 않으면
            # 실제 손절/익절 트리거는 바운딩 전 AI 원본값을 그대로 쓰게 된다.
            if isinstance(final, dict):
                if signal.stop_loss_price:
                    final["stop_loss_price"] = signal.stop_loss_price
                if signal.target_price:
                    final["target_price"] = signal.target_price

        # AI가 결정한 손절/익절/트레일링 스탑을 event_detector에 설정
        threshold_tier2 = dict(final or {})
        if signal.action == SignalAction.BUY:
            if signal.stop_loss_price and not threshold_tier2.get("stop_loss_price"):
                threshold_tier2["stop_loss_price"] = signal.stop_loss_price
            if signal.target_price and not threshold_tier2.get("target_price"):
                threshold_tier2["target_price"] = signal.target_price
        active_thresholds = self._apply_trade_thresholds(
            symbol, analysis, threshold_tier2,
            current_price=current_price,
            horizon=(signal.metadata or {}).get("trade_horizon"),
        )

        # 실행 비용 대비 기대수익(엣지) 게이트
        gate_eval = None
        if signal.action == SignalAction.BUY:
            cost_eval = self.policy_engine.evaluate_cost_gate(
                signal=signal,
                current_price=current_price,
                horizon=(signal.metadata or {}).get("trade_horizon"),
            )
            gate_eval = cost_eval.value
            if not gate_eval["approved"]:
                cost_policy = cost_eval.decision
                await activity_logger.log(
                    ActivityType.RISK_GATE, ActivityPhase.SKIP,
                    f"🚫 [{name}] 비용 게이트 차단: {gate_eval['reason']}",
                    cycle_id=cycle_id, symbol=symbol,
                    detail=with_policy_trace(gate_eval, cost_policy),
                )
                return result
            news_eval = await self.policy_engine.evaluate_news_gate(
                symbol=symbol,
                horizon=(signal.metadata or {}).get("trade_horizon"),
            )
            news_gate = news_eval.value
            await self._record_news_shadow_decision(
                symbol=symbol,
                name=name,
                strategy_type=strategy_type,
                horizon=(signal.metadata or {}).get("trade_horizon"),
                gate_eval=gate_eval,
                news_gate=news_gate,
                cycle_id=cycle_id,
            )
            if not news_gate["approved"] and bool(news_gate.get("blocking_enabled", True)):
                news_policy = news_eval.decision
                await activity_logger.log(
                    ActivityType.RISK_GATE, ActivityPhase.SKIP,
                    f"🚫 [{name}] 뉴스 게이트 차단: {news_gate['reason']}",
                    cycle_id=cycle_id, symbol=symbol,
                    detail=with_policy_trace(news_gate, news_policy),
                )
                return result
        else:
            news_gate = None

        # 4.5 매도 시 보유 여부 확인 — 미보유 종목 매도 차단
        if signal.action == SignalAction.SELL:
            snap = portfolio_snapshot or {}
            holding_symbols = [normalize_krx_symbol(item) for item in snap.get("holding_symbols", [])]
            if symbol not in holding_symbols:
                logger.debug("미보유 종목 매도 스킵: {} (보유: {})", symbol, holding_symbols)
                await activity_logger.log(
                    ActivityType.RISK_CHECK, ActivityPhase.SKIP,
                    f"🚫 [{name}] 미보유 종목 매도 차단",
                    cycle_id=cycle_id, symbol=symbol,
                )
                return result
            holding_qty = self._resolve_sell_quantity_from_snapshot(signal, snap)
            if holding_qty <= 0:
                logger.debug("보유 수량 0으로 매도 스킵: {}", symbol)
                await activity_logger.log(
                    ActivityType.RISK_CHECK, ActivityPhase.SKIP,
                    f"🚫 [{name}] 보유 수량 0주 → 매도 차단",
                    cycle_id=cycle_id, symbol=symbol,
                )
                return result
            if int(signal.suggested_quantity or 0) != holding_qty:
                logger.info(
                    "[{}] 매도 수량 보정: AI {}주 → 보유 {}주",
                    symbol,
                    int(signal.suggested_quantity or 0),
                    holding_qty,
                )
                signal.suggested_quantity = holding_qty
                signal.metadata["sell_quantity_source"] = "HOLDING_SNAPSHOT"

        exposure_decision: ExposureAlignmentDecision | None = None
        if signal.action == SignalAction.BUY:
            exposure_decision = await self._apply_aggressive_exposure_alignment(
                signal=signal,
                portfolio_snapshot=portfolio_snapshot,
                dynamic_limits=dynamic_limits,
                market_regime=self._market_regime,
                cycle_id=cycle_id,
                stock_name=name,
            )
            if exposure_decision.applied:
                signal.suggested_quantity = exposure_decision.final_quantity

        # 5. 리스크 검사
        snap = portfolio_snapshot or {}
        candidate_change_rate = self._optional_float(stock_info.get("change_rate"))
        intraday = getattr(chart_result.trend, "intraday", None) or {}
        risk_input_quantity = int(signal.suggested_quantity or 0)
        risk_eval = await self.policy_engine.evaluate_risk_manager(
            input_quantity=risk_input_quantity,
            signal=signal,
            portfolio_cash=snap.get("cash", 0),
            portfolio_budget=snap.get("total_asset", 0),
            today_trade_count=snap.get("today_trade_count", 0),
            current_holding_count=snap.get("holding_count", 0),
            cycle_id=cycle_id,
            dynamic_limits=dynamic_limits,
            market_regime=self._market_regime,
            candidate_change_rate=candidate_change_rate,
            candidate_pattern=self._extract_entry_pattern(chart_result),
            intraday_direction=intraday.get("direction"),
            intraday_vwap_position=intraday.get("vwap_position"),
            intraday_volume_trend=intraday.get("vol_trend"),
        )
        risk_result = risk_eval.value

        if not risk_result.get("approved"):
            logger.debug("리스크 검사 미통과: {} - {}", symbol, risk_result.get("reason"))
            return result

        if risk_result.get("adjusted_quantity") is not None:
            previous_qty = int(risk_result.get("previous_quantity") or risk_input_quantity)
            adjusted_qty = int(risk_result["adjusted_quantity"])
            signal.suggested_quantity = adjusted_qty
            risk_policy = risk_eval.decision
            await activity_logger.log(
                ActivityType.RISK_CHECK,
                ActivityPhase.COMPLETE,
                f"🧮 [{name}] 리스크 수량 조정: {previous_qty}주 → {adjusted_qty}주",
                cycle_id=cycle_id,
                symbol=symbol,
                detail={
                    "stage": "RISK_MANAGER_ADJUSTMENT",
                    "previous_quantity": previous_qty,
                    "adjusted_quantity": adjusted_qty,
                    "reason": risk_result.get("reason"),
                    "adjustments": risk_result.get("adjustments"),
                    "warnings": risk_result.get("warnings"),
                    "exposure_alignment": (
                        exposure_decision.__dict__ if exposure_decision else None
                    ),
                    "policy_trace": with_policy_trace({}, risk_policy)["policy_trace"],
                },
            )
        elif int(signal.suggested_quantity or 0) != risk_input_quantity:
            risk_policy = risk_eval.decision
            await activity_logger.log(
                ActivityType.RISK_CHECK,
                ActivityPhase.COMPLETE,
                f"🧮 [{name}] 리스크 수량 변경 감지: "
                f"{risk_input_quantity}주 → {int(signal.suggested_quantity or 0)}주",
                cycle_id=cycle_id,
                symbol=symbol,
                detail={
                    "stage": "RISK_MANAGER_SIGNAL_MUTATION",
                    "previous_quantity": risk_input_quantity,
                    "adjusted_quantity": int(signal.suggested_quantity or 0),
                    "risk_result": risk_result,
                    "exposure_alignment": (
                        exposure_decision.__dict__ if exposure_decision else None
                    ),
                    "policy_trace": with_policy_trace({}, risk_policy)["policy_trace"],
                },
            )

        reservation_decision: OrderReservationDecision | None = None

        # 6. 매수 시 주문 직전 매수가능수량 재조회 (병렬 주문으로 가용금액 변동 반영)
        if signal.action == SignalAction.BUY:
            min_qty = (
                (dynamic_limits or {}).get("min_buy_quantity", settings.MIN_BUY_QUANTITY)
            )
            bp = await self._broker_adapter.get_buying_power(
                symbol,
                price=current_price,
                market=Market(stock_info.get("market", "KRX")),
            )
            if bp.success:
                max_qty = bp.max_qty
                if max_qty < min_qty:
                    logger.info(
                        "[{}] 매수가능수량 부족으로 주문 포기: {}주 < 최소 {}주",
                        symbol, max_qty, min_qty,
                    )
                    await activity_logger.log(
                        ActivityType.RISK_CHECK, ActivityPhase.SKIP,
                        f"💰 [{name}] 매수가능수량 부족 → 주문 포기 "
                        f"(가능 {max_qty}주 < 최소 {min_qty}주)",
                        cycle_id=cycle_id, symbol=symbol,
                    )
                    return result
                if max_qty < signal.suggested_quantity:
                    previous_qty = int(signal.suggested_quantity or 0)
                    logger.info(
                        "[{}] 매수가능수량으로 수량 조정: {}주 → {}주",
                        symbol, previous_qty, max_qty,
                    )
                    signal.suggested_quantity = max_qty
                    await activity_logger.log(
                        ActivityType.RISK_CHECK,
                        ActivityPhase.COMPLETE,
                        f"💰 [{name}] 브로커 매수가능수량 조정: {previous_qty}주 → {max_qty}주",
                        cycle_id=cycle_id,
                        symbol=symbol,
                        detail={
                            "stage": "BROKER_BUYING_POWER_ADJUSTMENT",
                            "previous_quantity": previous_qty,
                            "adjusted_quantity": max_qty,
                            "available_cash": bp.available_cash,
                            "price": current_price,
                        },
                    )
            # 조회 실패 시 → 기존 수량 유지, 브로커가 최종 판단

            # 매수 주문 실행 정책 적용 (시장가/슬리피지 가드 지정가)
            self._apply_buy_execution_policy(signal=signal, current_price=current_price)

            reservation_decision = await self._reserve_buy_cash_for_cycle(
                signal,
                order_reservation_ledger,
                cycle_id=cycle_id,
                stock_name=name,
            )
            if not reservation_decision.approved and self._order_reservation_mode() == "ENFORCE":
                return result

        # 7. 매매 결정 (자율/반자율) — AI 분석 컨텍스트를 TradeResult에 전달
        analysis_context = {
            "ai_recommendation": analysis.get("recommendation"),
            "ai_confidence": analysis.get("confidence"),
            "ai_target_price": (
                active_thresholds.get("take_profit")
                or signal.target_price
                or final.get("target_price")
                or analysis.get("target_price")
            ),
            "ai_stop_loss_price": (
                active_thresholds.get("stop_loss")
                or signal.stop_loss_price
                or final.get("stop_loss_price")
                or analysis.get("stop_loss_price")
            ),
            "active_take_profit": active_thresholds.get("take_profit"),
            "active_stop_loss": active_thresholds.get("stop_loss"),
            "active_trailing_stop_pct": active_thresholds.get("trailing_stop_pct"),
            "entry_rsi": indicators.get("rsi_14"),
            "entry_macd_hist": indicators.get("macd_histogram"),
            "entry_pattern": self._extract_entry_pattern(chart_result),
            "market_regime": self._market_regime,
            "strategy_type": strategy_type,
            **strategy_profile_metadata(strategy_type),
            "stock_name": name,
            "scan_horizon": stock_info.get("scan_horizon"),
            "target_horizon_hint": target_horizon_hint,
            "horizon_decision_source": (signal.metadata or {}).get("horizon_decision_source"),
            "trade_horizon": (signal.metadata or {}).get("trade_horizon"),
            "chart_signal_direction": (chart_result.signal_summary or {}).get("direction"),
            "chart_signal_confidence": (chart_result.signal_summary or {}).get("confidence"),
            "estimated_edge_bps": gate_eval.get("edge_bps") if gate_eval else None,
            "estimated_cost_bps": gate_eval.get("cost_bps") if gate_eval else None,
            "edge_to_cost_ratio": gate_eval.get("edge_to_cost_ratio") if gate_eval else None,
            "cost_gate_ratio": gate_eval.get("min_ratio") if gate_eval else None,
            "news_negative_pressure": news_gate.get("negative_pressure") if news_gate else None,
            "news_negative_count": news_gate.get("negative_count") if news_gate else None,
            "news_source_count": news_gate.get("source_count") if news_gate else None,
            "news_threshold": news_gate.get("threshold") if news_gate else None,
            "news_top_contributors": (news_gate.get("contributors") or [])[:3] if news_gate else None,
            "news_context_available": bool(news_context_payload.get("available")),
            "news_context_horizon": news_context_payload.get("horizon"),
            "news_context_lookback_hours": news_context_payload.get("lookback_hours"),
            "news_context_match_source": news_context_payload.get("match_source"),
            "news_context_tone": news_context_payload.get("tone"),
            "news_context_negative_pressure": news_context_payload.get("negative_pressure"),
            "news_context_negative_count": news_context_payload.get("negative_count"),
            "news_context_positive_count": news_context_payload.get("positive_count"),
            "news_context_neutral_count": news_context_payload.get("neutral_count"),
            "news_context_confidence_hint": news_context_payload.get("confidence_hint"),
            "news_context_items": (news_context_payload.get("items") or [])[:3],
            "news_context_item_count": len(news_context_payload.get("items") or []),
            "news_context_source_codes": sorted({
                str(item.get("source_code") or "").upper()
                for item in (news_context_payload.get("items") or [])
                if item.get("source_code")
            }),
            # Pre-LLM deterministic fast gate 결과 (IC 분석용 — 매매된 trade도 score 저장)
            "fast_gate_score": fast_gate.score if fast_gate else None,
            "fast_gate_code": fast_gate.code if fast_gate else None,
            "fast_gate_threshold": (
                fast_gate.detail.get("threshold") if fast_gate and fast_gate.detail else None
            ),
            # 안정성 지표 (gate 미반영, IC 예측력 측정만)
            "ulcer_index_14d": (
                fast_gate.detail.get("ulcer_index_14d") if fast_gate and fast_gate.detail else None
            ),
            "r_squared_60d": (
                fast_gate.detail.get("r_squared_60d") if fast_gate and fast_gate.detail else None
            ),
            "exposure_alignment": (signal.metadata or {}).get("exposure_alignment"),
        }

        exec_result = await decision_maker.execute(
            signal, cycle_id=cycle_id, analysis_context=analysis_context,
        )
        result["executed"] = exec_result.get("success", False)
        if (
            signal.action == SignalAction.BUY
            and order_reservation_ledger is not None
            and reservation_decision is not None
            and reservation_decision.reservation_id
            and not result["executed"]
        ):
            order_reservation_ledger.release(reservation_decision.reservation_id, reason="order_not_submitted")

        return result

    async def _apply_aggressive_exposure_alignment(
        self,
        *,
        signal: TradeSignal,
        portfolio_snapshot: dict | None,
        dynamic_limits: dict | None,
        market_regime: str,
        cycle_id: str | None,
        stock_name: str,
    ) -> ExposureAlignmentDecision:
        exposure_eval = self.policy_engine.evaluate_exposure_alignment(
            signal=signal,
            portfolio_snapshot=portfolio_snapshot,
            dynamic_limits=dynamic_limits,
            market_regime=market_regime,
        )
        decision = exposure_eval.value
        signal.metadata["exposure_alignment"] = {
            "applied": decision.applied,
            "reason": decision.reason,
            "initial_quantity": decision.initial_quantity,
            "final_quantity": decision.final_quantity,
            "initial_notional": decision.initial_notional,
            "final_notional": decision.final_notional,
            "current_exposure_pct": decision.current_exposure_pct,
            "target_exposure_pct": decision.target_exposure_pct,
            "min_order_krw": decision.min_order_krw,
            "cap_order_krw": decision.cap_order_krw,
        }
        exposure_policy = exposure_eval.decision
        signal.metadata["exposure_alignment"]["policy_trace"] = with_policy_trace(
            {},
            exposure_policy,
        )["policy_trace"]
        if not decision.applied:
            return decision

        await activity_logger.log(
            ActivityType.RISK_CHECK,
            ActivityPhase.COMPLETE,
            f"📌 [{stock_name}] 공격적 노출 보정: "
            f"{decision.initial_quantity}주 → {decision.final_quantity}주 "
            f"({decision.initial_notional:,.0f}원 → {decision.final_notional:,.0f}원)",
            cycle_id=cycle_id,
            symbol=signal.symbol,
            detail=with_policy_trace(
                {
                    "stage": "AGGRESSIVE_EXPOSURE_ALIGNMENT",
                    "reason": decision.reason,
                    "current_exposure_pct": decision.current_exposure_pct,
                    "target_exposure_pct": decision.target_exposure_pct,
                    "min_order_krw": decision.min_order_krw,
                    "cap_order_krw": decision.cap_order_krw,
                    "initial_quantity": decision.initial_quantity,
                    "final_quantity": decision.final_quantity,
                    "initial_notional": decision.initial_notional,
                    "final_notional": decision.final_notional,
                },
                exposure_policy,
            ),
        )
        return decision

    @staticmethod
    def _order_reservation_mode() -> str:
        mode = str(getattr(settings, "ORDER_RESERVATION_ENFORCEMENT", "SHADOW") or "SHADOW").upper()
        return "ENFORCE" if mode == "ENFORCE" else "SHADOW"

    async def _reserve_buy_cash_for_cycle(
        self,
        signal: TradeSignal,
        order_reservation_ledger: OrderReservationLedger | None,
        *,
        cycle_id: str | None = None,
        stock_name: str | None = None,
    ) -> OrderReservationDecision:
        amount = float(signal.suggested_price or 0.0) * int(signal.suggested_quantity or 0)
        if order_reservation_ledger is None:
            return OrderReservationDecision(
                approved=True,
                symbol=normalize_krx_symbol(signal.symbol),
                requested_amount=amount,
                reserved_amount=0.0,
                available_cash=0.0,
                reason="예약 ledger 없음",
            )

        decision = order_reservation_ledger.reserve(
            symbol=signal.symbol,
            amount=amount,
            quantity=int(signal.suggested_quantity or 0),
        )
        if not decision.approved:
            message = (
                f"💰 [{stock_name or signal.symbol}] cycle 현금 예약 부족 "
                f"({decision.available_cash:,.0f}원 < {decision.requested_amount:,.0f}원)"
            )
            if self._order_reservation_mode() == "ENFORCE":
                await activity_logger.log(
                    ActivityType.RISK_CHECK,
                    ActivityPhase.SKIP,
                    message,
                    cycle_id=cycle_id,
                    symbol=signal.symbol,
                    detail={
                        "mode": "ENFORCE",
                        "reason": decision.reason,
                        "available_cash": decision.available_cash,
                        "requested_amount": decision.requested_amount,
                    },
                )
            else:
                logger.warning("[{}] cycle 현금 예약 shadow 경고: {}", signal.symbol, decision.reason)
            return decision

        signal.metadata["order_reservation_id"] = decision.reservation_id
        signal.metadata["order_reserved_amount"] = decision.reserved_amount
        return decision

    @staticmethod
    def _apply_buy_execution_policy(signal: TradeSignal, current_price: float) -> None:
        """매수 주문 실행 정책 적용.

        - MARKET: 시장가 실행 (price=None)
        - LIMIT_GUARD: 지정가 유지, 미지정 시 현재가+슬리피지(bp)로 가드 지정가 설정
        """
        mode = str(getattr(settings, "BUY_ORDER_EXECUTION_MODE", "LIMIT_GUARD") or "LIMIT_GUARD").upper()
        if mode == "MARKET":
            signal.suggested_price = None
            return

        if signal.suggested_price and signal.suggested_price > 0:
            return

        base_price = float(current_price or 0.0)
        if base_price <= 0:
            signal.suggested_price = None
            return

        bps = max(int(getattr(settings, "BUY_SLIPPAGE_GUARD_BPS", 20) or 0), 0)
        guarded_price = int(round(base_price * (1 + bps / 10000)))
        signal.suggested_price = max(guarded_price, 1)

    async def _run_after_hours_cycle(
        self,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
    ) -> dict:
        """장외 사이클: 오늘 데이트레이딩 성과 리뷰 (피드백 학습용)"""
        from util.time_util import now_kst

        llm_factory.start_session()

        cycle_id = activity_logger.start_cycle()
        cycle_timer = activity_logger.timer()

        logger.info("=== Agent 장 마감 리뷰 시작 ===")
        await event_bus.publish(Event(
            type=EventType.AGENT_CYCLE_START, source="trading_agent",
        ))
        await activity_logger.log(
            ActivityType.CYCLE, ActivityPhase.START,
            "\U0001f319 장 마감 리뷰 시작 — 오늘 매매 성과 분석",
            cycle_id=cycle_id,
        )

        results = {"mode": "AFTER_HOURS", "review_generated": False}

        try:
            # 1. 오늘 시장 마감 데이터 수집 (MCP)
            market_close_data, volume_rank_data, surge_data, drop_data = await self._collect_market_close_data()

            # 2. 포트폴리오 현황 (데이트레이딩이면 청산 완료 상태)
            balance = await self._broker_adapter.get_balance()

            cash_ratio = 0.0
            if balance.total_asset > 0:
                cash_ratio = (balance.cash / balance.total_asset) * 100

            # 3. 오늘 활동 집계
            today_date = now_kst().date()
            activity_summary = "활동 없음"
            today_cycles = 0
            today_analyses = 0
            today_recommendations = 0
            today_orders = 0

            try:
                async with AsyncSessionLocal() as session:
                    from repositories.agent_activity_repository import AgentActivityRepository
                    activity_repo = AgentActivityRepository(session)
                    activity_counts = await activity_repo.count_by_date(today_date)
                    activities = await activity_repo.get_by_date(today_date, limit=50)

                    today_cycles = activity_counts.get("CYCLE", 0) // 2
                    today_analyses = activity_counts.get("TIER1_ANALYSIS", 0)
                    today_recommendations = activity_counts.get("DECISION", 0)
                    today_orders = activity_counts.get("ORDER", 0)

                    if activities:
                        summary_lines = []
                        for a in activities[-20:]:
                            summary_lines.append(f"[{a.activity_type}/{a.phase}] {a.summary}")
                        activity_summary = "\n".join(summary_lines)
            except Exception as e:
                logger.warning("활동 집계 실패: {}", str(e))

            # 4. 과거 매매 성과
            performance_summary = "매매 이력 없음"
            try:
                from analysis.feedback.performance_tracker import PerformanceTracker
                async with AsyncSessionLocal() as session:
                    tracker = PerformanceTracker(session)
                    stats = await tracker.get_overall_stats()
                    overall = stats.get("overall")
                    if overall and overall.total_trades > 0:
                        performance_summary = (
                            f"총 {overall.total_trades}거래, "
                            f"승률 {overall.win_rate * 100:.1f}%, "
                            f"총손익 {overall.total_pnl:+,.0f}원"
                        )
            except Exception as e:
                logger.warning("성과 요약 실패: {}", str(e))

            # 5. 오버나이트 보유종목 현황 (스윙 모드)
            overnight_holdings_text = "없음 (당일 청산 모드)" if settings.DAY_TRADING_ONLY else "없음"
            if not settings.DAY_TRADING_ONLY:
                try:
                    async with AsyncSessionLocal() as session:
                        from repositories.trade_result_repository import TradeResultRepository
                        from strategy.holding_policy import _calc_hold_days, _get_max_hold_days_for_trade
                        repo = TradeResultRepository(session)
                        open_positions = await repo.get_all_open()
                        if open_positions:
                            # 실제 KIS 보유종목과 교차 검증
                            actual_symbols = set()
                            try:
                                from trading.account_manager import account_manager
                                actual_holdings = await account_manager.get_holdings()
                                actual_symbols = {h.symbol for h in actual_holdings if h.quantity > 0}
                            except Exception:
                                # 조회 실패 시 DB 그대로 사용 (정리 불가)
                                actual_symbols = {tr.stock_symbol for tr in open_positions}

                            orphan_count = 0
                            lines = []
                            for tr in open_positions:
                                if tr.stock_symbol not in actual_symbols:
                                    # 고아 레코드 → exit_at + 손익 계산
                                    from util.time_util import now_kst
                                    now = now_kst()
                                    tr.exit_at = now
                                    tr.exit_reason = "ORPHAN_CLEANUP"

                                    # exit_price 추정: 현재가 조회
                                    exit_price = 0.0
                                    try:
                                        exit_price = await self._lookup_current_price(
                                            tr.stock_symbol,
                                            tr.market or Market.KRX,
                                        )
                                    except Exception:
                                        pass

                                    if exit_price > 0 and tr.entry_price > 0:
                                        tr.exit_price = exit_price
                                        tr.pnl = (exit_price - tr.entry_price) * tr.quantity
                                        tr.return_pct = round(
                                            (exit_price - tr.entry_price) / tr.entry_price * 100, 2
                                        )
                                        tr.is_win = tr.pnl > 0
                                        tr.hold_days = (now - tr.entry_at).days if tr.entry_at else 0

                                    orphan_count += 1
                                    continue

                                hold_days = _calc_hold_days(tr)
                                max_days = _get_max_hold_days_for_trade(tr, settings)
                                conf = tr.ai_confidence or 0.0
                                target_pct = ""
                                if tr.ai_target_price and tr.entry_price > 0:
                                    target_pct = f", 목표 도달률 {(tr.entry_price / tr.ai_target_price) * 100:.0f}%"
                                lines.append(
                                    f"- {tr.stock_name}({tr.stock_symbol}): "
                                    f"보유 {hold_days}/{max_days}일, "
                                    f"신뢰도 {conf:.2f}, "
                                    f"전략 {tr.strategy_type}"
                                    f"{target_pct}"
                                )

                            if orphan_count:
                                await session.commit()
                                logger.warning("고아 TradeResult {}건 정리 완료", orphan_count)

                            overnight_holdings_text = "\n".join(lines) if lines else "없음"
                except Exception as e:
                    logger.warning("오버나이트 보유종목 조회 실패: {}", str(e))

            # 6. LLM으로 성과 리뷰
            t1_timer = activity_logger.timer()
            await activity_logger.log(
                ActivityType.DAILY_PLAN, ActivityPhase.START,
                "\U0001f4cb 장 마감 성과 리뷰 생성 중...",
                cycle_id=cycle_id,
            )

            if settings.DAY_TRADING_ONLY:
                trading_mode_text = "당일 청산 모드 (데이트레이딩): 당일 매수 → 당일 청산 필수, 오버나이트 보유 없음"
            else:
                trading_mode_text = (
                    "스윙 모드: 장 상황에 따라 AI가 당일 청산 또는 오버나이트 보유를 판단. "
                    "유망 종목(수익 중 + 고신뢰도 + 목표 미도달)은 오버나이트 보유 가능. "
                    "오버나이트 보유종목이 있다면 overnight_evaluation에 내일 전망을 반드시 작성."
                )

            prompt = DAILY_PLAN_PROMPT.format(
                today_date=today_date,
                trading_mode=trading_mode_text,
                market_close_data=market_close_data,
                volume_rank_data=volume_rank_data,
                surge_data=surge_data,
                drop_data=drop_data,
                total_asset=balance.total_asset,
                cash=balance.cash,
                cash_ratio=cash_ratio,
                stock_value=balance.stock_value,
                total_pnl=balance.total_pnl,
                total_pnl_rate=balance.total_pnl_rate,
                today_cycles=today_cycles,
                today_analyses=today_analyses,
                today_recommendations=today_recommendations,
                today_orders=today_orders,
                activity_summary=activity_summary,
                performance_summary=performance_summary,
                overnight_holdings_text=overnight_holdings_text,
            )

            result_text, provider = await llm_factory.generate_manual(
                prompt,
                system_prompt=DAILY_PLAN_SYSTEM,
                default_tier=LLMTier.TIER1,
                cycle_id=cycle_id,
                manual_provider_override=manual_provider_override,
                manual_model_override=manual_model_override,
            )
            t1_elapsed = activity_logger.elapsed_ms(t1_timer)

            parsed = self._parse_json(result_text)
            if parsed:
                results["review_generated"] = True

                today_review = parsed.get("today_review", "")
                trade_eval = parsed.get("trade_evaluation", {})
                success_patterns = parsed.get("success_patterns", [])
                failure_patterns = parsed.get("failure_patterns", [])
                feedback = parsed.get("feedback_for_tomorrow", {})
                risk_alerts = parsed.get("risk_alerts", [])

                summary_msg = "\U0001f4cb 장 마감 리뷰 완료"
                if today_review:
                    summary_msg += f"\n\U0001f4dd 리뷰: {today_review[:150]}"
                if trade_eval.get("total_trades"):
                    summary_msg += (
                        f"\n\U0001f4ca 매매: {trade_eval['total_trades']}건 "
                        f"(수익 {trade_eval.get('profitable_trades', 0)}건, "
                        f"손실 {trade_eval.get('loss_trades', 0)}건)"
                    )
                if success_patterns:
                    summary_msg += f"\n\u2705 성공 패턴: {success_patterns[0][:80]}"
                if failure_patterns:
                    summary_msg += f"\n\u274c 실패 패턴: {failure_patterns[0][:80]}"
                if feedback.get("system_improvement"):
                    summary_msg += f"\n\U0001f527 개선: {feedback['system_improvement'][:80]}"
                if risk_alerts:
                    summary_msg += f"\n\u26a0\ufe0f 리스크: {', '.join(risk_alerts[:3])}"

                await activity_logger.log(
                    ActivityType.DAILY_PLAN, ActivityPhase.COMPLETE,
                    summary_msg,
                    cycle_id=cycle_id,
                    detail=parsed,
                    llm_provider=provider,
                    llm_tier="TIER1",
                    execution_time_ms=t1_elapsed,
                )

                # 일일 리포트 DB 저장
                try:
                    await self._save_daily_report(
                        today_date, parsed,
                        today_cycles=today_cycles,
                        today_analyses=today_analyses,
                        today_recommendations=today_recommendations,
                        today_orders=today_orders,
                    )
                except Exception as e:
                    logger.warning("일일 리포트 저장 실패: {}", str(e))

                # 일일 리뷰 → 트레이딩 규칙 자동 생성 (내일 코드 레벨 강제 적용)
                try:
                    from analysis.feedback.trading_rules import trading_rule_engine
                    rules = await trading_rule_engine.generate_rules_from_review(
                        parsed, today_date,
                    )
                    if rules:
                        rule_summary = ", ".join(
                            f"{r.param_name}={r.param_value}" for r in rules
                        )
                        await activity_logger.log(
                            ActivityType.TRADING_RULE, ActivityPhase.COMPLETE,
                            f"📋 트레이딩 규칙 {len(rules)}건 생성 (내일 자동 적용): {rule_summary}",
                            cycle_id=cycle_id,
                            detail=[{"param": r.param_name, "value": r.param_value, "reason": r.reason} for r in rules],
                        )
                except Exception as e:
                    logger.warning("트레이딩 규칙 생성 실패: {}", str(e))
            else:
                await activity_logger.log(
                    ActivityType.DAILY_PLAN, ActivityPhase.ERROR,
                    "\u274c 장 마감 리뷰 생성 실패 (응답 파싱 불가)",
                    cycle_id=cycle_id,
                    llm_provider=provider,
                    execution_time_ms=t1_elapsed,
                )

        except Exception as e:
            logger.error("장외 사이클 오류: {}", str(e))
            await activity_logger.log(
                ActivityType.CYCLE, ActivityPhase.ERROR,
                f"\u274c 장외 사이클 오류: {str(e)[:100]}",
                cycle_id=cycle_id,
                error_message=str(e),
            )

        from util.time_util import now_kst
        self._last_cycle_time = now_kst()
        elapsed = activity_logger.elapsed_ms(cycle_timer)

        next_open = market_calendar.next_krx_open()
        await event_bus.publish(Event(
            type=EventType.AGENT_CYCLE_END, data=results, source="trading_agent",
        ))
        await activity_logger.log(
            ActivityType.CYCLE, ActivityPhase.COMPLETE,
            f"\U0001f319 장 마감 리뷰 완료 (소요 {elapsed / 1000:.1f}초) "
            f"| 다음 장 시작: {next_open.strftime('%m/%d %H:%M')}",
            cycle_id=cycle_id,
            detail=results,
            execution_time_ms=elapsed,
        )
        llm_factory.end_session()
        self._last_session_id = None

        logger.info("=== Agent 장 마감 리뷰 종료 ===")
        return results

    async def _save_daily_report(
        self, report_date, parsed: dict,
        today_cycles: int = 0, today_analyses: int = 0,
        today_recommendations: int = 0, today_orders: int = 0,
    ) -> None:
        """장 마감 리뷰 AI 결과를 DailyReport에 저장 (데이트레이딩 성과 리뷰)"""
        from models.daily_report import DailyReport
        from repositories.trade_result_repository import TradeResultRepository
        from repositories.daily_report_repository import DailyReportRepository

        feedback = parsed.get("feedback_for_tomorrow", {})
        trade_eval = parsed.get("trade_evaluation", {})

        # 피드백/패턴을 strategy_stats에 저장 (피드백 시스템이 참조)
        stats = {
            "risk_alerts": parsed.get("risk_alerts", []),
            "success_patterns": parsed.get("success_patterns", []),
            "failure_patterns": parsed.get("failure_patterns", []),
            "feedback": feedback,
            "trade_evaluation": trade_eval,
        }

        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = DailyReportRepository(session)
                report = await repo.get_by_date(report_date)
                trade_repo = TradeResultRepository(session)

                # 장마감 리뷰 저장 시에도 숫자 집계를 항상 DB 기준으로 맞춘다.
                opened_trades = await trade_repo.get_opened_by_date(report_date)
                completed_trades = await trade_repo.get_completed_by_date(report_date)
                sell_count = await trade_repo.get_sell_count_by_date(report_date)
                all_open = await trade_repo.get_all_open()

                buy_count = len(opened_trades)
                win_count = sum(1 for t in completed_trades if t.is_win)
                loss_count = sum(1 for t in completed_trades if not t.is_win)
                total_pnl = sum(float(t.pnl or 0.0) for t in completed_trades)
                open_position_count = len({t.stock_symbol for t in all_open}) if all_open else 0
                total_orders = buy_count + sell_count

                report_data = {
                    "total_cycles": today_cycles,
                    "total_analyses": today_analyses,
                    "total_recommendations": today_recommendations,
                    "total_orders": total_orders if total_orders > 0 else today_orders,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "win_count": win_count,
                    "loss_count": loss_count,
                    "total_pnl": total_pnl,
                    "open_position_count": open_position_count,
                    "market_summary": parsed.get("today_review", ""),
                    "performance_review": json.dumps(trade_eval, ensure_ascii=False),
                    "lessons_learned": feedback.get("system_improvement", ""),
                    "next_day_plan": "",  # 데이트레이딩: 익일 전략 불필요
                    "top_picks": "[]",  # 데이트레이딩: 관심종목 불필요
                    "strategy_stats": json.dumps(stats, ensure_ascii=False),
                }

                if report:
                    for k, v in report_data.items():
                        setattr(report, k, v)
                    logger.debug("일일 리포트 갱신 완료: {}", report_date)
                else:
                    report = DailyReport(report_date=report_date, **report_data)
                    session.add(report)
                    logger.debug("일일 리포트 생성 완료: {}", report_date)

    async def _collect_market_close_data(self) -> tuple[str, str, str, str]:
        """오늘 시장 마감 데이터 수집 (MCP) — 장외 리뷰용

        Returns:
            (market_close_data, volume_rank_data, surge_data, drop_data)
        """
        market_close_data = "시장 데이터 조회 실패"
        volume_rank_text = "데이터 없음"
        surge_text = "데이터 없음"
        drop_text = "데이터 없음"

        try:
            # 병렬로 시장 데이터 수집
            volume_items, surge_items, drop_items = await asyncio.gather(
                self._broker_adapter.get_volume_rank(),
                self._broker_adapter.get_fluctuation_rank(sort="top"),
                self._broker_adapter.get_fluctuation_rank(sort="bottom"),
                return_exceptions=True,
            )

            # 거래량 상위
            if not isinstance(volume_items, Exception) and volume_items:
                lines = []
                for i, item in enumerate(volume_items[:15], 1):
                    name = item.get("name", "")
                    symbol = item.get("symbol", item.get("code", ""))
                    price = item.get("price", item.get("current_price", ""))
                    change_rate = item.get("change_rate", "")
                    volume = item.get("volume", "")
                    lines.append(f"{i}. {name}({symbol}) {price}원 {change_rate}% 거래량:{volume}")
                volume_rank_text = "\n".join(lines)

            # 등락률 상위 (급등)
            if not isinstance(surge_items, Exception) and surge_items:
                lines = []
                for i, item in enumerate(surge_items[:15], 1):
                    name = item.get("name", "")
                    symbol = item.get("symbol", item.get("code", ""))
                    price = item.get("price", item.get("current_price", ""))
                    change_rate = item.get("change_rate", "")
                    lines.append(f"{i}. {name}({symbol}) {price}원 {change_rate}%")
                surge_text = "\n".join(lines)

            # 등락률 하위 (급락)
            if not isinstance(drop_items, Exception) and drop_items:
                lines = []
                for i, item in enumerate(drop_items[:15], 1):
                    name = item.get("name", "")
                    symbol = item.get("symbol", item.get("code", ""))
                    price = item.get("price", item.get("current_price", ""))
                    change_rate = item.get("change_rate", "")
                    lines.append(f"{i}. {name}({symbol}) {price}원 {change_rate}%")
                drop_text = "\n".join(lines)

            # 시장 요약은 등락률 상위/하위 데이터로 판단
            market_close_data = "거래량/등락률 상위 데이터로 오늘 시장 흐름 파악"

        except Exception as e:
            logger.warning("시장 마감 데이터 수집 실패: {}", str(e))

        return market_close_data, volume_rank_text, surge_text, drop_text

    async def _get_stock_trend_summary(self, symbol: str, name: str) -> str:
        """종목 일봉 기반 간단 추세 요약 (장 마감 후 사용)"""
        try:
            candles = await self._broker_adapter.get_daily_candles(symbol, count=20, market=Market.KRX)
            prices = [
                {
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles
            ]
            if len(prices) < 5:
                return ""

            # 최근 5일 종가 추출
            recent = prices[:5]
            closes = [float(p.get("close", 0)) for p in recent if float(p.get("close", 0)) > 0]
            if len(closes) < 3:
                return ""

            latest = closes[0]
            avg_5 = sum(closes) / len(closes)

            # 20일 평균
            all_closes = [float(p.get("close", 0)) for p in prices[:20] if float(p.get("close", 0)) > 0]
            avg_20 = sum(all_closes) / len(all_closes) if all_closes else latest

            # 5일 등락률
            change_5d = ((closes[0] - closes[-1]) / closes[-1] * 100) if closes[-1] > 0 else 0

            # 추세 판단
            if latest > avg_5 > avg_20:
                trend = "상승추세"
            elif latest < avg_5 < avg_20:
                trend = "하락추세"
            else:
                trend = "횡보"

            # 최근 거래량 추이
            volumes = [int(p.get("volume", 0)) for p in recent if int(p.get("volume", 0)) > 0]
            vol_text = ""
            if len(volumes) >= 3:
                avg_vol = sum(volumes) / len(volumes)
                if volumes[0] > avg_vol * 1.5:
                    vol_text = ", 거래량 급증"
                elif volumes[0] < avg_vol * 0.5:
                    vol_text = ", 거래량 감소"

            return (
                f"- {name}({symbol}): {trend} | "
                f"종가 {latest:,.0f}원 | 5일 {change_5d:+.1f}% | "
                f"5MA {avg_5:,.0f} / 20MA {avg_20:,.0f}{vol_text}"
            )
        except Exception as e:
            logger.debug("종목 추세 요약 실패 ({}): {}", symbol, str(e))
            return ""

    def _build_market_context(self, scan_result: dict) -> str:
        """시장 스캔 결과에서 Tier1/Tier2용 시장 컨텍스트 빌드"""
        parts = []

        # market_regime (개선된 프롬프트에서 제공)
        regime = scan_result.get("market_regime", "")
        if regime:
            parts.append(f"시장 국면: {regime}")

        # market_analysis (개선된 프롬프트에서 제공)
        analysis = scan_result.get("market_analysis", scan_result.get("market_summary", ""))
        if analysis:
            parts.append(f"시장 분석: {analysis}")

        # leading_sectors
        sectors = scan_result.get("leading_sectors", [])
        if sectors:
            parts.append(f"주도 섹터: {', '.join(sectors)}")

        if not parts:
            return "시장 컨텍스트 없음"

        return "\n".join(parts)

    async def _build_trading_context(self) -> str:
        """매매 컨텍스트 (프롬프트 주입용)"""
        from util.time_util import now_kst

        now = now_kst()

        # 강제 청산까지 남은 분
        close_time = now.replace(
            hour=settings.FORCE_LIQUIDATION_HOUR,
            minute=settings.FORCE_LIQUIDATION_MINUTE,
            second=0, microsecond=0,
        )
        minutes_left = max(0, int((close_time - now).total_seconds() / 60))

        # 일일 손익
        daily_pnl_pct = 0.0
        if self._daily_start_balance > 0:
            try:
                balance = await self._broker_adapter.get_balance()
                daily_pnl_pct = (
                    (balance.total_asset - self._daily_start_balance)
                    / self._daily_start_balance * 100
                )
            except Exception:
                pass

        # 오늘 매매 성적
        stats = await self._get_today_trade_stats()

        if settings.DAY_TRADING_ONLY:
            time_info = f"강제 청산까지: {minutes_left}분"
        else:
            time_info = f"장 마감까지: {minutes_left}분 (스윙: 오버나이트 보유 가능)"

        context = (
            f"현재 시각: {now.strftime('%H:%M')} | "
            f"{time_info}\n"
            f"오늘 누적 손익: {daily_pnl_pct:+.2f}% | "
            f"매매 성적: {stats['wins']}승 {stats['losses']}패 "
            f"(총 {stats['total']}건)"
        )

        if not settings.DAY_TRADING_ONLY:
            context += (
                f"\n모드: 스윙 (STABLE {settings.MAX_HOLD_DAYS_STABLE}일, "
                f"AGGRESSIVE {settings.MAX_HOLD_DAYS_AGGRESSIVE}일)"
            )

        return context

    async def _get_today_trade_stats(self) -> dict:
        """오늘 매매 승/패 집계 (trade_results 테이블)"""
        from models.trade_result import TradeResult
        from sqlalchemy import select, func
        from util.time_util import now_kst

        today = now_kst().date()
        stats = {"wins": 0, "losses": 0, "total": 0}
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TradeResult.pnl).where(
                        func.date(TradeResult.created_at) == today
                    )
                )
                for (pnl,) in result:
                    stats["total"] += 1
                    if pnl >= 0:
                        stats["wins"] += 1
                    else:
                        stats["losses"] += 1
        except Exception:
            pass
        return stats

    def _build_monitor_candidates(self, scan_result: dict, selected: list[dict]) -> list[dict]:
        """WebSocket 실시간 감시용 후보를 최대 30종목까지 확장."""
        monitor_candidates: list[dict] = []
        seen: set[str] = set()

        for source in (
            selected,
            scan_result.get("monitor_candidates") or [],
            scan_result.get("scored_candidates") or [],
        ):
            for item in source:
                symbol = normalize_krx_symbol(item.get("symbol", ""))
                if not symbol or symbol in seen or len(monitor_candidates) >= 30:
                    continue
                candidate = dict(item)
                candidate["symbol"] = symbol
                candidate.setdefault("market", "KRX")
                monitor_candidates.append(candidate)
                seen.add(symbol)

        return monitor_candidates

    def _symbols_from_candidates(self, candidates: list[dict]) -> list[tuple[str, str]]:
        return [
            (normalize_krx_symbol(c.get("symbol", "")), c.get("market", "KRX"))
            for c in candidates
            if normalize_krx_symbol(c.get("symbol", ""))
        ]

    def _apply_scan_thresholds(self, candidates: list[dict]) -> None:
        """시장 스캔 결과에서 AI가 결정한 모니터링 임계값을 event_detector에 적용

        감시 후보는 LLM 값이 과도해도 장중 강세장에서 놓치지 않도록 보수적인 상한으로 보정한다.
        """
        applied = 0
        for c in candidates:
            symbol = normalize_krx_symbol(c.get("symbol", ""))
            if not symbol:
                continue
            monitoring = c.get("monitoring") if isinstance(c.get("monitoring"), dict) else {}

            kwargs = {
                "surge_pct": self._clamp_float(monitoring.get("surge_pct"), default=2.5, min_value=0.8, max_value=2.5),
                "drop_pct": self._clamp_float(monitoring.get("drop_pct"), default=-2.5, min_value=-2.5, max_value=-0.8),
                "volume_spike_ratio": self._clamp_float(
                    monitoring.get("volume_spike_ratio"),
                    default=1.5,
                    min_value=1.1,
                    max_value=1.5,
                ),
            }

            event_detector.set_thresholds(symbol, **kwargs)
            applied += 1

        if applied:
            logger.debug("AI 모니터링 임계값 설정: {}종목", applied)

    @staticmethod
    def _clamp_float(value, *, default: float, min_value: float, max_value: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(min_value, min(max_value, number))

    @staticmethod
    def _optional_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _apply_trade_thresholds(
        self, symbol: str, tier1: dict, tier2: dict,
        current_price: float = 0.0,
        horizon: str | None = None,
        preserve_tighter_stop_loss: bool = False,
    ) -> dict[str, float]:
        """Tier1/Tier2 분석 결과에서 손절/익절/트레일링 스탑을 event_detector에 적용

        Tier2 값을 우선 사용하고, 없으면 Tier1 값 사용.
        """
        thresholds = self._resolve_trade_thresholds(
            tier1=tier1,
            tier2=tier2,
            current_price=current_price,
            horizon=horizon,
        )

        if preserve_tighter_stop_loss and "stop_loss" in thresholds:
            current_thresholds = event_detector.get_thresholds(symbol)
            current_stop = self._optional_float(getattr(current_thresholds, "stop_loss", None))
            thresholds = self._resolve_trade_thresholds(
                tier1=tier1,
                tier2=tier2,
                current_price=current_price,
                horizon=horizon,
                preserve_tighter_stop_loss=True,
                current_stop_loss=current_stop,
            )

        return self._enforce_trade_thresholds(symbol, thresholds)

    def _resolve_trade_thresholds(
        self,
        *,
        tier1: dict,
        tier2: dict,
        current_price: float = 0.0,
        horizon: str | None = None,
        preserve_tighter_stop_loss: bool = False,
        current_stop_loss: float | None = None,
    ) -> dict[str, float]:
        """Resolve trade thresholds without writing to event detector."""
        kwargs = {}

        # stop_loss: Tier2 > Tier1
        stop_loss = tier2.get("stop_loss_price") or tier1.get("stop_loss_price")
        if stop_loss and float(stop_loss) > 0:
            kwargs["stop_loss"] = float(stop_loss)

        # take_profit: Tier2 target_price > Tier1 target_price
        take_profit = tier2.get("target_price") or tier1.get("target_price")
        if take_profit and float(take_profit) > 0:
            kwargs["take_profit"] = float(take_profit)

        # trailing_stop_pct: Tier2 > Tier1
        trailing = tier2.get("trailing_stop_pct") or tier1.get("trailing_stop_pct")
        if trailing and float(trailing) > 0:
            kwargs["trailing_stop_pct"] = float(trailing)

        horizon_key = str(horizon or "").upper()
        if current_price > 0:
            stop_loss = kwargs.get("stop_loss")
            take_profit = kwargs.get("take_profit")

            if stop_loss and stop_loss > 0:
                risk_pct = ((current_price - stop_loss) / current_price) * 100
                min_risk_pct, max_risk_pct = self._stop_loss_risk_bounds(horizon_key)
                if min_risk_pct and risk_pct < min_risk_pct:
                    kwargs["stop_loss"] = current_price * (1 - min_risk_pct / 100)
                    risk_pct = min_risk_pct
                if max_risk_pct and risk_pct > max_risk_pct:
                    kwargs["stop_loss"] = current_price * (1 - max_risk_pct / 100)

            if take_profit and take_profit > 0:
                reward_pct = ((take_profit - current_price) / current_price) * 100
                min_reward_map = {
                    TradeHorizon.SHORT: 1.2,
                    TradeHorizon.MID: 2.0,
                    TradeHorizon.LONG: 4.0,
                }
                min_reward_pct = min_reward_map.get(horizon_key)
                if min_reward_pct and reward_pct < min_reward_pct:
                    kwargs["take_profit"] = current_price * (1 + min_reward_pct / 100)

            if "trailing_stop_pct" not in kwargs:
                default_trailing = {
                    TradeHorizon.SHORT: 0.8,
                    TradeHorizon.MID: 1.5,
                    TradeHorizon.LONG: 2.5,
                }.get(horizon_key)
                if default_trailing:
                    kwargs["trailing_stop_pct"] = default_trailing

        if preserve_tighter_stop_loss and "stop_loss" in kwargs:
            current_stop = self._optional_float(current_stop_loss)
            proposed_stop = self._optional_float(kwargs.get("stop_loss"))
            if (
                current_stop is not None
                and proposed_stop is not None
                and current_stop > 0
                and proposed_stop > 0
                and proposed_stop < current_stop
            ):
                kwargs["stop_loss"] = current_stop

        return kwargs

    @staticmethod
    def _enforce_trade_thresholds(symbol: str, thresholds: dict[str, float]) -> dict[str, float]:
        """Apply resolved trade thresholds to event detector."""
        if thresholds:
            event_detector.set_thresholds(symbol, **thresholds)
            logger.info(
                "AI 손절/익절 설정: {} → {}",
                symbol,
                ", ".join(f"{k}={v}" for k, v in thresholds.items()),
            )
        return thresholds

    async def _persist_open_position_thresholds(
        self,
        symbol: str,
        thresholds: dict[str, float],
        *,
        current_price: float = 0.0,
        horizon: str | None = None,
    ) -> dict[str, float]:
        stop_loss = self._optional_float(thresholds.get("stop_loss"))
        take_profit = self._optional_float(thresholds.get("take_profit"))
        if (not stop_loss or stop_loss <= 0) and (not take_profit or take_profit <= 0):
            return thresholds

        from repositories.trade_result_repository import TradeResultRepository

        normalized = normalize_krx_symbol(symbol)
        protected_thresholds = dict(thresholds)
        try:
            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                trade_result = await repo.get_open_buy(normalized)
                if not trade_result:
                    return protected_thresholds

                changed = False
                entry_price = self._optional_float(getattr(trade_result, "entry_price", None)) or 0.0
                resolved_horizon = str(horizon or trade_horizon_from_result(trade_result)).upper()
                if stop_loss and stop_loss > 0:
                    current_stop = self._optional_float(
                        getattr(trade_result, "ai_stop_loss_price", None)
                    ) or 0.0
                    notes_stop = self._optional_float(
                        trade_notes_dict(trade_result).get("active_stop_loss")
                    ) or 0.0
                    profit_guard_stop = is_profit_protection_stop(stop_loss, entry_price)
                    if (
                        profit_guard_stop
                        and not self._allow_profit_protection_stop(
                            entry_price=entry_price,
                            current_price=current_price,
                            horizon=resolved_horizon,
                        )
                    ):
                        fallback_stop = 0.0
                        if is_loss_protective_stop(current_stop, entry_price):
                            fallback_stop = current_stop
                        elif is_loss_protective_stop(notes_stop, entry_price):
                            fallback_stop = notes_stop

                        protected_thresholds["stop_loss"] = fallback_stop
                        if fallback_stop > 0:
                            if current_stop != fallback_stop:
                                trade_result.ai_stop_loss_price = fallback_stop
                                changed = True
                        elif current_stop > 0:
                            trade_result.ai_stop_loss_price = None
                            changed = True
                    elif current_stop <= 0 or stop_loss >= current_stop:
                        trade_result.ai_stop_loss_price = stop_loss
                        changed = True
                    elif current_stop > 0:
                        protected_thresholds["stop_loss"] = current_stop
                if take_profit and take_profit > 0:
                    trade_result.ai_target_price = take_profit
                    changed = True

                if changed:
                    await session.flush()
                    await session.commit()
        except Exception as exc:
            logger.warning("보유 포지션 임계값 DB 반영 실패 {}: {}", normalized, str(exc))
        return protected_thresholds

    @staticmethod
    def _allow_profit_protection_stop(
        *,
        entry_price: float,
        current_price: float,
        horizon: str,
    ) -> bool:
        if entry_price <= 0 or current_price <= 0:
            return False
        pnl_rate = (current_price - entry_price) / entry_price * 100
        trigger_pct = {
            TradeHorizon.SHORT: float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_SHORT", 1.0) or 1.0),
            TradeHorizon.MID: float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_MID", 1.5) or 1.5),
            TradeHorizon.LONG: float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_LONG", 2.0) or 2.0),
        }.get(str(horizon or TradeHorizon.MID).upper(), 1.5)
        return pnl_rate >= trigger_pct

    @staticmethod
    def _default_stop_loss_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_SHORT", -3.0) or -3.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_LONG", -10.0) or -10.0)
        return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_MID", -7.0) or -7.0)

    @staticmethod
    def _default_take_profit_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_SHORT", 5.0) or 5.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_LONG", 18.0) or 18.0)
        return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_MID", 12.0) or 12.0)

    def _bound_stop_loss_to_horizon(
        self, stop_loss_price: float | None, entry_price: float, horizon: str
    ) -> float | None:
        """MID/LONG는 AI 손절이 호라이즌 기본보다 타이트하면 기본 폭까지 넓힌다.

        '중기/장기'로 진입했는데 단기처럼 좁은 손절(예: MID인데 -3.7%)로 관리돼
        정상 변동성에 조기 손절되는 문제를 막는다. SHORT는 AI 손절을 그대로 둔다.
        """
        key = str(horizon or TradeHorizon.MID).upper()
        if key not in (TradeHorizon.MID, TradeHorizon.LONG):
            return stop_loss_price
        if not stop_loss_price or entry_price <= 0:
            return stop_loss_price
        default_stop = entry_price * (1 + self._default_stop_loss_pct(key) / 100)
        # 더 낮은(넓은) 손절가를 채택한다.
        return min(float(stop_loss_price), default_stop)

    def _bound_take_profit_to_horizon(
        self, target_price: float | None, entry_price: float, horizon: str
    ) -> float | None:
        """MID/LONG는 AI 익절이 호라이즌 기본보다 가까우면 기본까지 넓힌다 (조기 익절 방지).

        SHORT는 AI 익절을 그대로 둔다. 부분 익절·트레일링은 별도로 수익을 보호한다.
        """
        key = str(horizon or TradeHorizon.MID).upper()
        if key not in (TradeHorizon.MID, TradeHorizon.LONG):
            return target_price
        if not target_price or entry_price <= 0:
            return target_price
        default_target = entry_price * (1 + self._default_take_profit_pct(key) / 100)
        # 더 높은(먼) 익절가를 채택한다.
        return max(float(target_price), default_target)

    @staticmethod
    def _stop_loss_risk_bounds(horizon_key: str) -> tuple[float | None, float | None]:
        appetite = str(getattr(settings, "RISK_APPETITE", "CONSERVATIVE") or "CONSERVATIVE").upper()
        bounds = {
            "CONSERVATIVE": {
                TradeHorizon.SHORT: (1.8, 2.8),
                TradeHorizon.MID: (4.0, 7.0),
                TradeHorizon.LONG: (6.0, 10.0),
            },
            "MODERATE": {
                TradeHorizon.SHORT: (2.4, 3.5),
                TradeHorizon.MID: (5.0, 8.0),
                TradeHorizon.LONG: (7.0, 11.0),
            },
            "AGGRESSIVE": {
                TradeHorizon.SHORT: (3.0, 5.0),
                TradeHorizon.MID: (6.0, 9.5),
                TradeHorizon.LONG: (8.0, 14.0),
            },
        }
        return bounds.get(appetite, bounds["CONSERVATIVE"]).get(horizon_key, (None, None))

    @staticmethod
    def _evaluate_tier1_cost_gate(analysis: dict, current_price: float, horizon: str | None = None) -> dict:
        return TradingPolicyEngine.evaluate_tier1_cost_gate_payload(
            analysis=analysis,
            current_price=current_price,
            horizon=horizon,
        )

    @staticmethod
    def _evaluate_cost_gate(signal: TradeSignal, current_price: float, horizon: str | None = None) -> dict:
        return TradingPolicyEngine.evaluate_cost_gate_payload(
            signal=signal,
            current_price=current_price,
            horizon=horizon,
        )

    @staticmethod
    def _extract_entry_pattern(chart_result: ChartAnalysisResult | None) -> str | None:
        if not chart_result:
            return None
        patterns = ((chart_result.patterns or {}).get("patterns") or [])
        if patterns:
            first = patterns[0]
            label = str(first.get("description") or first.get("name") or "").strip()
            if label:
                return label
        trend = str(((chart_result.patterns or {}).get("trend") or "")).strip()
        return trend or None

    async def _evaluate_news_gate(self, *, symbol: str, horizon: str | None = None) -> dict:
        return (
            await self.policy_engine.evaluate_news_gate(symbol=symbol, horizon=horizon)
        ).value

    async def _record_news_shadow_decision(
        self,
        *,
        symbol: str,
        name: str,
        strategy_type: str,
        horizon: str | None,
        gate_eval: dict | None,
        news_gate: dict | None,
        cycle_id: str | None,
    ) -> None:
        if not news_gate_rollout_service.should_record_shadow():
            return

        detail = {
            "kind": "NEWS_SHADOW_AB",
            "policy": "NEWS_GATE",
            "strategy_type": strategy_type,
            "horizon": str(horizon or TradeHorizon.MID).upper(),
            "actual_decision": "BUY" if (news_gate or {}).get("approved", True) else "BLOCK",
            "baseline_decision": "BUY",
            "blocked_by_news": not bool((news_gate or {}).get("approved", True)),
            "negative_pressure": (news_gate or {}).get("negative_pressure"),
            "threshold": (news_gate or {}).get("threshold"),
            "source_count": (news_gate or {}).get("source_count"),
            "edge_bps": (gate_eval or {}).get("edge_bps"),
            "cost_bps": (gate_eval or {}).get("cost_bps"),
            "edge_to_cost_ratio": (gate_eval or {}).get("edge_to_cost_ratio"),
            "contributors": (news_gate or {}).get("contributors") or [],
        }
        await activity_logger.log(
            ActivityType.REPORT,
            ActivityPhase.COMPLETE,
            f"🧪 [{name}] Shadow A/B: 뉴스ON={detail['actual_decision']} / 뉴스OFF=BUY",
            cycle_id=cycle_id,
            symbol=symbol,
            detail=detail,
        )

    async def _get_today_trade_count(self) -> int:
        """당일 BUY 주문 시도 건수 조회.

        실시간 주문 경로는 legacy orders 테이블이 아니라 trade_results에
        PENDING_CONFIRM/CONFIRMED/CONFIRM_FAILED 생명주기로 기록된다.
        """
        try:
            from datetime import datetime, time

            from models.trade_result import TradeResult
            from sqlalchemy import and_, func, or_, select
            from util.time_util import KST, now_kst

            today = now_kst().date()
            start = datetime.combine(today, time.min, tzinfo=KST)
            end = datetime.combine(today, time.max, tzinfo=KST)
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(func.count(TradeResult.id)).where(
                        TradeResult.side == "BUY",
                        TradeResult.status.in_(
                            ["PENDING_CONFIRM", "CONFIRMED", "CONFIRM_FAILED"]
                        ),
                        or_(
                            and_(
                                TradeResult.entry_at.isnot(None),
                                TradeResult.entry_at >= start,
                                TradeResult.entry_at <= end,
                            ),
                            and_(
                                TradeResult.entry_at.is_(None),
                                TradeResult.created_at >= start,
                                TradeResult.created_at <= end,
                            ),
                        ),
                        or_(
                            TradeResult.strategy_type.is_(None),
                            TradeResult.strategy_type != "HOLDING_SYNC",
                        ),
                        or_(
                            TradeResult.notes.is_(None),
                            ~TradeResult.notes.like("HOLDING_SYNC_BACKFILL%"),
                        ),
                    )
                )
                return result.scalar() or 0
        except Exception as e:
            logger.warning("당일 체결 건수 조회 실패: {}", str(e))
            return 0

    async def _tier1_analysis(
        self, symbol: str, name: str, current_price: float,
        chart_result: ChartAnalysisResult, price_data: dict,
        feedback_context: str = "",
        market_context: str = "",
        trading_context: str = "",
        news_context: str = "",
        deterministic_context: str = "",
        cycle_id: str | None = None,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
    ) -> dict | None:
        """Tier 1 AI 심층 분석"""
        prompt = STOCK_ANALYSIS_PROMPT.format(
            stock_name=name,
            symbol=symbol,
            current_price=current_price or 0,
            change=float(price_data.get("change") or 0),
            change_rate=float(price_data.get("change_rate") or 0),
            volume=int(float(price_data.get("volume") or 0)),
            technical_indicators=chart_result.indicators_text or "지표 데이터 없음",
            chart_patterns=chart_result.patterns_text or "차트 패턴 데이터 없음",
            daily_data=chart_result.trend_text or "추세 데이터 없음",
            per=price_data.get("per", "N/A"),
            pbr=price_data.get("pbr", "N/A"),
            market_cap=price_data.get("market_cap", "N/A"),
            feedback_context=feedback_context or "매매 이력 없음",
            market_context=market_context or "시장 컨텍스트 없음",
            trading_context=trading_context or "매매 컨텍스트 없음",
            news_context=news_context or (
                "### 최근 뉴스 보조 컨텍스트\n- 최근 뉴스 정보 없음. 뉴스는 중립으로 간주하세요."
            ),
            deterministic_context=deterministic_context or "사전 판단 데이터 없음",
        )

        try:
            last_result_text = ""
            last_provider = None
            for attempt in range(2):
                timeout_sec = self._tier1_llm_timeout_sec()
                if manual_provider_override or manual_model_override:
                    generate_call = llm_factory.generate_manual(
                        prompt,
                        system_prompt=STOCK_ANALYSIS_SYSTEM,
                        default_tier=LLMTier.TIER1,
                        symbol=symbol,
                        cycle_id=cycle_id,
                        manual_provider_override=manual_provider_override,
                        manual_model_override=manual_model_override,
                    )
                else:
                    generate_call = llm_factory.generate_tier1(
                        prompt,
                        system_prompt=STOCK_ANALYSIS_SYSTEM,
                        symbol=symbol,
                        cycle_id=cycle_id,
                    )
                result_text, provider = await asyncio.wait_for(generate_call, timeout=timeout_sec)
                last_result_text = result_text
                last_provider = provider
                parsed = self._parse_json(result_text)
                if parsed:
                    parsed["provider"] = provider
                    parsed = self._validate_llm_prices(parsed, current_price)
                    return parsed
                if attempt == 0:
                    logger.warning("[{}] Tier1 JSON 파싱 실패 → 같은 provider로 1회 재시도", symbol)
            logger.warning(
                "[{}] Tier1 JSON 파싱 최종 실패 (provider={}): {}",
                symbol,
                last_provider or "UNKNOWN",
                (last_result_text or "")[:200],
            )
            return None
        except asyncio.TimeoutError:
            timeout_sec = self._tier1_llm_timeout_sec()
            logger.warning("[{}] Tier1 LLM timeout ({}s) → HOLD fallback", symbol, timeout_sec)
            return self._tier1_timeout_fallback(symbol=symbol, timeout_sec=timeout_sec)
        except Exception as e:
            logger.error("Tier 1 분석 실패 ({}): {}", symbol, str(e))
            return None

    @staticmethod
    def _tier1_llm_timeout_sec() -> float:
        return max(float(getattr(settings, "TIER1_LLM_TIMEOUT_SEC", 45) or 45), 0.001)

    @staticmethod
    def _tier1_timeout_fallback(*, symbol: str, timeout_sec: float) -> dict:
        return {
            "analysis": f"Tier1 LLM이 {timeout_sec:.0f}초 안에 응답하지 않아 보수적으로 HOLD 처리했습니다.",
            "recommendation": "HOLD",
            "confidence": 0.0,
            "reason": "Tier1 LLM timeout fallback",
            "target_price": 0,
            "stop_loss_price": 0,
            "trailing_stop_pct": 0.0,
            "entry_action": "SKIP",
            "position_action": "HOLD",
            "exit_plan": {},
            "key_factors": ["TIER1_LLM_TIMEOUT", symbol],
            "provider": "TIMEOUT_FALLBACK",
        }

    async def _tier2_review(
        self, symbol: str, name: str, current_price: float,
        strategy_type: str, tier1_analysis: dict,
        feedback_context: str = "",
        chart_result: ChartAnalysisResult | None = None,
        dynamic_limits: dict | None = None,
        trade_horizon: str | None = None,
        market_context: str = "",
        trading_context: str = "",
        news_context: str = "",
        portfolio_snapshot: dict | None = None,
        deterministic_context: str = "",
        cycle_id: str | None = None,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
    ) -> dict | None:
        """Tier 2 최종 검토"""
        strategy = self.strategies.get(strategy_type)
        snap = portfolio_snapshot or {}

        # 추세 분석 기반 전략 파라미터 조정 제안
        tuning_suggestions = "조정 제안 없음"
        if chart_result and chart_result.trend:
            trend = chart_result.trend
            suggestions = []
            if trend.direction == "BEARISH" and trend.strength == "STRONG":
                suggestions.append("강한 하락 추세 - 매수 진입 자제, 손절 타이트하게 설정 권장")
            if trend.momentum == "DECELERATING":
                suggestions.append("모멘텀 감속 중 - 진입 시점 재고 필요")
            if trend.volatility_state == "EXPANDING":
                suggestions.append("변동성 확대 구간 - 포지션 사이즈 축소 권장")
            if trend.volatility_state == "CONTRACTING":
                suggestions.append("변동성 수축 - 돌파 대기, 포지션 준비")
            if suggestions:
                tuning_suggestions = "\n".join(f"- {s}" for s in suggestions)

        # 포트폴리오 대비 비중 계산
        # max_single_order_krw=0이면 무제한 → 포지션 비중으로 산출
        max_order = dynamic_limits.get("max_single_order_krw", 0) if dynamic_limits else 0
        max_pos_pct = dynamic_limits.get("max_position_pct", 20.0) if dynamic_limits else 20.0
        total_asset = snap.get("total_asset", 0)
        max_amount = max_order if max_order > 0 else int(total_asset * max_pos_pct / 100) if total_asset > 0 else 0
        position_pct = (max_amount / total_asset * 100) if total_asset > 0 else 0
        normalized_symbol = normalize_krx_symbol(symbol)
        holding_symbols = [normalize_krx_symbol(item) for item in snap.get("holding_symbols", [])]
        holding_quantities = snap.get("holding_quantities") or {}
        is_holding = normalized_symbol in holding_symbols
        holding_quantity = int(holding_quantities.get(normalized_symbol, 0) or 0)
        resolved_horizon = str(trade_horizon or TradeHorizon.MID).upper()

        prompt = FINAL_REVIEW_PROMPT.format(
            tier1_analysis=json.dumps(tier1_analysis, ensure_ascii=False, indent=2),
            stock_name=name,
            symbol=symbol,
            current_price=current_price or 0,
            strategy_type=strategy_type,
            is_holding=str(is_holding).lower(),
            holding_quantity=holding_quantity,
            max_amount=max_amount or 0,
            holding_count=snap.get("holding_count") or 0,
            position_pct=position_pct or 0,
            stop_loss_pct=self._default_stop_loss_pct(resolved_horizon),
            take_profit_pct=self._default_take_profit_pct(resolved_horizon),
            max_hold_days=5,
            max_position_pct=20,
            feedback_context=feedback_context or "매매 이력 없음",
            tuning_suggestions=tuning_suggestions,
            market_context=market_context or "시장 컨텍스트 없음",
            trading_context=trading_context or "매매 컨텍스트 없음",
            news_context=news_context or (
                "### 최근 뉴스 보조 컨텍스트\n- 최근 뉴스 정보 없음. 뉴스는 중립으로 간주하세요."
            ),
            deterministic_context=deterministic_context or "사전 판단 데이터 없음",
        )

        try:
            if manual_provider_override or manual_model_override:
                result_text, provider = await llm_factory.generate_manual(
                    prompt,
                    system_prompt=FINAL_REVIEW_SYSTEM,
                    default_tier=LLMTier.TIER2,
                    symbol=symbol,
                    cycle_id=cycle_id,
                    manual_provider_override=manual_provider_override,
                    manual_model_override=manual_model_override,
                )
            else:
                result_text, provider = await llm_factory.generate_tier2(
                    prompt,
                    system_prompt=FINAL_REVIEW_SYSTEM,
                    symbol=symbol,
                    cycle_id=cycle_id,
                )
            parsed = self._parse_json(result_text)
            if parsed:
                parsed["provider"] = provider
                parsed = self._validate_llm_prices(parsed, current_price)
            return parsed
        except Exception as e:
            logger.error("Tier 2 검토 실패 ({}): {}", symbol, str(e))
            return None

    async def _on_market_event(self, event: Event) -> None:
        """실시간 시장 이벤트 → 즉시 해당 종목 분석/매매"""
        if not self._running:
            return
        if not settings.TRADING_ENABLED:
            return
        if runtime_reconfiguration_service.is_reconfiguring():
            return

        # 장외 시간: 매매 불가이므로 이벤트 분석 스킵
        from scheduler.market_calendar import market_calendar
        if not market_calendar.is_krx_trading_hours():
            return

        # 데이트레이딩: 매수 마감 시간 이후 신규 매수 이벤트 무시
        if settings.DAY_TRADING_ONLY:
            from datetime import time as _dt_time
            from util.time_util import now_kst
            cutoff = _dt_time(settings.BUY_CUTOFF_HOUR, settings.BUY_CUTOFF_MINUTE)
            if now_kst().time() >= cutoff:
                return

        symbol = normalize_krx_symbol(event.data.get("symbol", ""))
        if not symbol:
            return

        # P2-8: 매도 진행 중인 종목 분석 스킵
        if symbol in self._selling:
            return

        # 쿨다운 체크 (동일 종목 연속 분석 방지)
        import time as _time
        now_ts = _time.time()
        last_ts = self._cooldowns.get(symbol, 0)
        if now_ts - last_ts < self.EVENT_COOLDOWN_SEC:
            return
        if symbol in self._analyzing:
            return

        self._cooldowns[symbol] = now_ts
        self._analyzing.add(symbol)

        price = event.data.get("price", 0)
        change_rate = event.data.get("change_rate", 0)
        event_type = event.type.value
        if event.data.get("name") and event.data.get("name") != symbol:
            self._symbol_names[symbol] = event.data.get("name")
        name = event.data.get("name") or self._resolve_name(symbol)

        await activity_logger.log(
            ActivityType.EVENT, ActivityPhase.PROGRESS,
            f"\u26a1 실시간 감지: {event_type} - {name}({symbol}) "
            f"({price:,.0f}원, {change_rate:+.2f}%)",
                symbol=symbol,
                detail={**event.data, "symbol": symbol},
        )

        # 즉시 분석 + 매매 (비동기)
        try:
            # 실시간 이벤트에서도 트레이딩 컨텍스트 갱신
            self._trading_context = await self._build_trading_context()

            stock_info = {
                "symbol": symbol,
                "name": event.data.get("name") or self._resolve_name(symbol),
                "strategy_type": "AGGRESSIVE_SHORT" if abs(change_rate) >= 5 else "STABLE_SHORT",
                "trigger": event_type,
            }
            cycle_id = activity_logger.start_cycle()

            # 포트폴리오 스냅샷 조회 (리스크 체크용)
            snapshot = {"cash": 0, "total_asset": 0, "holding_count": 0, "today_trade_count": 0}
            try:
                snapshot = await self._build_portfolio_snapshot()
            except RuntimeError:
                logger.error("실시간 이벤트: 계좌 조회 실패 → 분석 중단")
                return
            except Exception as e:
                logger.warning("실시간 이벤트 포트폴리오 스냅샷 조회 실패: {}", str(e))

            # 비보유종목 + 현금 부족 → 분석 스킵
            holding_syms = [normalize_krx_symbol(item) for item in snapshot.get("holding_symbols", [])]
            if symbol not in holding_syms and price > 0:
                if snapshot["cash"] < price:
                    logger.info(
                        "실시간 이벤트 스킵 (비보유 + 현금 부족): {} {:,.0f}원 < {:,.0f}원",
                        symbol, snapshot["cash"], price,
                    )
                    return

            # AI 한도
            dynamic_limits = None
            if settings.AI_RISK_TUNING_ENABLED:
                try:
                    from strategy.ai_risk_tuner import ai_risk_tuner
                    dynamic_limits = await ai_risk_tuner.compute_limits(
                        risk_appetite=settings.RISK_APPETITE, cycle_id=cycle_id,
                    )
                except Exception:
                    pass

            result = await self._analyze_and_trade(
                stock_info, cycle_id,
                dynamic_limits=dynamic_limits,
                portfolio_snapshot=snapshot,
            )
            if result.get("executed"):
                logger.info("실시간 매매 실행: {} ({})", symbol, event_type)
                # 신규 매수 종목 WebSocket 구독 추가
                await self._ensure_realtime_subscription(symbol)
        except Exception as e:
            logger.error("실시간 분석 오류 ({}): {}", symbol, str(e))
        finally:
            self._analyzing.discard(symbol)

    async def _on_news_item(self, event: Event) -> None:
        """신규 뉴스 유입 → 보유/감시 종목만 증분 재검증"""
        if not self._running:
            return
        if not settings.TRADING_ENABLED:
            return
        if runtime_reconfiguration_service.is_reconfiguring():
            return

        from scheduler.market_calendar import market_calendar
        if not market_calendar.is_krx_trading_hours():
            return

        symbols = [
            normalize_krx_symbol(item)
            for item in (event.data.get("symbols") or [])
            if normalize_krx_symbol(item)
        ]
        if not symbols:
            single = normalize_krx_symbol(event.data.get("symbol", ""))
            symbols = [single] if single else []
        if not symbols:
            return

        try:
            snapshot = await self._build_portfolio_snapshot()
        except Exception as e:
            logger.warning("뉴스 재검증 스냅샷 조회 실패: {}", str(e))
            return

        tracked_symbols = {
            normalize_krx_symbol(item)
            for item in snapshot.get("holding_symbols", [])
        }
        tracked_symbols.update(
            normalize_krx_symbol(item)
            for item in event_detector.monitored_symbols
        )
        impacted = [symbol for symbol in symbols if symbol in tracked_symbols]
        if not impacted:
            return

        awaitable_log = activity_logger.log
        await awaitable_log(
            ActivityType.EVENT, ActivityPhase.PROGRESS,
            f"📰 신규 뉴스 감지 → 관련 종목 재검증 ({', '.join(impacted[:5])})",
            detail={"symbols": impacted, "title": event.data.get("title", "")},
        )

        self._trading_context = await self._build_trading_context()

        import time as _time
        cooldown_sec = max(int(getattr(settings, "NEWS_RECHECK_COOLDOWN_SEC", 300) or 300), 1)
        now_ts = _time.time()

        for symbol in impacted:
            news_key = f"news:{symbol}"
            last_ts = self._cooldowns.get(news_key, 0)
            if now_ts - last_ts < cooldown_sec:
                continue
            if symbol in self._selling or symbol in self._analyzing:
                continue

            self._cooldowns[news_key] = now_ts
            self._analyzing.add(symbol)
            try:
                stock_info = {
                    "symbol": symbol,
                    "name": self._resolve_name(symbol),
                    "strategy_type": "STABLE_SHORT",
                    "trigger": event.type.value,
                }
                cycle_id = activity_logger.start_cycle()
                await self._analyze_and_trade(
                    stock_info,
                    cycle_id,
                    portfolio_snapshot=snapshot,
                )
            except Exception as e:
                logger.error("뉴스 재검증 오류 ({}): {}", symbol, str(e))
            finally:
                self._analyzing.discard(symbol)

    async def _staged_stop_loss_event_plan(
        self,
        symbol: str,
        *,
        current_price: float,
    ) -> dict:
        plan = {
            "blocked": False,
            "quantity": None,
            "exit_reason": "STOP_LOSS",
            "reason": "",
        }
        try:
            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                trade_result = await repo.get_open_buy(symbol)
            if not trade_result:
                return plan

            holdings = await self._broker_adapter.get_holdings()
            holding = next(
                (item for item in holdings if normalize_krx_symbol(item.symbol) == symbol),
                None,
            )
            if not holding or int(getattr(holding, "quantity", 0) or 0) <= 0:
                return plan

            avg_price = (
                self._optional_float(getattr(holding, "avg_buy_price", None))
                or self._optional_float(getattr(trade_result, "entry_price", None))
                or 0.0
            )
            if avg_price <= 0 or current_price <= 0:
                return plan

            horizon = trade_horizon_from_result(trade_result)
            default_stop_pct = self._default_stop_loss_pct(horizon)
            pnl_rate = (current_price - avg_price) / avg_price * 100
            if pnl_rate > default_stop_pct:
                return plan

            staged = staged_stop_loss_exit_decision(
                settings=settings,
                tr=trade_result,
                horizon=horizon,
                pnl_rate=pnl_rate,
                holding_quantity=int(holding.quantity),
                default_stop_loss_pct=default_stop_pct,
            )
            if staged.action == "hold":
                return {**plan, "blocked": True, "reason": staged.reason}
            if staged.action == "partial":
                return {
                    **plan,
                    "quantity": staged.quantity,
                    "exit_reason": "PARTIAL_STOP_LOSS",
                    "reason": staged.reason,
                }
            if staged.reason:
                return {**plan, "reason": staged.reason}
            return plan
        except Exception as exc:
            logger.warning("손절 이벤트 분할청산 계획 확인 실패 ({}): {}", symbol, str(exc))
            return plan

    async def _on_stop_loss(self, event: Event) -> None:
        """손절선 도달 → 즉시 매도"""
        if not self._running:
            return
        from scheduler.market_calendar import market_calendar
        if not market_calendar.is_krx_trading_hours():
            return
        symbol = normalize_krx_symbol(event.data.get("symbol", ""))
        price = event.data.get("price", 0)
        stop_loss = event.data.get("stop_loss_price", 0)

        # P0-2: 이중 매도 방지
        if not await self._acquire_sell(symbol):
            return

        try:
            name = event.data.get("name") or self._resolve_name(symbol)
            min_hold_reason = await self._stop_loss_min_hold_block_reason(
                symbol,
                stop_loss_price=float(stop_loss or 0.0),
                current_price=float(price or 0.0),
            )
            if min_hold_reason:
                logger.info("손절 이벤트 보류: {} {} — {}", name, symbol, min_hold_reason)
                await activity_logger.log(
                    ActivityType.EVENT, ActivityPhase.PROGRESS,
                    f"👀 손절 이벤트 보류: {name}({symbol}) — {min_hold_reason} "
                    f"(현재가: {price:,.0f}원, 기준: {stop_loss:,.0f}원)",
                    symbol=symbol,
                    detail=with_policy_trace(
                        {**event.data, "symbol": symbol, "min_hold_blocked": True},
                        self.policy_engine.evaluate_exit_event(
                            event_type="STOP_LOSS_HIT",
                            blocked=True,
                            exit_reason="MIN_HOLD_BLOCK",
                            reason=min_hold_reason,
                            metadata={"stop_loss_price": stop_loss, "current_price": price},
                        ).decision,
                    ),
                )
                return

            event_plan = await self._staged_stop_loss_event_plan(
                symbol,
                current_price=float(price or 0.0),
            )
            if event_plan.get("blocked"):
                logger.info("손절 이벤트 보류: {} {} — {}", name, symbol, event_plan["reason"])
                await activity_logger.log(
                    ActivityType.EVENT, ActivityPhase.PROGRESS,
                    f"👀 손절 이벤트 보류: {name}({symbol}) — {event_plan['reason']}",
                    symbol=symbol,
                    detail=with_policy_trace(
                        {**event.data, "symbol": symbol, "staged_stop_loss_blocked": True},
                        self.policy_engine.evaluate_exit_event(
                            event_type="STOP_LOSS_HIT",
                            blocked=True,
                            exit_reason="STAGED_STOP_LOSS_BLOCK",
                            reason=str(event_plan.get("reason") or ""),
                            metadata={"stop_loss_price": stop_loss, "current_price": price},
                        ).decision,
                    ),
                )
                return

            exit_reason = str(event_plan.get("exit_reason") or "STOP_LOSS")
            sell_quantity = event_plan.get("quantity")
            staged_reason = str(event_plan.get("reason") or "")
            action_text = "분할 손실축소" if exit_reason == "PARTIAL_STOP_LOSS" else "즉시 매도 실행"
            logger.warning("손절선 도달: {} {} (현재가: {:,.0f}, 손절: {:,.0f})", name, symbol, price, stop_loss)
            await activity_logger.log(
                ActivityType.EVENT, ActivityPhase.PROGRESS,
                f"\U0001f6a8 손절선 도달: {name}({symbol}) — {action_text} "
                f"(현재가: {price:,.0f}원, 손절: {stop_loss:,.0f}원)"
                + (f" — {staged_reason}" if staged_reason else ""),
                symbol=symbol,
                detail=with_policy_trace(
                    {**event.data, "symbol": symbol, "exit_reason": exit_reason, "quantity": sell_quantity},
                    self.policy_engine.evaluate_exit_event(
                        event_type="STOP_LOSS_HIT",
                        exit_reason=exit_reason,
                        quantity=sell_quantity,
                        reason=staged_reason,
                        metadata={"stop_loss_price": stop_loss, "current_price": price},
                    ).decision,
                ),
            )

            # 즉시 시장가 매도
            if settings.TRADING_ENABLED:
                try:
                    resp = await self._execute_exit_order(
                        symbol=symbol,
                        expected_price=price,
                        exit_reason=exit_reason,
                        quantity=sell_quantity,
                    )
                    if resp:
                        await activity_logger.log(
                            ActivityType.ORDER, ActivityPhase.COMPLETE,
                            f"\U0001f6a8 손절 매도: {symbol} "
                            f"({'성공' if resp.success else '실패: ' + (resp.message or '')})",
                            symbol=symbol,
                        )
                        if resp.success and exit_reason != "PARTIAL_STOP_LOSS":
                            event_detector.remove_levels(symbol)
                except Exception as e:
                    logger.error("손절 매도 실패 ({}): {}", symbol, str(e))
        finally:
            self._release_sell(symbol)

    async def _on_take_profit(self, event: Event) -> None:
        """익절선 도달 → 즉시 매도"""
        if not self._running:
            return
        from scheduler.market_calendar import market_calendar
        if not market_calendar.is_krx_trading_hours():
            return
        symbol = normalize_krx_symbol(event.data.get("symbol", ""))
        price = event.data.get("price", 0)
        take_profit = event.data.get("take_profit_price", 0)

        # P0-2: 이중 매도 방지
        if not await self._acquire_sell(symbol):
            return

        try:
            name = event.data.get("name") or self._resolve_name(symbol)
            min_hold_reason = await self._take_profit_min_hold_block_reason(symbol)
            if min_hold_reason:
                logger.info("익절선 도달 보류: {} {} — {}", name, symbol, min_hold_reason)
                await activity_logger.log(
                    ActivityType.EVENT, ActivityPhase.PROGRESS,
                    f"\U0001f3af 익절선 도달 보류: {name}({symbol}) — {min_hold_reason} "
                    f"(현재가: {price:,.0f}원, 익절: {take_profit:,.0f}원)",
                    symbol=symbol,
                    detail=with_policy_trace(
                        {**event.data, "symbol": symbol, "min_hold_blocked": True},
                        self.policy_engine.evaluate_exit_event(
                            event_type="TAKE_PROFIT_HIT",
                            blocked=True,
                            exit_reason="MIN_HOLD_BLOCK",
                            reason=min_hold_reason,
                            metadata={"take_profit_price": take_profit, "current_price": price},
                        ).decision,
                    ),
                )
                return

            logger.info("익절선 도달: {} {} (현재가: {:,.0f}, 익절: {:,.0f})", name, symbol, price, take_profit)
            await activity_logger.log(
                ActivityType.EVENT, ActivityPhase.PROGRESS,
                f"\U0001f3af 익절선 도달: {name}({symbol}) — 매도 실행 "
                f"(현재가: {price:,.0f}원, 익절: {take_profit:,.0f}원)",
                symbol=symbol,
                detail=with_policy_trace(
                    {**event.data, "symbol": symbol},
                    self.policy_engine.evaluate_exit_event(
                        event_type="TAKE_PROFIT_HIT",
                        exit_reason="TAKE_PROFIT",
                        reason="take profit threshold reached",
                        metadata={"take_profit_price": take_profit, "current_price": price},
                    ).decision,
                ),
            )

            # 즉시 시장가 매도
            if settings.TRADING_ENABLED:
                try:
                    resp = await self._execute_exit_order(
                        symbol=symbol,
                        expected_price=price,
                        exit_reason="TAKE_PROFIT",
                    )
                    if resp:
                        await activity_logger.log(
                            ActivityType.ORDER, ActivityPhase.COMPLETE,
                            f"\U0001f3af 익절 매도: {symbol} "
                            f"({'성공' if resp.success else '실패: ' + (resp.message or '')})",
                            symbol=symbol,
                        )
                        if resp.success:
                            event_detector.remove_levels(symbol)
                except Exception as e:
                    logger.error("익절 매도 실패 ({}): {}", symbol, str(e))
        finally:
            self._release_sell(symbol)

    async def _ensure_realtime_subscription(self, symbol: str) -> None:
        """매수 후 WebSocket 실시간 구독 확인/추가"""
        try:
            from realtime.stream_manager import SubscriptionPriority, SubscriptionRequest, stream_manager
            await stream_manager.subscribe_symbols([
                SubscriptionRequest(symbol=symbol, market="KRX", priority=SubscriptionPriority.HELD_POSITION)
            ])
            logger.debug("매수 종목 WebSocket 구독 추가: {}", symbol)
        except Exception as e:
            logger.warning("WebSocket 구독 추가 실패 ({}): {}", symbol, str(e))

    @staticmethod
    def _validate_llm_prices(analysis: dict, current_price: float) -> dict:
        """LLM 응답의 가격/신뢰도 값을 검증하고 보정

        - target_price: (current_price * 0.5, current_price * 2.0) 범위
        - stop_loss_price: (current_price * 0.5, current_price) 범위
        - stop_loss < target_price 검증
        - confidence: [0.0, 1.0] 클램핑 (100 초과 시 /100)
        """
        if not analysis or current_price <= 0:
            return analysis or {}

        # confidence 검증
        try:
            conf = float(analysis.get("confidence", 0))
            if conf > 1.0:
                conf = conf / 100.0 if conf <= 100.0 else 1.0
            conf = max(0.0, min(1.0, conf))
            analysis["confidence"] = conf
        except (TypeError, ValueError):
            analysis["confidence"] = 0.0

        # target_price 검증
        try:
            tp = analysis.get("target_price")
            if tp is not None:
                tp = float(tp)
                if tp <= 0 or tp < current_price * 0.5 or tp > current_price * 2.0:
                    logger.warning("LLM target_price 범위 초과: {} (현재가: {})", tp, current_price)
                    analysis["target_price"] = None
                else:
                    analysis["target_price"] = tp
        except (TypeError, ValueError):
            analysis["target_price"] = None

        # stop_loss_price 검증
        try:
            sl = analysis.get("stop_loss_price")
            if sl is not None:
                sl = float(sl)
                if sl <= 0 or sl < current_price * 0.5 or sl >= current_price:
                    logger.warning("LLM stop_loss_price 범위 초과: {} (현재가: {})", sl, current_price)
                    analysis["stop_loss_price"] = None
                else:
                    analysis["stop_loss_price"] = sl
        except (TypeError, ValueError):
            analysis["stop_loss_price"] = None

        # stop_loss < target_price 교차 검증
        tp = analysis.get("target_price")
        sl = analysis.get("stop_loss_price")
        if tp is not None and sl is not None and sl >= tp:
            logger.warning("LLM stop_loss({}) >= target_price({}) → 둘 다 무효화", sl, tp)
            analysis["target_price"] = None
            analysis["stop_loss_price"] = None

        return analysis

    def _normalize_tier1_decision(
        self,
        analysis: dict,
        *,
        symbol: str,
        portfolio_snapshot: dict | None,
    ) -> dict:
        """Normalize the expanded Tier1 schema while preserving legacy responses."""
        if not analysis:
            return {}

        normalized_symbol = normalize_krx_symbol(symbol)
        holding_symbols = [
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
        ]
        is_holding = normalized_symbol in holding_symbols

        recommendation = str(analysis.get("recommendation") or "HOLD").upper()
        entry_action = str(analysis.get("entry_action") or "").upper()
        position_action = str(analysis.get("position_action") or "").upper()

        if not entry_action:
            entry_action = "BUY" if recommendation == "BUY" else "SKIP"
        if not position_action:
            if recommendation == "SELL" and is_holding:
                position_action = "SELL"
            elif recommendation == "BUY" and is_holding:
                position_action = "ADD_BUY"
            else:
                position_action = "HOLD"

        valid_position_actions = {"HOLD", "SELL", "PARTIAL_SELL", "ADD_BUY", "TIGHTEN_STOP"}
        if position_action not in valid_position_actions:
            position_action = "HOLD"
        if entry_action not in {"BUY", "SKIP"}:
            entry_action = "SKIP"

        exit_plan = analysis.get("exit_plan") if isinstance(analysis.get("exit_plan"), dict) else {}
        plan_stop = self._optional_float(exit_plan.get("stop_loss_price"))
        plan_take_profit = self._optional_float(
            exit_plan.get("take_profit_price") or exit_plan.get("target_price")
        )
        plan_trailing = self._optional_float(exit_plan.get("trailing_stop_pct"))
        if plan_stop and plan_stop > 0 and not analysis.get("stop_loss_price"):
            analysis["stop_loss_price"] = plan_stop
        if plan_take_profit and plan_take_profit > 0 and not analysis.get("target_price"):
            analysis["target_price"] = plan_take_profit
        if plan_trailing and plan_trailing > 0 and not analysis.get("trailing_stop_pct"):
            analysis["trailing_stop_pct"] = plan_trailing

        if is_holding:
            if position_action == "SELL":
                recommendation = "SELL"
            elif position_action == "ADD_BUY":
                recommendation = "BUY"
            else:
                recommendation = "HOLD"
        else:
            recommendation = "BUY" if entry_action == "BUY" and recommendation == "BUY" else "HOLD"
            if position_action == "SELL":
                position_action = "HOLD"

        analysis["recommendation"] = recommendation
        analysis["entry_action"] = entry_action
        analysis["position_action"] = position_action
        analysis["exit_plan"] = exit_plan
        return analysis

    def _parse_json(self, text: str) -> dict | None:
        from core.json_utils import parse_llm_json
        result = parse_llm_json(text)
        return result if result else None

    @property
    def last_cycle_time(self):
        return self._last_cycle_time


trading_agent = TradingAgent()
