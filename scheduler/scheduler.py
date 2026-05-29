"""트레이딩 에이전트 스케줄러 — KRX 데이트레이딩 자동 운영

타임라인 (KST):
  08:50  장 시작 전 준비 — 어제 리뷰 피드백 확인
  09:00  KRX 개장
  09:05  장 시작 스캔 → 종목 선정 → 실시간 모니터링 돌입
  09:00~14:30  WebSocket 실시간 이벤트 → AI 분석/매매 (이벤트 기반)
              + 1시간 간격 보유종목 안전 점검 (시간 기반 조기 청산 포함)
  11:00/13:00  장중 재스캔 — 새로운 기회 탐색
  14:30  신규 매수 마감 (청산 시간 확보)
  15:10  장마감 보유 심사 (DAY_TRADING_ONLY=true일 때만 전량 강제 청산)
  15:30  KRX 폐장
  15:40  장 마감 성과 리뷰 (KRX 종가 기반, 피드백 학습)
  16:00  포트폴리오 정산 (KIS ↔ DB 동기화)
  16:30  일봉 데이터 보관용 수집

※ DAY_TRADING_ONLY=true: 당일 매수→당일 청산 필수 (오버나이트 없음)
※ DAY_TRADING_ONLY=false: 스윙 모드 — AI 보유 심사 후 유망 종목 오버나이트 보유
"""
from collections.abc import Awaitable
import asyncio
import copy
import json
import time as _time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from core.config import settings
from core.events import Event, EventType, event_bus
from core.order_submission import decide_order_submission
from services.observability_maintenance_service import observability_maintenance_service
from services.observability_service import observability_service
from services.account_equity_service import account_equity_service
from services.error_capture_service import error_capture_service
from services.news_translation_backfill_service import news_translation_backfill_service
from trading.symbols import normalize_krx_symbol
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType, Market, OrderSide, OrderType
from trading.models import OrderRequest
from scheduler.jobs.forward_return_label_job import forward_return_label_job
from strategy.trade_horizon import TradeHorizon


class TradingScheduler:
    """KRX 장 시간 기반 자동 운영 스케줄러"""

    def __init__(self):
        self.scheduler = self._build_scheduler()
        self._running = False
        self._trading_jobs_registered = False
        self._news_jobs_registered = False
        self._common_jobs_registered = False
        self._news_poll_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task[object]] = set()
        self._last_event_news_poll_at = 0.0
        self._last_event_news_poll_by_symbol: dict[str, float] = {}
        self._soft_stop_observations: dict[str, dict[str, object]] = {}
        self._position_price_peaks: dict[str, dict[str, float]] = {}
        self._event_handlers_registered = False
        self._register_news_event_handlers()

    def _spawn_background_task(
        self,
        coro,
        *,
        task_name: str,
        delay_seconds: float = 0.25,
    ) -> None:
        async def _runner() -> None:
            try:
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                await coro
            except Exception as exc:
                logger.warning("백그라운드 시작 작업 실패 ({}): {}", task_name, str(exc))
                await error_capture_service.capture_exception(
                    component="scheduler",
                    operation=f"startup_task:{task_name}",
                    exc=exc,
                )

        asyncio.create_task(_runner())

    @staticmethod
    def _build_scheduler() -> AsyncIOScheduler:
        return AsyncIOScheduler(timezone="Asia/Seoul")

    def _register_news_event_handlers(self) -> None:
        if self._event_handlers_registered:
            return
        event_bus.subscribe(EventType.VOLUME_SPIKE, self._on_news_trigger_event)
        event_bus.subscribe(EventType.PRICE_SURGE, self._on_news_trigger_event)
        event_bus.subscribe(EventType.PRICE_DROP, self._on_news_trigger_event)
        event_bus.subscribe(EventType.ORDER_EXECUTED, self._on_news_trigger_event)
        event_bus.subscribe(EventType.RECOMMENDATION_CREATED, self._on_news_trigger_event)
        event_bus.subscribe(EventType.MARKET_OPEN, self._on_news_trigger_event)
        self._event_handlers_registered = True

    def _soft_stop_buffer_pct(self) -> float:
        appetite = str(getattr(settings, "RISK_APPETITE", "CONSERVATIVE") or "CONSERVATIVE").upper()
        return {
            "CONSERVATIVE": 0.4,
            "MODERATE": 0.8,
            "AGGRESSIVE": 1.2,
        }.get(appetite, 0.4)

    def _should_defer_soft_stop(
        self,
        symbol: str,
        *,
        pnl_rate: float,
        stop_loss_pct: float,
        minutes_left: int,
        observed_at: float,
        scope: str,
    ) -> tuple[bool, str]:
        """Defer shallow stop-loss breaches once to avoid selling on a brief shakeout."""
        key = f"{scope}:{normalize_krx_symbol(symbol)}"
        if pnl_rate > stop_loss_pct:
            self._soft_stop_observations.pop(key, None)
            return False, ""

        breach_depth = stop_loss_pct - pnl_rate
        if breach_depth >= self._soft_stop_buffer_pct():
            self._soft_stop_observations.pop(key, None)
            return False, "hard_breach"
        if minutes_left <= 20:
            self._soft_stop_observations.pop(key, None)
            return False, "near_close"

        previous = self._soft_stop_observations.get(key)
        if previous and observed_at - float(previous.get("observed_at", 0.0)) <= 180:
            self._soft_stop_observations.pop(key, None)
            return False, "confirmed"

        self._soft_stop_observations[key] = {
            "observed_at": observed_at,
            "pnl_rate": pnl_rate,
            "stop_loss_pct": stop_loss_pct,
        }
        return True, "first_observation"

    @staticmethod
    def _trade_notes_dict(tr) -> dict:
        notes = str(getattr(tr, "notes", "") or "")
        try:
            parsed = json.loads(notes)
        except (TypeError, ValueError):
            try:
                parsed, _end_index = json.JSONDecoder().raw_decode(notes.strip())
            except (TypeError, ValueError):
                return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _positive_float(value) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _persisted_threshold_kwargs(cls, tr, *, current_thresholds=None) -> dict[str, float]:
        """Restore persisted AI exit thresholds after an intraday restart.

        `event_detector` is in-memory, while open-position AI stop/take values are
        persisted on TradeResult rows. A restart during market hours should not
        downgrade those positions to default stop/take rules until premarket restore.
        """
        if tr is None:
            return {}

        kwargs: dict[str, float] = {}
        current_stop = float(getattr(current_thresholds, "stop_loss", 0.0) or 0.0)
        current_take = float(getattr(current_thresholds, "take_profit", 0.0) or 0.0)
        current_trailing = float(getattr(current_thresholds, "trailing_stop_pct", 0.0) or 0.0)

        stop_loss = cls._positive_float(getattr(tr, "ai_stop_loss_price", None))
        if current_stop <= 0 and stop_loss is not None:
            kwargs["stop_loss"] = stop_loss

        take_profit = cls._positive_float(getattr(tr, "ai_target_price", None))
        if current_take <= 0 and take_profit is not None:
            kwargs["take_profit"] = take_profit

        notes = cls._trade_notes_dict(tr)
        trailing_stop = cls._positive_float(notes.get("active_trailing_stop_pct"))
        if current_trailing <= 0 and trailing_stop is not None:
            kwargs["trailing_stop_pct"] = trailing_stop

        return kwargs

    @staticmethod
    def _trade_horizon_from_result(tr) -> str:
        parsed = TradingScheduler._trade_notes_dict(tr)
        if isinstance(parsed, dict):
            horizon = str(parsed.get("trade_horizon") or "").upper()
            if horizon in {TradeHorizon.SHORT, TradeHorizon.MID, TradeHorizon.LONG}:
                return horizon
        strategy_type = str(getattr(tr, "strategy_type", "") or "").upper()
        if "AGGRESSIVE" in strategy_type:
            return TradeHorizon.SHORT
        return TradeHorizon.MID

    @staticmethod
    def _note_has_marker(tr, marker: str) -> bool:
        return marker in str(getattr(tr, "notes", "") or "")

    @staticmethod
    def _partial_take_profit_threshold_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "PARTIAL_TAKE_PROFIT_PCT_SHORT", 1.5) or 1.5)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "PARTIAL_TAKE_PROFIT_PCT_LONG", 5.0) or 5.0)
        return float(getattr(settings, "PARTIAL_TAKE_PROFIT_PCT_MID", 3.0) or 3.0)

    @staticmethod
    def _partial_take_profit_size_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "PARTIAL_TAKE_PROFIT_SIZE_PCT_SHORT", 40.0) or 40.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "PARTIAL_TAKE_PROFIT_SIZE_PCT_LONG", 25.0) or 25.0)
        return float(getattr(settings, "PARTIAL_TAKE_PROFIT_SIZE_PCT_MID", 33.0) or 33.0)

    @staticmethod
    def _breakeven_trigger_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_SHORT", 1.0) or 1.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_LONG", 2.0) or 2.0)
        return float(getattr(settings, "BREAKEVEN_TRIGGER_PCT_MID", 1.5) or 1.5)

    @staticmethod
    def _default_stop_loss_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_SHORT", -3.0) or -3.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_LONG", -6.0) or -6.0)
        return float(getattr(settings, "DEFAULT_STOP_LOSS_PCT_MID", -4.0) or -4.0)

    @staticmethod
    def _default_take_profit_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_SHORT", 5.0) or 5.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_LONG", 12.0) or 12.0)
        return float(getattr(settings, "DEFAULT_TAKE_PROFIT_PCT_MID", 8.0) or 8.0)

    @staticmethod
    def _trailing_profit_activate_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            return float(getattr(settings, "TRAILING_PROFIT_ACTIVATE_PCT_SHORT", 2.0) or 2.0)
        if key == TradeHorizon.LONG:
            return float(getattr(settings, "TRAILING_PROFIT_ACTIVATE_PCT_LONG", 5.0) or 5.0)
        return float(getattr(settings, "TRAILING_PROFIT_ACTIVATE_PCT_MID", 3.0) or 3.0)

    @staticmethod
    def _trailing_profit_drawdown_pct(horizon: str) -> float:
        key = str(horizon or TradeHorizon.MID).upper()
        if key == TradeHorizon.SHORT:
            base = float(getattr(settings, "TRAILING_PROFIT_DRAWDOWN_PCT_SHORT", 1.0) or 1.0)
        elif key == TradeHorizon.LONG:
            base = float(getattr(settings, "TRAILING_PROFIT_DRAWDOWN_PCT_LONG", 3.0) or 3.0)
        else:
            base = float(getattr(settings, "TRAILING_PROFIT_DRAWDOWN_PCT_MID", 1.8) or 1.8)
        appetite = str(getattr(settings, "RISK_APPETITE", "CONSERVATIVE") or "CONSERVATIVE").upper()
        if appetite == "AGGRESSIVE":
            return base + 0.4
        if appetite == "MODERATE":
            return base + 0.2
        return max(base - 0.1, 0.5)

    def _partial_take_profit_quantity(self, *, holding_quantity: int, horizon: str) -> int:
        if not bool(getattr(settings, "PARTIAL_TAKE_PROFIT_ENABLED", True)):
            return 0
        quantity = int(holding_quantity or 0)
        if quantity <= 1:
            return 0
        size_pct = min(max(self._partial_take_profit_size_pct(horizon), 1.0), 95.0)
        sell_qty = int(quantity * size_pct / 100.0)
        return min(max(sell_qty, 1), quantity - 1)

    def _should_partial_take_profit(self, *, tr, pnl_rate: float, holding_quantity: int) -> tuple[bool, int, str]:
        if not bool(getattr(settings, "POSITION_EXIT_MANAGEMENT_ENABLED", True)):
            return False, 0, ""
        if self._note_has_marker(tr, "PARTIAL_TAKE_PROFIT_DONE"):
            return False, 0, ""
        horizon = self._trade_horizon_from_result(tr)
        trigger_pct = self._partial_take_profit_threshold_pct(horizon)
        if pnl_rate < trigger_pct:
            return False, 0, ""
        quantity = self._partial_take_profit_quantity(
            holding_quantity=holding_quantity,
            horizon=horizon,
        )
        if quantity <= 0:
            return False, 0, ""
        return True, quantity, f"{horizon} 부분익절 ({pnl_rate:+.1f}% ≥ {trigger_pct:+.1f}%)"

    def _breakeven_stop_price(self, *, avg_buy_price: float, pnl_rate: float, tr) -> float | None:
        if not bool(getattr(settings, "POSITION_EXIT_MANAGEMENT_ENABLED", True)):
            return None
        if not bool(getattr(settings, "BREAKEVEN_STOP_ENABLED", True)):
            return None
        if avg_buy_price <= 0:
            return None
        horizon = self._trade_horizon_from_result(tr)
        if pnl_rate < self._breakeven_trigger_pct(horizon):
            return None
        buffer_bps = max(int(getattr(settings, "BREAKEVEN_BUFFER_BPS", 10) or 0), 0)
        return avg_buy_price * (1 + buffer_bps / 10000.0)

    def _evaluate_trailing_profit_guard(
        self,
        *,
        symbol: str,
        avg_buy_price: float,
        current_price: float,
        pnl_rate: float,
        tr,
    ) -> tuple[bool, str, dict]:
        if not bool(getattr(settings, "POSITION_EXIT_MANAGEMENT_ENABLED", True)):
            return False, "", {}
        if not bool(getattr(settings, "TRAILING_PROFIT_GUARD_ENABLED", True)):
            return False, "", {}
        if not tr or avg_buy_price <= 0 or current_price <= 0:
            return False, "", {}

        normalized = normalize_krx_symbol(symbol)
        horizon = self._trade_horizon_from_result(tr)
        peak = self._position_price_peaks.get(normalized, {})
        peak_price = max(float(peak.get("peak_price", 0.0) or 0.0), float(current_price))
        peak_pnl_rate = (peak_price - avg_buy_price) / avg_buy_price * 100
        self._position_price_peaks[normalized] = {
            "peak_price": peak_price,
            "peak_pnl_rate": peak_pnl_rate,
        }

        activate_pct = self._trailing_profit_activate_pct(horizon)
        drawdown_limit = self._trailing_profit_drawdown_pct(horizon)
        drawdown_pct = peak_pnl_rate - pnl_rate
        detail = {
            "horizon": horizon,
            "peak_price": peak_price,
            "peak_pnl_rate": peak_pnl_rate,
            "pnl_rate": pnl_rate,
            "activate_pct": activate_pct,
            "drawdown_pct": drawdown_pct,
            "drawdown_limit": drawdown_limit,
        }
        if peak_pnl_rate < activate_pct:
            return False, "", detail
        if drawdown_pct < drawdown_limit:
            return False, "", detail
        return (
            True,
            f"{horizon} 트레일링 수익보호 "
            f"(고점 {peak_pnl_rate:+.1f}% → 현재 {pnl_rate:+.1f}%, 되돌림 {drawdown_pct:.1f}%p)",
            detail,
        )

    def _scale_in_candidate_reason(
        self,
        *,
        tr,
        pnl_rate: float,
        current_price: float,
        active_stop_loss: float,
    ) -> str | None:
        if not bool(getattr(settings, "SCALE_IN_CANDIDATE_ENABLED", True)):
            return None
        horizon = self._trade_horizon_from_result(tr)
        if horizon == TradeHorizon.SHORT:
            return None
        min_pullback = (
            float(getattr(settings, "SCALE_IN_MIN_PULLBACK_PCT_LONG", -4.0) or -4.0)
            if horizon == TradeHorizon.LONG
            else float(getattr(settings, "SCALE_IN_MIN_PULLBACK_PCT_MID", -2.5) or -2.5)
        )
        max_pullback = float(getattr(settings, "SCALE_IN_MAX_PULLBACK_PCT", -0.8) or -0.8)
        if not (min_pullback <= pnl_rate <= max_pullback):
            return None
        if active_stop_loss > 0 and current_price <= active_stop_loss:
            return None
        return f"{horizon} 눌림 추가매수 후보 ({pnl_rate:+.1f}%, 손절선 위)"

    async def _update_open_position_stop_loss(self, symbol: str, stop_loss_price: float) -> None:
        if stop_loss_price <= 0:
            return
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository

        normalized = normalize_krx_symbol(symbol)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                open_buys = await repo.get_all_open_buys(normalized)
                for open_buy in open_buys:
                    current_stop = float(getattr(open_buy, "ai_stop_loss_price", 0.0) or 0.0)
                    if current_stop <= 0 or stop_loss_price > current_stop:
                        open_buy.ai_stop_loss_price = stop_loss_price

    def _schedule_background_task(
        self,
        coro: Awaitable[object],
        *,
        label: str,
    ) -> asyncio.Task[object]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _finalize(done_task: asyncio.Task[object]) -> None:
            self._background_tasks.discard(done_task)
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception as exc:  # pragma: no cover - logging path
                logger.warning("{} 실패: {}", label, str(exc))

        task.add_done_callback(_finalize)
        return task

    async def _on_news_trigger_event(self, event: Event) -> None:
        if not settings.NEWS_POLL_ENABLED:
            return

        now_mono = _time.monotonic()
        symbol = str((event.data or {}).get("symbol") or "").strip()
        global_cooldown_sec = 90.0
        symbol_cooldown_sec = 300.0

        if (now_mono - self._last_event_news_poll_at) < global_cooldown_sec:
            return
        if symbol:
            last_symbol_at = float(self._last_event_news_poll_by_symbol.get(symbol) or 0.0)
            if (now_mono - last_symbol_at) < symbol_cooldown_sec:
                return
            self._last_event_news_poll_by_symbol[symbol] = now_mono

        self._last_event_news_poll_at = now_mono
        self._schedule_background_task(
            self._news_poll(
                trigger_mode="AUTO_EVENT",
                trigger_reason=event.type.value,
            ),
            label="이벤트 기반 뉴스 폴링",
        )

    async def _fetch_current_price(self, symbol: str, market: Market = Market.KRX) -> float:
        """브로커 어댑터 기준 현재가를 조회한다."""
        quote = await get_broker_adapter().get_current_price(symbol, market)
        return float(quote.price or 0.0)

    async def _place_market_sell(self, symbol: str, quantity: int, market: Market = Market.KRX):
        """브로커 어댑터 기준 시장가 매도 주문을 실행한다."""
        submission_decision = decide_order_submission(OrderSide.SELL)
        if not submission_decision.allowed:
            return type("NormalizedOrderResult", (), {
                "success": False,
                "order_id": "",
                "message": submission_decision.reason,
                "error": submission_decision.reason,
            })()

        request = OrderRequest(
            symbol=symbol,
            market=market,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )
        result = await get_broker_adapter().place_order(request)
        return type("NormalizedOrderResult", (), {
            "success": bool(result.success),
            "order_id": result.order_id or "",
            "message": result.message,
            "error": None if result.success else result.message,
        })()

    async def start(self) -> None:
        trading_jobs_enabled = bool(settings.SCHEDULER_ENABLED)
        news_jobs_enabled = bool(settings.NEWS_POLL_ENABLED)

        if not trading_jobs_enabled and not news_jobs_enabled:
            logger.debug("스케줄러 비활성화 (SCHEDULER_ENABLED=false, NEWS_POLL_ENABLED=false)")
            return

        if self._running:
            # 이미 실행 중이면 신규 활성화된 잡 그룹만 추가 등록한다.
            add_trading = trading_jobs_enabled and not self._trading_jobs_registered
            add_news = news_jobs_enabled and not self._news_jobs_registered
            if not (add_trading or add_news):
                logger.debug("스케줄러 이미 실행 중")
                return

            self._setup_jobs(
                include_trading_jobs=add_trading,
                include_news_jobs=add_news,
                include_common_jobs=not self._common_jobs_registered,
            )
            self._common_jobs_registered = True
            if add_trading:
                self._trading_jobs_registered = True
                logger.info("스케줄러 트레이딩 잡 등록 — 이후 사이클이 활성화됩니다")
                self._spawn_background_task(
                    self._on_startup(),
                    task_name="trading_startup",
                )
            if add_news:
                self._news_jobs_registered = True
                logger.info("스케줄러 뉴스 잡 등록")
                self._spawn_background_task(
                    self._news_poll(),
                    task_name="initial_news_poll",
                )
                self._spawn_background_task(
                    self._news_translation_backfill(),
                    task_name="initial_news_translation_backfill",
                )
            return

        self.scheduler = self._build_scheduler()
        self._setup_jobs(
            include_trading_jobs=trading_jobs_enabled,
            include_news_jobs=news_jobs_enabled,
        )
        self.scheduler.start()
        self._running = True
        self._trading_jobs_registered = trading_jobs_enabled
        self._news_jobs_registered = news_jobs_enabled
        self._common_jobs_registered = True
        if trading_jobs_enabled:
            logger.info("스케줄러 시작 — 트레이딩 타임라인 활성화")
        else:
            logger.info("뉴스 폴링 스케줄러 시작 — 트레이딩 스케줄러 비활성")

        # 서버 기동 시 현재 상태에 맞는 초기 작업 실행
        if trading_jobs_enabled:
            self._spawn_background_task(
                self._on_startup(),
                task_name="trading_startup",
            )
        if news_jobs_enabled:
            self._spawn_background_task(
                self._news_poll(),
                task_name="initial_news_poll",
            )
            self._spawn_background_task(
                self._news_translation_backfill(),
                task_name="initial_news_translation_backfill",
            )

    async def stop(self) -> None:
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            self._trading_jobs_registered = False
            self._news_jobs_registered = False
            self._common_jobs_registered = False
            self.scheduler = self._build_scheduler()
            logger.info("스케줄러 중지")

    async def wait_until_idle(
        self,
        *,
        timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.1,
    ) -> bool:
        deadline = _time.perf_counter() + max(float(timeout_sec), 0.0)
        interval = max(float(poll_interval_sec), 0.01)

        while True:
            if not self._news_poll_lock.locked() and not self._background_tasks:
                return True
            if _time.perf_counter() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def _resource_snapshot(self) -> None:
        await observability_service.record_resource_snapshot()

    async def _account_equity_snapshot(self) -> None:
        await account_equity_service.capture_and_record_current(
            session_phase="INTRADAY",
            detail={"reason": "scheduler_interval"},
        )
        try:
            from scheduler.jobs.portfolio_sync_job import _backfill_missing_open_buys_from_holdings

            summary = await _backfill_missing_open_buys_from_holdings()
            if int((summary or {}).get("backfilled") or 0) > 0:
                logger.warning("계좌 스냅샷 후 보유수량 백필 실행: {}", summary)
        except Exception as exc:
            logger.warning("계좌 스냅샷 후 보유수량 백필 실패: {}", str(exc))

    async def _observability_maintenance(self) -> None:
        started_at = _time.perf_counter()
        try:
            summary = await observability_maintenance_service.run_maintenance()
            elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
            await observability_service.record_execution_metric(
                metric_type="JOB",
                metric_name="OBSERVABILITY_MAINTENANCE",
                status="SUCCESS",
                elapsed_ms=elapsed_ms,
                detail=summary,
            )
        except Exception as exc:
            elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
            await observability_service.record_execution_metric(
                metric_type="JOB",
                metric_name="OBSERVABILITY_MAINTENANCE",
                status="ERROR",
                elapsed_ms=elapsed_ms,
                detail={"error": str(exc)},
            )
            raise

    async def _forward_return_label(self) -> None:
        started_at = _time.perf_counter()
        try:
            summary = await forward_return_label_job.run_once()
            elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
            await observability_service.record_execution_metric(
                metric_type="JOB",
                metric_name="FORWARD_RETURN_LABEL",
                status="SUCCESS",
                elapsed_ms=elapsed_ms,
                detail=summary,
            )
        except Exception as exc:
            elapsed_ms = int((_time.perf_counter() - started_at) * 1000)
            await observability_service.record_execution_metric(
                metric_type="JOB",
                metric_name="FORWARD_RETURN_LABEL",
                status="ERROR",
                elapsed_ms=elapsed_ms,
                detail={"error": str(exc)},
            )
            raise

    def _setup_jobs(
        self,
        *,
        include_trading_jobs: bool = True,
        include_news_jobs: bool = True,
        include_common_jobs: bool = True,
    ) -> None:
        from scheduler.jobs.portfolio_sync_job import portfolio_sync_job
        from scheduler.jobs.market_data_job import market_data_job

        if include_trading_jobs:
            # ── 장 시작 전 준비 (08:50 평일) — KRX 개장 10분 전 ──
            self.scheduler.add_job(
                self._pre_market,
                "cron",
                hour=8, minute=50,
                day_of_week="mon-fri",
                id="pre_market",
                name="장 시작 전 준비",
                misfire_grace_time=600,
            )

            # ── 장 시작 스캔 (09:05 평일) — 전체 시장 스캔 → 종목 선정 → 매매 시작 ──
            self.scheduler.add_job(
                self._market_open_scan,
                "cron",
                hour=9, minute=5,
                day_of_week="mon-fri",
                id="market_open_scan",
                name="장 시작 스캔 + 매매",
                misfire_grace_time=600,
            )

            # ── 장중 재스캔 (11:00, 13:00 평일) — 새로운 기회 탐색 ──
            self.scheduler.add_job(
                self._intraday_rescan,
                "cron",
                hour="11,13", minute=0,
                day_of_week="mon-fri",
                id="intraday_rescan",
                name="장중 재스캔",
                misfire_grace_time=600,
            )
            self.scheduler.add_job(
                self._intraday_rescan,
                "cron",
                minute=f"*/{max(int(settings.INTRADAY_RESCAN_INTERVAL_MIN or 10), 1)}",
                hour="9-14",
                day_of_week="mon-fri",
                id="intraday_rescan_interval",
                name="장중 정기 재스캔",
                misfire_grace_time=300,
                max_instances=1,
                coalesce=True,
            )

        if include_news_jobs:
            self.scheduler.add_job(
                self._news_poll,
                "interval",
                minutes=max(int(settings.NEWS_POLL_INTERVAL_MIN_TRADING or 5), 1),
                id="news_poll_trading",
                name="장중 뉴스 폴링",
                kwargs={"market_hours": True},
            )

            self.scheduler.add_job(
                self._news_poll,
                "interval",
                minutes=max(int(settings.NEWS_POLL_INTERVAL_MIN_OFF_HOURS or 30), 1),
                id="news_poll_off_hours",
                name="장외 뉴스 폴링",
                kwargs={"market_hours": False},
            )
            self.scheduler.add_job(
                self._news_translation_backfill,
                "interval",
                minutes=5,
                id="news_translation_backfill",
                name="뉴스 번역 백로그 처리",
            )

        if include_common_jobs:
            if bool(getattr(settings, "METRICS_RESOURCE_SAMPLING_ENABLED", True)):
                self.scheduler.add_job(
                    self._resource_snapshot,
                    "interval",
                    minutes=max(int(getattr(settings, "METRICS_RESOURCE_INTERVAL_MIN", 5) or 5), 1),
                    id="resource_snapshot",
                    name="리소스 스냅샷",
                )

            if bool(getattr(settings, "METRICS_MAINTENANCE_ENABLED", True)):
                self.scheduler.add_job(
                    self._observability_maintenance,
                    "interval",
                    minutes=max(int(getattr(settings, "METRICS_MAINTENANCE_INTERVAL_MIN", 60) or 60), 1),
                    id="observability_maintenance",
                    name="운영 메트릭 롤업/정리",
                )

            if bool(getattr(settings, "FORWARD_RETURN_LABEL_ENABLED", True)):
                self.scheduler.add_job(
                    self._forward_return_label,
                    "interval",
                    minutes=max(int(getattr(settings, "FORWARD_RETURN_LABEL_INTERVAL_MIN", 5) or 5), 1),
                    id="forward_return_label",
                    name="Decision forward return 라벨링",
                )

        if include_trading_jobs:
            self.scheduler.add_job(
                self._account_equity_snapshot,
                "cron",
                minute="*/5",
                hour="9-15",
                day_of_week="mon-fri",
                id="account_equity_snapshot",
                name="계좌 자산 스냅샷",
                misfire_grace_time=300,
            )

            if bool(getattr(settings, "FAST_HOLDINGS_GUARD_ENABLED", True)):
                self.scheduler.add_job(
                    self._fast_holdings_guard,
                    "interval",
                    minutes=max(int(getattr(settings, "FAST_HOLDINGS_GUARD_INTERVAL_MIN", 3) or 3), 1),
                    id="fast_holdings_guard",
                    name="빠른 보유 가격 가드",
                    misfire_grace_time=120,
                )

            # ── 장중 보유종목 점검 (1시간 간격, 09:00~15:00) — WebSocket 보완용 안전망 ──
            self.scheduler.add_job(
                self._holdings_check,
                "cron",
                minute="0,15,30,45",
                hour="9-14",
                day_of_week="mon-fri",
                id="holdings_check",
                name="보유종목 손절/익절 점검",
                misfire_grace_time=300,
            )

            # ── 장중 보유종목 AI 재평가 (30분 간격, 09:00~14:00) — 맥락 기반 HOLD/SELL + 임계값 조정 ──
            self.scheduler.add_job(
                self._intraday_holdings_review,
                "cron",
                minute="0,30",
                hour="9-14",
                day_of_week="mon-fri",
                id="intraday_holdings_review",
                name="장중 보유종목 AI 재평가",
                misfire_grace_time=600,
            )

            # ── 장 마감 전 보유 심사 (15:10 평일) — DAY_TRADING: 전량 매도 / 스윙: AI 보유 심사 ──
            self.scheduler.add_job(
                self._force_liquidation,
                "cron",
                hour=settings.FORCE_LIQUIDATION_HOUR,
                minute=settings.FORCE_LIQUIDATION_MINUTE,
                day_of_week="mon-fri",
                id="force_liquidation",
                name="장 마감 전 보유 심사",
                misfire_grace_time=300,
            )

            # ── 장 마감 리뷰 (15:40 평일) — KRX 종가 기반 성과 리뷰 ──
            self.scheduler.add_job(
                self._post_market,
                "cron",
                hour=15, minute=40,
                day_of_week="mon-fri",
                id="post_market",
                name="장 마감 성과 리뷰",
                misfire_grace_time=3600,
            )

            # ── 포트폴리오 정산 (16:00) ──
            self.scheduler.add_job(
                portfolio_sync_job,
                "cron",
                hour=16, minute=0,
                id="portfolio_sync",
                name="포트폴리오 정산",
                misfire_grace_time=3600,
            )

            # ── 주간 캘리브레이션·IC 검증 (금요일 16:10) ──
            # post_market(15:40) + portfolio_sync(16:00) 직후 한 주 데이터로
            # LLM 신뢰도 보정과 pre-LLM 신호 IC를 자동으로 재측정해 활동 로그에
            # 요약을 남긴다. 결과는 runtime/reports/weekly_review_*.json에 보관.
            from scheduler.jobs.calibration_review_job import calibration_review_job
            self.scheduler.add_job(
                calibration_review_job,
                "cron",
                hour=16, minute=10,
                day_of_week="fri",
                id="weekly_calibration_review",
                name="주간 캘리브레이션·IC 검증",
                misfire_grace_time=3600,
            )

            # ── 일봉 데이터 수집 (16:30) ──
            self.scheduler.add_job(
                market_data_job,
                "cron",
                hour=16, minute=30,
                id="market_data",
                name="일봉 데이터 수집",
                misfire_grace_time=3600,
            )

            # ── 만료 추천 정리 (1시간 간격) ──
            self.scheduler.add_job(
                self._expire_recommendations,
                "interval",
                hours=1,
                id="expire_recommendations",
                name="만료 추천 처리",
            )

    # ─────────── 스케줄 작업 구현 ───────────

    async def _on_startup(self) -> None:
        """서버 기동 시 현재 시간대에 맞는 초기 작업 실행"""
        import asyncio
        from scheduler.market_calendar import market_calendar

        # 기동 직후 약간의 딜레이 (MCP 연결 안정화)
        await asyncio.sleep(3)

        if market_calendar.is_krx_trading_hours():
            if not settings.TRADING_ENABLED:
                logger.info("서버 기동: 장중이지만 TRADING_ENABLED=false → startup 시장 스캔 스킵")
                return
            logger.debug("서버 기동: 장중 → 즉시 시장 스캔 + 매매 시작")
            # 매매 사이클 전에 스냅샷을 한 번 새로 잡아 STALE 가드가 신규 매수를 차단하지 않도록 한다.
            try:
                await self._account_equity_snapshot()
            except Exception as exc:
                logger.warning("기동 시 계좌 스냅샷 갱신 실패: {}", str(exc))
            asyncio.create_task(self._market_open_scan())
        else:
            next_open = market_calendar.next_krx_open()
            logger.debug("서버 기동: 장외 → 다음 장 시작: {}", next_open.strftime("%m/%d %H:%M"))
            # 장외 기동 시 리뷰가 아직 안 되었으면 실행
            asyncio.create_task(self._post_market_if_needed())

    async def _pre_market(self) -> None:
        """장 시작 전 준비 (08:50) — 어제 리뷰 피드백 확인"""
        from scheduler.market_calendar import market_calendar
        from services.activity_logger import activity_logger

        if market_calendar.is_krx_holiday():
            holiday_name = market_calendar.get_holiday_name() or "공휴일"
            logger.debug("오늘은 휴장일 ({}) — 장 시작 전 준비 스킵", holiday_name)
            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                f"\U0001f3d6\ufe0f 오늘은 휴장일 ({holiday_name}) — 매매 스킵",
            )
            return

        logger.debug("=== 장 시작 전 준비 (08:50) ===")
        await activity_logger.log(
            ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
            "\u2615 장 시작 전 준비 — 10분 후 KRX 개장",
        )

        # 1. 일일 기준 자산 설정 (데이트레이딩 손익 계산용)
        try:
            from agent.trading_agent import trading_agent
            from trading.account_manager import account_manager

            balance = await account_manager.get_balance()
            trading_agent._daily_start_balance = balance.total_asset
            logger.debug("일일 기준 자산 설정: {:,.0f}원", balance.total_asset)
        except Exception as e:
            logger.warning("기준 자산 설정 실패: {}", str(e))

        # 2. 어제 리뷰 피드백 확인 (AI 학습용)
        try:
            from datetime import timedelta
            from util.time_util import now_kst
            from core.database import AsyncSessionLocal
            from repositories.daily_report_repository import DailyReportRepository

            yesterday = (now_kst() - timedelta(days=1)).date()
            async with AsyncSessionLocal() as session:
                repo = DailyReportRepository(session)
                report = await repo.get_by_date(yesterday)
                if report and report.lessons_learned:
                    await activity_logger.log(
                        ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                        f"\U0001f4cb 어제 리뷰 피드백: {report.lessons_learned[:200]}",
                    )
        except Exception as e:
            logger.debug("어제 리뷰 로드 실패: {}", str(e))

        # 3. 오버나이트 포지션 점검 (스윙 모드)
        if not settings.DAY_TRADING_ONLY:
            await self._check_overnight_positions()

        # 4. 활성 트레이딩 규칙 로드 + 적용 (일일 리뷰 피드백 자동 학습)
        try:
            from analysis.feedback.trading_rules import trading_rule_engine
            from agent.trading_agent import trading_agent
            from strategy.risk_manager import risk_manager

            active_rules = await trading_rule_engine.load_active_rules()
            rules = active_rules.get("rules", [])

            if rules:
                trading_rule_engine.apply_to_strategies(
                    trading_agent.strategies, active_rules,
                )
                trading_rule_engine.apply_to_risk_manager(
                    risk_manager, active_rules,
                )
                trading_agent._active_trading_rules = active_rules

                rule_summary = ", ".join(
                    f"{r.param_name}={r.param_value}" for r in rules[:5]
                )
                await activity_logger.log(
                    ActivityType.TRADING_RULE, ActivityPhase.COMPLETE,
                    f"📋 트레이딩 규칙 {len(rules)}건 적용: {rule_summary}",
                )
                await trading_rule_engine.record_application(
                    [r.id for r in rules]
                )

            expired = await trading_rule_engine.expire_old_rules()
            if expired:
                logger.debug("만료된 트레이딩 규칙 {}건 비활성화", expired)
        except Exception as e:
            logger.warning("트레이딩 규칙 로드 실패: {}", str(e))

    async def _market_open_scan(self) -> None:
        """장 시작 직후 (09:05) — 전체 시장 스캔 → 종목 선정 → 매매

        AI Agent가 전체 시장 데이터를 받아서 어떤 종목에 투자할지 판단하고,
        선정된 종목을 WebSocket 실시간 구독에 등록하여 이후 이벤트 기반 매매.
        """
        from agent.trading_agent import trading_agent
        from scheduler.market_calendar import market_calendar
        from services.activity_logger import activity_logger

        if market_calendar.is_krx_holiday():
            logger.debug("휴장일 — 장 시작 스캔 스킵")
            return
        if not settings.TRADING_ENABLED:
            logger.info("TRADING_ENABLED=false → 장 시작 스캔/AI 매매 사이클 스킵")
            await activity_logger.log(
                ActivityType.SCHEDULE,
                ActivityPhase.SKIP,
                "TRADING_ENABLED=false → 장 시작 스캔/AI 매매 사이클 스킵",
            )
            return

        logger.debug("=== 장 시작 첫 스캔 (09:05) — 전체 시장 분석 + 매매 시작 ===")
        await activity_logger.log(
            ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
            "\U0001f514 장 시작! 전체 시장 스캔 → AI 종목 선정 → 분석/매매 시작",
        )

        try:
            # 0. 오버나이트 포지션 갭 체크 (스윙 모드)
            if not settings.DAY_TRADING_ONLY:
                await self._check_overnight_gap()

            # 1. AI Agent 매매 사이클 실행 (전체 시장 스캔 → 분석 → 매매)
            result = await trading_agent.run_cycle()

            # 2. 실시간 감시 후보 + 보유종목을 WebSocket 구독
            selected = result.get("monitor_symbols") or result.get("selected_symbols", [])

            # 보유종목 추가
            from trading.account_manager import account_manager
            holdings = await account_manager.get_holdings()
            holding_symbols = [(h.symbol, "KRX") for h in holdings if h.symbol]

            from realtime.stream_manager import SubscriptionPriority, SubscriptionRequest

            # StreamManager가 우선순위와 한도를 적용한다. 보유종목은 신규 후보보다 우선 감시한다.
            subscription_requests = {
                s: SubscriptionRequest(symbol=s, market=m, priority=SubscriptionPriority.NEW_CANDIDATE)
                for s, m in selected
            }
            subscription_requests.update({
                s: SubscriptionRequest(symbol=s, market=m, priority=SubscriptionPriority.HELD_POSITION)
                for s, m in holding_symbols
            })
            all_symbols = list(subscription_requests.values())

            if all_symbols:
                from realtime.stream_manager import stream_manager
                await stream_manager.update_subscriptions(all_symbols)

            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                f"\u2705 장 시작 완료 — 분석 {result.get('analyzed', 0)}건, "
                f"매매 {result.get('executed', 0)}건, "
                f"실시간 감시 {len(all_symbols)}종목 → 모니터링 돌입",
            )
        except Exception as e:
            logger.error("장 시작 스캔 오류: {}", str(e))

    async def _intraday_rescan(self) -> None:
        """장중 재스캔 (11:00, 13:00) — 새로운 기회 탐색

        기존 run_cycle()을 재사용하여 시장 재스캔 → 분석 → 매매.
        cycle_lock이 잡혀있으면 자동 스킵.
        """
        from agent.trading_agent import trading_agent
        from scheduler.market_calendar import market_calendar
        from services.activity_logger import activity_logger
        from util.time_util import now_kst

        if market_calendar.is_krx_holiday():
            return
        if not settings.TRADING_ENABLED:
            logger.info("TRADING_ENABLED=false → 장중 재스캔/AI 매매 사이클 스킵")
            await activity_logger.log(
                ActivityType.SCHEDULE,
                ActivityPhase.SKIP,
                "TRADING_ENABLED=false → 장중 재스캔/AI 매매 사이클 스킵",
            )
            return

        # 매수 마감 시간 이후면 재스캔 불필요
        if settings.DAY_TRADING_ONLY:
            from datetime import time as _time
            cutoff = _time(settings.BUY_CUTOFF_HOUR, settings.BUY_CUTOFF_MINUTE)
            if now_kst().time() >= cutoff:
                logger.debug("매수 마감 시간 경과 → 장중 재스캔 스킵")
                return

        logger.debug("=== 장중 재스캔 시작 ({}) ===", now_kst().strftime("%H:%M"))
        await activity_logger.log(
            ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
            f"\U0001f504 장중 재스캔 시작 ({now_kst().strftime('%H:%M')}) — 새로운 기회 탐색",
        )

        try:
            result = await trading_agent.run_cycle()

            # 실시간 감시 후보 WebSocket 구독 갱신
            selected = result.get("monitor_symbols") or result.get("selected_symbols", [])
            if selected:
                from trading.account_manager import account_manager
                from realtime.stream_manager import SubscriptionPriority, SubscriptionRequest, stream_manager
                holdings = await account_manager.get_holdings()
                holding_symbols = [(h.symbol, "KRX") for h in holdings if h.symbol]
                subscription_requests = {
                    s: SubscriptionRequest(symbol=s, market=m, priority=SubscriptionPriority.NEW_CANDIDATE)
                    for s, m in selected
                }
                subscription_requests.update({
                    s: SubscriptionRequest(symbol=s, market=m, priority=SubscriptionPriority.HELD_POSITION)
                    for s, m in holding_symbols
                })
                all_symbols = list(subscription_requests.values())
                if all_symbols:
                    await stream_manager.update_subscriptions(all_symbols)

            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                f"\u2705 장중 재스캔 완료 — 분석 {result.get('analyzed', 0)}건, "
                f"매매 {result.get('executed', 0)}건",
            )
        except Exception as e:
            logger.error("장중 재스캔 오류: {}", str(e))

    async def _update_realtime_subscriptions(self) -> None:
        """보유종목 WebSocket 구독 갱신 (임계값은 AI가 설정)"""
        try:
            from trading.account_manager import account_manager
            from realtime.stream_manager import SubscriptionPriority, SubscriptionRequest, stream_manager

            holdings = await account_manager.get_holdings()
            if holdings:
                symbols = [
                    SubscriptionRequest(symbol=h.symbol, market="KRX", priority=SubscriptionPriority.HELD_POSITION)
                    for h in holdings
                    if h.symbol
                ]
                await stream_manager.update_subscriptions(symbols)
                logger.debug("WebSocket 구독 갱신: {}종목", len(symbols))
        except Exception as e:
            logger.warning("WebSocket 구독 갱신 실패: {}", str(e))

    async def _news_poll(
        self,
        market_hours: bool | None = None,
        *,
        trigger_mode: str | None = None,
        trigger_reason: str | None = None,
    ) -> None:
        """뉴스 자동 폴링 + 신규 뉴스 이벤트 발행"""
        if not settings.NEWS_POLL_ENABLED:
            return

        from core.database import AsyncSessionLocal
        from scheduler.market_calendar import market_calendar
        from services.news_polling_service import news_polling_service

        actual_market_hours = market_calendar.is_krx_trading_hours()
        if market_hours is not None and actual_market_hours != market_hours:
            return

        runtime_mode = trigger_mode or ("AUTO_TRADING" if actual_market_hours else "AUTO_OFF_HOURS")

        try:
            async with self._news_poll_lock:
                async with AsyncSessionLocal() as session:
                    summary = await news_polling_service.poll_sources(
                        session,
                        market_hours=actual_market_hours,
                        mode=runtime_mode,
                    )
                    await session.commit()
                await news_polling_service.log_activity_from_summary(summary)
                metric_payload = summary.get("metric_payload")
                if isinstance(metric_payload, dict):
                    await observability_service.record_news_poll(**metric_payload)
            if summary.get("skipped"):
                logger.debug("뉴스 폴링 스킵: {}", summary.get("reason", "unknown"))
            if summary.get("created"):
                logger.info(
                    "뉴스 폴링 완료: 신규 {}건, 이벤트 {}건",
                    summary.get("created", 0),
                    summary.get("published_events", 0),
                )
            elif trigger_reason:
                logger.debug("이벤트 기반 뉴스 폴링 완료: {} ({})", runtime_mode, trigger_reason)
        except Exception as e:
            logger.warning("뉴스 폴링 오류: {}", str(e))
            await error_capture_service.capture_exception(
                component="scheduler",
                operation="news_poll",
                exc=e,
                detail={
                    "trigger_mode": runtime_mode,
                    "trigger_reason": trigger_reason,
                    "market_hours": actual_market_hours,
                },
            )

    async def _news_translation_backfill(self) -> None:
        if not settings.NEWS_LLM_ENABLED:
            return

        from core.database import AsyncSessionLocal
        from scheduler.market_calendar import market_calendar

        actual_market_hours = market_calendar.is_krx_trading_hours()
        try:
            async with AsyncSessionLocal() as session:
                summary = await news_translation_backfill_service.process_pending(
                    session,
                    market_hours=actual_market_hours,
                )
                await session.commit()
            await observability_service.record_execution_metric(
                metric_type="JOB",
                metric_name="NEWS_TRANSLATION_BACKFILL",
                status=str(summary.get("status") or "IDLE"),
                elapsed_ms=0,
                detail=summary,
            )
        except Exception as e:
            logger.warning("뉴스 번역 백로그 처리 오류: {}", str(e))
            await error_capture_service.capture_exception(
                component="scheduler",
                operation="news_translation_backfill",
                exc=e,
                detail={"market_hours": actual_market_hours},
            )

    async def _holdings_check(self) -> None:
        """보유종목 현재가 점검 — WebSocket 보완용 안전망 + 시간 기반 조기 청산

        WebSocket 끊김이나 누락 대비, MCP로 보유종목 현재가를 직접 조회하여
        손절/익절 조건을 체크한다. 데이트레이딩 모드에서는 잔여 시간에 따라
        조기 익절/손절도 실행한다. KRX 장중(09:00~15:30)에만 작동.
        """
        from services.activity_logger import activity_logger
        from util.time_util import now_kst
        from scheduler.market_calendar import market_calendar

        current_dt = now_kst()
        try:
            is_automated_session = market_calendar.is_automated_trading_session(current_dt)
        except TypeError:
            is_automated_session = market_calendar.is_automated_trading_session()
        if not is_automated_session:
            return

        try:
            from trading.account_manager import account_manager

            holdings = await account_manager.get_holdings()
            if not holdings:
                return

            from core.database import AsyncSessionLocal
            from repositories.trade_result_repository import TradeResultRepository

            try:
                async with AsyncSessionLocal() as session:
                    repo = TradeResultRepository(session)
                    open_positions = await repo.get_all_open()
            except Exception as exc:
                logger.debug("보유종목 점검 open position 조회 생략: {}", str(exc))
                open_positions = []
            open_map = {
                normalize_krx_symbol(getattr(tr, "stock_symbol", "")): tr
                for tr in open_positions
                if normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
            }

            # 구독 갱신 (WebSocket 연결 복원 대비)
            await self._update_realtime_subscriptions()

            # 강제 청산까지 남은 시간 계산
            close_time = current_dt.replace(
                hour=settings.FORCE_LIQUIDATION_HOUR,
                minute=settings.FORCE_LIQUIDATION_MINUTE,
                second=0, microsecond=0,
            )
            minutes_left = max(0, int((close_time - current_dt).total_seconds() / 60))

            alerts = []
            for h in holdings:
                symbol = normalize_krx_symbol(getattr(h, "symbol", ""))
                if not symbol:
                    continue
                if h.avg_buy_price <= 0 or h.quantity <= 0:
                    continue
                # MCP로 현재가 직접 조회
                current = await self._fetch_current_price(symbol)
                if current <= 0:
                    continue
                pnl_rate = (current - h.avg_buy_price) / h.avg_buy_price * 100

                should_sell = False
                reason = ""

                # AI가 설정한 임계값이 있으면 우선 사용, 없으면 기본값
                from realtime.event_detector import event_detector
                th = event_detector.get_thresholds(symbol)
                tr = open_map.get(symbol)
                horizon = self._trade_horizon_from_result(tr) if tr else TradeHorizon.MID
                restored_thresholds = self._persisted_threshold_kwargs(
                    tr,
                    current_thresholds=th,
                )
                if restored_thresholds:
                    event_detector.set_thresholds(symbol, **restored_thresholds)
                    th = event_detector.get_thresholds(symbol)
                    await activity_logger.log(
                        ActivityType.HOLDINGS_CHECK,
                        ActivityPhase.PROGRESS,
                        f"♻️ {h.name}({symbol}) AI 손절/익절 임계값 복원",
                        symbol=symbol,
                        detail={
                            "action": "RESTORE_AI_EXIT_THRESHOLDS",
                            **restored_thresholds,
                        },
                    )

                if th.stop_loss <= 0 and th.take_profit <= 0:
                    alerts.append(f"⚠️ {h.name}({symbol}): AI 손절/익절 미설정 — 기본값 적용 중")

                stop_loss_pct = self._default_stop_loss_pct(horizon)
                take_profit_pct = self._default_take_profit_pct(horizon)
                if th.stop_loss > 0 and h.avg_buy_price > 0:
                    stop_loss_pct = ((th.stop_loss - h.avg_buy_price) / h.avg_buy_price) * 100
                if th.take_profit > 0 and h.avg_buy_price > 0:
                    take_profit_pct = ((th.take_profit - h.avg_buy_price) / h.avg_buy_price) * 100

                sell_quantity = int(h.quantity)
                exit_reason = "HOLDINGS_CHECK"

                if tr:
                    new_stop = self._breakeven_stop_price(
                        avg_buy_price=float(h.avg_buy_price),
                        pnl_rate=pnl_rate,
                        tr=tr,
                    )
                    if new_stop and (th.stop_loss <= 0 or new_stop > th.stop_loss):
                        event_detector.set_thresholds(symbol, stop_loss=new_stop)
                        await self._update_open_position_stop_loss(symbol, new_stop)
                        th = event_detector.get_thresholds(symbol)
                        stop_loss_pct = ((th.stop_loss - h.avg_buy_price) / h.avg_buy_price) * 100
                        await activity_logger.log(
                            ActivityType.HOLDINGS_CHECK,
                            ActivityPhase.PROGRESS,
                            f"🛡️ {h.name}({symbol}) 본전스탑 상향: {new_stop:,.0f}원",
                            symbol=symbol,
                            detail={
                                "action": "BREAKEVEN_STOP",
                                "pnl_rate": pnl_rate,
                                "stop_loss": new_stop,
                                "horizon": self._trade_horizon_from_result(tr),
                            },
                        )

                    do_partial, partial_qty, partial_reason = self._should_partial_take_profit(
                        tr=tr,
                        pnl_rate=pnl_rate,
                        holding_quantity=int(h.quantity),
                    )
                    if do_partial:
                        should_sell = True
                        sell_quantity = partial_qty
                        exit_reason = "PARTIAL_TAKE_PROFIT"
                        reason = partial_reason

                if not should_sell and tr:
                    trail_sell, trail_reason, trail_detail = self._evaluate_trailing_profit_guard(
                        symbol=symbol,
                        avg_buy_price=float(h.avg_buy_price),
                        current_price=current,
                        pnl_rate=pnl_rate,
                        tr=tr,
                    )
                    if trail_sell:
                        should_sell = True
                        exit_reason = "TRAILING_PROFIT_GUARD"
                        reason = trail_reason
                        await activity_logger.log(
                            ActivityType.HOLDINGS_CHECK,
                            ActivityPhase.PROGRESS,
                            f"🧭 {h.name}({symbol}) 트레일링 수익보호 발동: {trail_reason}",
                            symbol=symbol,
                            detail={
                                "action": "TRAILING_PROFIT_GUARD",
                                **trail_detail,
                            },
                        )

                # 손절/익절
                if not should_sell and pnl_rate <= stop_loss_pct:
                    reason = f"손절 도달 ({pnl_rate:+.1f}%, 기준 {stop_loss_pct:+.1f}%)"
                    defer_sell, defer_reason = self._should_defer_soft_stop(
                        symbol,
                        pnl_rate=pnl_rate,
                        stop_loss_pct=stop_loss_pct,
                        minutes_left=minutes_left,
                        observed_at=current_dt.timestamp(),
                        scope="holdings_check",
                    )
                    if defer_sell:
                        alerts.append(
                            f"👀 {h.name}({symbol}): {reason} — 완충 확인 중 "
                            f"(얕은 이탈, 다음 점검까지 보류)"
                        )
                        continue
                    should_sell = True
                    if defer_reason == "confirmed":
                        reason += " — 2회 연속 확인"
                    elif defer_reason == "hard_breach":
                        reason += " — 손절선 깊게 이탈"
                    elif defer_reason == "near_close":
                        reason += " — 장마감 임박"
                elif not should_sell and pnl_rate >= take_profit_pct:
                    should_sell = True
                    reason = f"익절 도달 ({pnl_rate:+.1f}%, 기준 {take_profit_pct:+.1f}%)"
                # 시간 기반 조건 (데이트레이딩 전용)
                elif not should_sell and settings.DAY_TRADING_ONLY:
                    if minutes_left <= 60 and pnl_rate > 1.0:
                        should_sell = True
                        reason = f"잔여 {minutes_left}분 + 수익 {pnl_rate:+.1f}% → 조기 익절"
                    elif minutes_left <= 30 and pnl_rate < -1.0:
                        should_sell = True
                        reason = f"잔여 {minutes_left}분 + 손실 {pnl_rate:+.1f}% → 조기 손절"

                if not should_sell and tr:
                    scale_reason = self._scale_in_candidate_reason(
                        tr=tr,
                        pnl_rate=pnl_rate,
                        current_price=current,
                        active_stop_loss=th.stop_loss,
                    )
                    if scale_reason:
                        await activity_logger.log(
                            ActivityType.HOLDINGS_CHECK,
                            ActivityPhase.PROGRESS,
                            f"📌 {h.name}({symbol}) {scale_reason} — 자동 물타기 미실행, 후보 기록",
                            symbol=symbol,
                            detail={
                                "action": "SCALE_IN_CANDIDATE",
                                "pnl_rate": pnl_rate,
                                "current_price": current,
                                "avg_buy_price": h.avg_buy_price,
                                "stop_loss": th.stop_loss,
                                "horizon": self._trade_horizon_from_result(tr),
                            },
                        )

                if should_sell and settings.TRADING_ENABLED:
                    # P0-2: 이중 매도 방지
                    from agent.trading_agent import trading_agent
                    if not await trading_agent._acquire_sell(symbol):
                        alerts.append(
                            f"\u26a0\ufe0f {h.name}({symbol}): {reason} → 이미 매도 진행 중"
                        )
                        continue
                    try:
                        sell_resp = await self._place_market_sell(symbol, sell_quantity)
                        if sell_resp.success:
                            alerts.append(
                                f"\U0001f6a8 {h.name}({symbol}): {reason} → 매도 주문 접수"
                            )
                            await activity_logger.log(
                                ActivityType.ORDER, ActivityPhase.PROGRESS,
                                f"🚨 보유점검 매도 주문 접수: {h.name}({symbol}) "
                                f"{sell_quantity}주 — {reason} — 체결 확인 대기",
                                symbol=symbol,
                            )
                            confirmed = await self._track_scheduler_sell_confirmation(
                                holding=h,
                                response=sell_resp,
                                symbol=symbol,
                                quantity=int(sell_quantity),
                                expected_price=current,
                                exit_reason=exit_reason,
                            )
                            if confirmed:
                                alerts.append(
                                    f"✅ {h.name}({symbol}): {reason} → 매도 체결 확인 완료"
                                )
                                await activity_logger.log(
                                    ActivityType.ORDER, ActivityPhase.COMPLETE,
                                    f"📉 보유점검 매도 완료: {h.name}({symbol}) "
                                    f"{sell_quantity}주 — {reason} — 체결 확인 완료",
                                    symbol=symbol,
                                )
                                if sell_quantity >= int(h.quantity):
                                    event_detector.remove_levels(symbol)
                                    # 매도 성공 → 재스캔 트리거
                                    import asyncio
                                    asyncio.create_task(self._trigger_rescan_after_sell())
                            else:
                                alerts.append(
                                    f"⚠️ {h.name}({symbol}): {reason} → 매도 체결 확인 실패/취소"
                                )
                                await activity_logger.log(
                                    ActivityType.ORDER, ActivityPhase.ERROR,
                                    f"⚠️ 보유점검 매도 체결 확인 실패: {h.name}({symbol}) "
                                    f"{sell_quantity}주 — {reason}",
                                    symbol=symbol,
                                    detail={
                                        "action": "SELL_CONFIRM_FAILED",
                                        "source": "HOLDINGS_CHECK",
                                        "quantity": int(sell_quantity),
                                        "price": current,
                                        "order_id": getattr(sell_resp, "order_id", None),
                                        "exit_reason": exit_reason,
                                    },
                                )
                        else:
                            alerts.append(
                                f"\U0001f6a8 {h.name}({symbol}): {reason} → 매도 실패: {sell_resp.error or ''}"
                            )
                    except Exception as e:
                        alerts.append(
                            f"\u274c {h.name}({symbol}): {reason} → 매도 오류: {str(e)[:50]}"
                        )
                    finally:
                        trading_agent._release_sell(symbol)
                elif should_sell:
                    # TRADING_ENABLED=false이면 알림만
                    alerts.append(
                        f"\u26a0\ufe0f {h.name}({symbol}): {reason} (TRADING_ENABLED=false)"
                    )

            if alerts:
                await activity_logger.log(
                    ActivityType.HOLDINGS_CHECK, ActivityPhase.PROGRESS,
                    f"\U0001f50d 보유종목 점검 (잔여 {minutes_left}분):\n" + "\n".join(alerts),
                )
        except Exception as e:
            logger.warning("보유종목 점검 오류: {}", str(e))

    async def _fast_holdings_guard(self) -> None:
        """Short-cycle holdings guard for price-based sell protection.

        This intentionally reuses `_holdings_check` so broker order submission,
        duplicate-sell locking, and fill confirmation stay on the existing path.
        """
        await self._holdings_check()

    async def _post_market(self) -> None:
        """장 마감 성과 리뷰 (15:40, KRX 종가 기반)"""
        from agent.trading_agent import trading_agent
        from scheduler.market_calendar import market_calendar
        from services.activity_logger import activity_logger

        if market_calendar.is_krx_holiday():
            logger.debug("휴장일 — 장 마감 리뷰 스킵")
            return

        logger.debug("=== 장 마감 리뷰 시작 (15:40) ===")
        await activity_logger.log(
            ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
            "\U0001f319 장 마감 — 오늘 매매 성과 리뷰 시작",
        )

        try:
            await trading_agent.run_cycle()  # 장외이므로 자동으로 _run_after_hours_cycle 실행
        except Exception as e:
            logger.error("장 마감 리뷰 오류: {}", str(e))

    async def _post_market_if_needed(self) -> None:
        """장외 기동 시 오늘 리뷰가 아직 안 되었으면 실행"""
        try:
            from util.time_util import now_kst
            from core.database import AsyncSessionLocal
            from repositories.daily_report_repository import DailyReportRepository

            today = now_kst().date()
            async with AsyncSessionLocal() as session:
                repo = DailyReportRepository(session)
                existing = await repo.get_by_date(today)
                if existing:
                    logger.debug("오늘 리포트 이미 존재 — 장외 리뷰 스킵")
                    return

            # 거래일이고 15:30 이후면 리뷰 실행
            now = now_kst()
            from datetime import time
            from scheduler.market_calendar import market_calendar
            if market_calendar.is_krx_trading_day(now) and now.time() > time(15, 30):
                logger.debug("오늘 리뷰 미완료 — 장외 리뷰 실행")
                from agent.trading_agent import trading_agent
                await trading_agent.run_cycle()
        except Exception as e:
            logger.warning("장외 리뷰 체크 실패: {}", str(e))

    async def _force_liquidation(self) -> None:
        """장 마감 전 보유 심사

        DAY_TRADING_ONLY=True: 보유종목 전량 시장가 매도 (기존 동작)
        DAY_TRADING_ONLY=False: 종목별 AI 우선 판정 (HOLD/SELL), HOLD 가능
        """
        import asyncio
        from scheduler.market_calendar import market_calendar
        from services.activity_logger import activity_logger

        if market_calendar.is_krx_holiday():
            return

        if not settings.TRADING_ENABLED:
            logger.debug("매매 비활성 — 청산 스킵")
            return

        try:
            from trading.account_manager import account_manager

            holdings = await account_manager.get_holdings()
            pending_orders = await account_manager.get_pending_orders()
            if not holdings:
                await activity_logger.log(
                    ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                    "\u2705 보유종목 없음 — 장마감 보유 심사 불필요",
                )
                return

            pending_sell_qty_by_symbol: dict[str, int] = {}
            for order in pending_orders or []:
                if str(getattr(order, "side", "")) != "매도":
                    continue
                symbol = str(getattr(order, "symbol", "") or "")
                remaining_qty = max(int(getattr(order, "remaining_qty", 0) or 0), 0)
                if not symbol or remaining_qty <= 0:
                    continue
                pending_sell_qty_by_symbol[symbol] = pending_sell_qty_by_symbol.get(symbol, 0) + remaining_qty

            adjusted_sellable = []
            for holding in holdings:
                quantity = int(getattr(holding, "quantity", 0) or 0)
                if quantity <= 0:
                    continue
                pending_sell_qty = pending_sell_qty_by_symbol.get(getattr(holding, "symbol", ""), 0)
                available_qty = max(quantity - pending_sell_qty, 0)
                if available_qty <= 0:
                    logger.info(
                        "청산 스킵: {}({}) — 미체결 매도 {}주 대기 중",
                        holding.name, holding.symbol, pending_sell_qty,
                    )
                    continue
                if available_qty != quantity:
                    logger.info(
                        "청산 수량 보정: {}({}) {}주 → {}주 (미체결 매도 {}주 제외)",
                        holding.name, holding.symbol, quantity, available_qty, pending_sell_qty,
                    )
                if hasattr(holding, "model_copy"):
                    adjusted = holding.model_copy(update={"quantity": available_qty})
                else:
                    adjusted = copy.copy(holding)
                    setattr(adjusted, "quantity", available_qty)
                adjusted_sellable.append(adjusted)

            sellable = adjusted_sellable
            if not sellable:
                return

            # 스윙 모드: 종목별 HOLD/SELL 판정
            if not settings.DAY_TRADING_ONLY:
                to_sell, to_hold = await self._smart_liquidation(sellable)
            else:
                to_sell = sellable
                to_hold = []

            mode_label = "AI 보유 심사" if not settings.DAY_TRADING_ONLY else "강제 청산"
            logger.warning("=== 장 마감 전 {} 시작 (매도 {}건, HOLD {}건) ===",
                           mode_label, len(to_sell), len(to_hold))
            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                f"\U0001f50e 장마감 {mode_label} — 매도 {len(to_sell)}건, HOLD {len(to_hold)}건",
            )

            if not to_sell:
                return

            async def _sell_one(h):
                # P0-2: 이중 매도 방지
                from agent.trading_agent import trading_agent
                if not await trading_agent._acquire_sell(h.symbol):
                    return (None, h)
                try:
                    resp = await self._place_market_sell(h.symbol, h.quantity)
                    return (resp, h)
                finally:
                    trading_agent._release_sell(h.symbol)

            results = await asyncio.gather(
                *[_sell_one(h) for h in to_sell],
                return_exceptions=True,
            )

            sold_count = 0
            failed_holdings = []

            for r in results:
                if isinstance(r, Exception):
                    logger.error("청산 주문 오류: {}", str(r))
                    continue

                resp, h = r
                if resp is None:
                    # P2-6: 매도 스킵 (이미 매도 중이거나 잠금 실패)
                    continue
                if resp.success:
                    sold_count += 1
                    pnl_text = f"{h.pnl_rate:+.1f}%" if hasattr(h, "pnl_rate") else ""
                    await activity_logger.log(
                        ActivityType.ORDER, ActivityPhase.PROGRESS,
                        f"\U0001f6a8 청산 주문 접수: {h.name}({h.symbol}) "
                        f"{h.quantity}주 시장가 매도 {pnl_text} — 체결 확인 대기",
                        symbol=h.symbol,
                    )
                    exit_reason = "FORCE_LIQUIDATION" if settings.DAY_TRADING_ONLY else "CLOSE_REVIEW"
                    await self._record_liquidation_sell(h, resp, exit_reason=exit_reason)
                else:
                    failed_holdings.append(h)
                    logger.error(
                        "청산 실패: {}({}) — {}",
                        h.name, h.symbol, resp.error or "알 수 없는 오류",
                    )
                    await activity_logger.log(
                        ActivityType.ORDER, ActivityPhase.ERROR,
                        f"\u274c 청산 실패: {h.name}({h.symbol}) — {resp.error or ''}",
                        symbol=h.symbol,
                    )

            # 실패 종목 2차 재시도 (5초 후)
            if failed_holdings:
                logger.warning("청산 {}건 실패 → 5초 후 재시도", len(failed_holdings))
                await activity_logger.log(
                    ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                    f"\u26a0\ufe0f 청산 {len(failed_holdings)}건 실패 → 5초 후 재시도",
                )
                await asyncio.sleep(5)
                retry_results = await asyncio.gather(
                    *[_sell_one(h) for h in failed_holdings],
                    return_exceptions=True,
                )
                for r in retry_results:
                    if isinstance(r, Exception):
                        logger.error("청산 재시도 오류: {}", str(r))
                        continue
                    resp, h = r
                    if resp.success:
                        sold_count += 1
                        logger.info("청산 재시도 성공: {}({})", h.name, h.symbol)
                        exit_reason = "FORCE_LIQUIDATION" if settings.DAY_TRADING_ONLY else "CLOSE_REVIEW"
                        await self._record_liquidation_sell(h, resp, exit_reason=exit_reason)
                    else:
                        logger.error("청산 재시도 실패: {}({}) — {}", h.name, h.symbol, resp.error or "")

            summary = f"\U0001f50e 장마감 {mode_label} 주문 접수: {sold_count}건 매도"
            if to_hold:
                hold_names = ", ".join(f"{h.name}" for h in to_hold)
                summary += f" | HOLD {len(to_hold)}건: {hold_names}"
            if failed_holdings:
                summary += f" | 실패 {len(failed_holdings)}건"
            await activity_logger.log(ActivityType.SCHEDULE, ActivityPhase.PROGRESS, summary)

            # 매도한 종목만 이벤트 감시 임계값 제거 (HOLD 종목은 유지)
            from realtime.event_detector import event_detector
            sold_symbols = {h.symbol for h in to_sell}
            for h in holdings:
                if h.symbol in sold_symbols:
                    event_detector.remove_levels(h.symbol)

        except Exception as e:
            logger.error("장마감 보유 심사 오류: {}", str(e))
            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.ERROR,
                f"\u274c 장마감 보유 심사 오류: {str(e)[:100]}",
            )

    async def _record_liquidation_sell(self, holding, response, *, exit_reason: str = "FORCE_LIQUIDATION") -> bool:
        return await self._track_scheduler_sell_confirmation(
            holding=holding,
            response=response,
            symbol=getattr(holding, "symbol", ""),
            quantity=int(getattr(holding, "quantity", 0) or 0),
            expected_price=float(getattr(holding, "current_price", 0.0) or 0.0),
            exit_reason=exit_reason,
        )

    async def _track_scheduler_sell_confirmation(
        self,
        *,
        holding,
        response,
        symbol: str,
        quantity: int,
        expected_price: float,
        exit_reason: str,
    ) -> bool:
        order_id = str(getattr(response, "order_id", "") or "")
        if not order_id:
            logger.error(
                "SELL 체결 추적 스킵: {}({}) — 주문번호 없음",
                getattr(holding, "name", ""),
                symbol,
            )
            return False

        from agent.decision_maker import decision_maker
        pending_record_id = await decision_maker._create_pending_record(
            symbol=symbol,
            side="SELL",
            order_id=order_id,
            quantity=quantity,
            expected_price=expected_price,
            analysis_context={
                "stock_name": getattr(holding, "name", "") or symbol,
                "strategy_type": exit_reason,
                "ai_recommendation": "SELL",
            },
        )
        confirmed = await decision_maker.confirm_and_record(
            symbol=symbol,
            side="SELL",
            order_id=order_id,
            quantity=quantity,
            expected_price=expected_price,
            exit_reason=exit_reason,
            pending_record_id=pending_record_id,
        )
        return True if confirmed is None else bool(confirmed)

    async def _collect_holdings_data(
        self, sellable: list,
    ) -> tuple[list[dict], dict, list[dict]]:
        """보유종목 데이터 수집 — LLM 프롬프트용 공통 헬퍼

        Returns:
            (holdings_data, holdings_map, review_required)
            - holdings_data: LLM 프롬프트에 넣을 종목별 데이터 리스트
            - holdings_map: symbol → (holding, trade_result, current_price)
            - review_required: 데이터 수집 실패로 자동 청산하지 않고 확인이 필요한 항목
        """
        from core.database import AsyncSessionLocal
        from realtime.event_detector import event_detector
        from repositories.trade_result_repository import TradeResultRepository
        from strategy.holding_policy import (
            _calc_hold_days,
            _get_max_hold_days_for_trade,
            get_hold_extension_status,
        )

        holdings_data: list[dict] = []
        holdings_map: dict = {}
        review_required: list[dict] = []

        async with AsyncSessionLocal() as session:
            repo = TradeResultRepository(session)

            for h in sellable:
                try:
                    symbol = normalize_krx_symbol(getattr(h, "symbol", ""))
                    if not symbol:
                        review_required.append(self._holding_review_required(
                            h,
                            reason_code="SYMBOL_NORMALIZATION_FAILED",
                            reason="보유종목 심볼 정규화 실패",
                        ))
                        logger.warning("보유종목 심볼 정규화 실패 {} → REVIEW_REQUIRED", getattr(h, "symbol", ""))
                        continue
                    try:
                        current_price = await self._fetch_current_price(symbol)
                    except Exception as price_error:
                        review_required.append(self._holding_review_required(
                            h,
                            reason_code="PRICE_LOOKUP_FAILED",
                            reason=f"현재가 조회 실패: {str(price_error)[:120]}",
                        ))
                        logger.warning("현재가 조회 실패 {} → REVIEW_REQUIRED: {}", symbol, str(price_error))
                        continue

                    if current_price <= 0:
                        review_required.append(self._holding_review_required(
                            h,
                            reason_code="PRICE_LOOKUP_FAILED",
                            reason="현재가 조회 실패",
                        ))
                        logger.warning("현재가 조회 실패 {} → REVIEW_REQUIRED", symbol)
                        continue

                    trade_result = await repo.get_open_buy(symbol)

                    if trade_result is None:
                        review_required.append(self._holding_review_required(
                            h,
                            reason_code="TRADE_RESULT_MISSING",
                            reason="open BUY TradeResult 없음",
                        ))
                        logger.warning("TradeResult 없음 {} → REVIEW_REQUIRED", symbol)
                        continue

                    avg_price = h.avg_buy_price
                    pnl_rate = (current_price - avg_price) / avg_price * 100 if avg_price > 0 else 0.0
                    hold_days = _calc_hold_days(trade_result)
                    max_hold_days = _get_max_hold_days_for_trade(trade_result, settings)
                    hold_extension_status = get_hold_extension_status(trade_result, settings)

                    # 현재 event_detector 활성 임계값
                    th = event_detector.get_thresholds(symbol)
                    news_context = await self._build_holding_news_context(
                        session,
                        symbol=symbol,
                        name=h.name or trade_result.stock_name or symbol,
                    )

                    data = {
                        "symbol": symbol,
                        "stock_name": h.name or trade_result.stock_name or symbol,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "pnl_rate": pnl_rate,
                        "quantity": h.quantity,
                        "hold_days": hold_days,
                        "max_hold_days": max_hold_days,
                        "confidence": trade_result.ai_confidence or 0.0,
                        "target_price": trade_result.ai_target_price,
                        "stop_loss_price": trade_result.ai_stop_loss_price,
                        "strategy_type": trade_result.strategy_type or "N/A",
                        **hold_extension_status,
                        "active_stop_loss": th.stop_loss,
                        "active_take_profit": th.take_profit,
                        **news_context,
                    }
                    holdings_data.append(data)
                    holdings_map[symbol] = (h, trade_result, current_price)

                except Exception as e:
                    review_required.append(self._holding_review_required(
                        h,
                        reason_code="HOLDING_DATA_ERROR",
                        reason=f"보유종목 데이터 수집 오류: {str(e)[:120]}",
                    ))
                    logger.warning("보유종목 데이터 수집 오류 {} → REVIEW_REQUIRED: {}", getattr(h, "symbol", ""), str(e))

        if review_required:
            await self._record_holdings_review_required_metrics(review_required)

        return holdings_data, holdings_map, review_required

    async def _build_holding_news_context(self, session, *, symbol: str, name: str) -> dict:
        try:
            from services.news_context_service import news_context_service

            payload = await news_context_service.build_for_symbol(
                session,
                symbol=symbol,
                name=name,
            )
        except Exception as exc:
            logger.debug("보유 재평가 뉴스 컨텍스트 조회 실패 {}: {}", symbol, str(exc))
            return {
                "news_context_available": False,
                "news_context_tone": "LOOKUP_FAILED",
                "news_context_negative_pressure": None,
                "news_context_negative_count": 0,
                "news_context_positive_count": 0,
                "news_context_neutral_count": 0,
                "news_context_item_count": 0,
                "news_context_source_codes": [],
                "news_context_items": [],
                "news_context_prompt": (
                    "### 최근 뉴스 보조 컨텍스트\n"
                    "- 뉴스 컨텍스트 조회 실패. 뉴스는 중립으로 보고 가격/수급/리스크를 우선 판단하세요."
                ),
            }

        items = list(payload.get("items") or [])
        return {
            "news_context_available": bool(payload.get("available")),
            "news_context_tone": payload.get("tone"),
            "news_context_negative_pressure": payload.get("negative_pressure"),
            "news_context_negative_count": int(payload.get("negative_count") or 0),
            "news_context_positive_count": int(payload.get("positive_count") or 0),
            "news_context_neutral_count": int(payload.get("neutral_count") or 0),
            "news_context_item_count": len(items),
            "news_context_source_codes": sorted({
                str(item.get("source_code") or "").upper()
                for item in items
                if item.get("source_code")
            }),
            "news_context_items": items[:3],
            "news_context_prompt": str(payload.get("prompt") or ""),
        }

    @staticmethod
    def _holding_review_required(holding, *, reason_code: str, reason: str) -> dict:
        return {
            "holding": holding,
            "reason_code": reason_code,
            "reason": reason,
        }

    async def _record_holdings_review_required_metrics(self, review_required: list[dict]) -> None:
        for item in review_required:
            holding = item.get("holding")
            symbol = normalize_krx_symbol(getattr(holding, "symbol", ""))
            reason_code = str(item.get("reason_code") or "UNKNOWN").upper()
            reason = str(item.get("reason") or "")
            try:
                await observability_service.record_execution_metric(
                    metric_type="HOLDINGS_REVIEW",
                    metric_name="REVIEW_REQUIRED",
                    status="REVIEW_REQUIRED",
                    symbol=symbol or None,
                    item_count=1,
                    success_count=0,
                    error_count=1,
                    detail={
                        "stage": "HOLDINGS_DATA_COLLECTION",
                        "reason_code": reason_code,
                        "reason": reason,
                        "source_symbol": str(getattr(holding, "symbol", "") or ""),
                        "stock_name": str(getattr(holding, "name", "") or ""),
                    },
                )
            except Exception as exc:
                logger.debug("보유 재평가 REVIEW_REQUIRED metric 기록 실패 (무시): {}", str(exc))

    async def _record_holdings_review_decision_event(
        self,
        *,
        data: dict,
        holding,
        trade_result,
        current_price: float,
        decision: dict,
        source: str,
        reason_code: str,
        decision_stage: str = "HOLDINGS_REVIEW",
    ) -> None:
        """보유 재평가의 deterministic/cache 판단도 forward return 라벨링 대상으로 남긴다."""
        try:
            from services.decision_event_service import decision_event_service

            action = str(decision.get("action") or "HOLD").upper()
            await decision_event_service.record_event(
                cycle_id=None,
                symbol=str(data.get("symbol") or getattr(holding, "symbol", "")),
                stock_name=str(data.get("stock_name") or getattr(holding, "name", "") or ""),
                market="KRX",
                decision_stage=decision_stage,
                source=source,
                strategy_type=str(data.get("strategy_type") or getattr(trade_result, "strategy_type", "") or ""),
                tier1_decision=action,
                risk_gate_result=reason_code,
                final_action=action,
                confidence=float(decision.get("confidence") or 0.0),
                reference_price=float(current_price or 0.0),
                quantity=int(getattr(holding, "quantity", 0) or 0),
                provider="DETERMINISTIC",
                model=source.upper(),
                status="RECORDED",
                reason=str(decision.get("reason") or ""),
                metadata={
                    "ai_skipped": True,
                    "reason_code": reason_code,
                    "source": source,
                    "pnl_rate": data.get("pnl_rate"),
                    "hold_days": data.get("hold_days"),
                    "max_hold_days": data.get("max_hold_days"),
                    "news_context_available": data.get("news_context_available"),
                    "news_context_tone": data.get("news_context_tone"),
                    "news_context_negative_pressure": data.get("news_context_negative_pressure"),
                    "news_context_item_count": data.get("news_context_item_count"),
                    "news_context_source_codes": data.get("news_context_source_codes"),
                },
            )
        except Exception as exc:
            logger.debug("보유 재평가 decision event 기록 실패 (무시): {}", str(exc))

    @staticmethod
    def _hold_extension_hard_reject_reason(data: dict, current_price: float) -> str:
        pnl_rate = float(data.get("pnl_rate") or 0.0)
        if pnl_rate < -3.0:
            return f"손실 과대 ({pnl_rate:+.1f}% < -3%)"

        confidence = float(data.get("confidence") or 0.0)
        if confidence < 0.45:
            return f"AI 신뢰도 부족 ({confidence:.2f} < 0.45)"

        for key, label in (
            ("stop_loss_price", "AI 손절가"),
            ("active_stop_loss", "활성 손절가"),
        ):
            stop_price = float(data.get(key) or 0.0)
            if stop_price > 0 and current_price <= stop_price:
                return f"{label} 돌파/근접 (현재 {current_price:,.0f} ≤ {stop_price:,.0f})"

        for key, label in (
            ("target_price", "AI 목표가"),
            ("active_take_profit", "활성 익절가"),
        ):
            target_price = float(data.get(key) or 0.0)
            if target_price > 0 and current_price >= target_price:
                return f"{label} 도달 (현재 {current_price:,.0f} ≥ {target_price:,.0f})"

        return ""

    async def _apply_hold_extension_decision(
        self,
        *,
        symbol: str,
        trade_result,
        decision: dict,
        hold_days: int,
    ):
        from strategy.holding_policy import apply_hold_extension_decision
        from util.time_util import now_kst

        update = apply_hold_extension_decision(
            trade_result,
            decision=decision,
            hold_days=hold_days,
            config=settings,
            source="LLM",
            reviewed_at=now_kst(),
        )
        if update is None:
            return None

        trade_result.notes = update.updated_notes
        try:
            from core.database import AsyncSessionLocal
            from repositories.trade_result_repository import TradeResultRepository

            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                open_buy = await repo.get_open_buy(symbol)
                if open_buy:
                    open_buy.notes = update.updated_notes
                    await session.flush()
                    await session.commit()
        except Exception as exc:
            logger.warning("보유 연장 notes DB 반영 오류 {}: {}", symbol, str(exc))

        return update

    async def _smart_liquidation(self, sellable: list) -> tuple[list, list]:
        """스윙 모드: LLM Tier1 기반 종목별 HOLD/SELL 판정

        전 종목 데이터를 LLM에 일괄 전달하여 포트폴리오 맥락을 고려한 판정.
        LLM 실패 시 코드 룰(holding_policy) 폴백.

        Returns:
            (to_sell, to_hold) 두 리스트
        """
        import time

        from services.ai_skip_metric_service import ai_skip_metric_service
        from services.activity_logger import activity_logger
        from services.holdings_precheck_service import holdings_precheck_service
        from strategy.holding_policy import evaluate_overnight_hold

        to_sell = []
        to_hold = []

        # ── 1) 전 종목 데이터 수집 (공통 헬퍼) ──
        holdings_data, holdings_map, review_required = await self._collect_holdings_data(sellable)
        if review_required:
            to_hold.extend(item["holding"] for item in review_required)

        if not holdings_data:
            if review_required:
                lines = [
                    f"  - {getattr(item['holding'], 'name', item['holding'].symbol)}"
                    f"({item['holding'].symbol}): REVIEW_REQUIRED — {item['reason']}"
                    for item in review_required
                ]
                await activity_logger.log(
                    ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                    "📊 스마트 청산 데이터 확인 필요:\n" + "\n".join(lines),
                )
            return to_sell, to_hold

        # ── 2) LLM Tier1 단일 호출 (전 종목 일괄 판정) ──
        llm_decisions = {}  # symbol → {"action": ..., "reason": ..., "confidence": ...}
        prechecked_decisions = {}
        llm_provider = ""
        llm_elapsed_ms = 0

        try:
            from analysis.llm.llm_factory import llm_factory
            from analysis.llm.prompts.overnight_hold import (
                OVERNIGHT_HOLD_SYSTEM,
                build_overnight_prompt,
            )
            from core.json_utils import parse_llm_json

            # 시장 국면 가져오기
            from agent.trading_agent import trading_agent
            market_regime = trading_agent._market_regime or ""

            llm_candidates = []
            for data in holdings_data:
                symbol = data["symbol"]
                h, trade_result, current_price = holdings_map[symbol]
                precheck = holdings_precheck_service.evaluate(
                    holding=h,
                    trade_result=trade_result,
                    current_price=current_price,
                    settings=settings,
                )
                if precheck.should_skip_llm:
                    prechecked_decisions[symbol] = {
                        "action": precheck.action,
                        "reason": precheck.reason,
                        "confidence": 0.0,
                    }
                    await ai_skip_metric_service.record(
                        stage="HOLDINGS_PRECHECK",
                        reason_code=precheck.action,
                        skipped_tier="TIER1",
                        symbol=symbol,
                        detail={
                            "source": precheck.source,
                            "reason": precheck.reason,
                        },
                    )
                else:
                    llm_candidates.append(data)

            if llm_candidates:
                prompt = build_overnight_prompt(llm_candidates, market_regime)

                start = time.time()
                result_text, llm_provider = await llm_factory.generate_tier1(
                    prompt, system_prompt=OVERNIGHT_HOLD_SYSTEM,
                )
                llm_elapsed_ms = int((time.time() - start) * 1000)

                parsed = parse_llm_json(result_text)
                if parsed and "decisions" in parsed:
                    for d in parsed["decisions"]:
                        symbol = d.get("symbol", "")
                        if symbol and symbol in holdings_map:
                            llm_decisions[symbol] = {
                                "action": d.get("action", "SELL").upper(),
                                "reason": d.get("reason", ""),
                                "confidence": d.get("confidence", 0.0),
                                "extend_horizon": d.get("extend_horizon"),
                                "extension_days": d.get("extension_days"),
                            }

            logger.info(
                "스마트 청산 판정 완료: LLM {}건 / 정책 사전판단 {}건 / {} ({}ms)",
                len(llm_decisions), len(prechecked_decisions), llm_provider, llm_elapsed_ms,
            )
        except Exception as e:
            logger.warning("스마트 청산 LLM 호출 실패 → 코드 룰 폴백: {}", str(e))

        # ── 3) 판정 결과 분류 + 누락 종목 폴백 ──
        log_lines = [
            f"  - {getattr(item['holding'], 'name', item['holding'].symbol)}"
            f"({item['holding'].symbol}): REVIEW_REQUIRED — {item['reason']}"
            for item in review_required
        ]

        for data in holdings_data:
            symbol = data["symbol"]
            h, trade_result, current_price = holdings_map[symbol]
            stock_name = data["stock_name"]

            if symbol in prechecked_decisions:
                decision = prechecked_decisions[symbol]
                action = decision["action"]
                reason = decision["reason"]
                conf = decision["confidence"]
                await self._record_holdings_review_decision_event(
                    data=data,
                    holding=h,
                    trade_result=trade_result,
                    current_price=current_price,
                    decision=decision,
                    source="holdings_precheck",
                    reason_code=f"PRECHECK_{action}",
                    decision_stage="SMART_LIQUIDATION",
                )

                if action == "HOLD":
                    to_hold.append(h)
                else:
                    to_sell.append(h)
                log_lines.append(
                    f"  - {stock_name}({symbol}): {action} — {reason} (정책 사전판단)"
                )
                logger.info("스마트 청산 사전판단 {}: {} — {}", action, symbol, reason)
            elif symbol in llm_decisions:
                decision = llm_decisions[symbol]
                action = decision["action"]
                reason = decision["reason"]
                conf = decision["confidence"]

                if action == "HOLD":
                    to_hold.append(h)
                    log_lines.append(
                        f"  - {stock_name}({symbol}): HOLD — {reason} "
                        f"(AI 신뢰도: {conf:.2f})"
                    )
                elif action == "EXTEND":
                    hard_reject = self._hold_extension_hard_reject_reason(data, current_price)
                    if hard_reject:
                        to_sell.append(h)
                        log_lines.append(
                            f"  - {stock_name}({symbol}): SELL — 연장 거부: {hard_reject} "
                            f"(AI 신뢰도: {conf:.2f})"
                        )
                        logger.info("스마트 청산 EXTEND 하드가드 거부 → SELL: {} — {}", symbol, hard_reject)
                        continue

                    try:
                        update = await self._apply_hold_extension_decision(
                            symbol=symbol,
                            trade_result=trade_result,
                            decision=decision,
                            hold_days=int(data.get("hold_days") or 0),
                        )
                    except ValueError as exc:
                        to_sell.append(h)
                        log_lines.append(
                            f"  - {stock_name}({symbol}): SELL — 연장 불가: {str(exc)} "
                            f"(AI 신뢰도: {conf:.2f})"
                        )
                        logger.info("스마트 청산 EXTEND 거부 → SELL: {} — {}", symbol, str(exc))
                    else:
                        to_hold.append(h)
                        if update is None:
                            log_lines.append(
                                f"  - {stock_name}({symbol}): EXTEND→HOLD — {reason} "
                                f"(아직 연장 기록 시점 아님, AI 신뢰도: {conf:.2f})"
                            )
                        else:
                            log_lines.append(
                                f"  - {stock_name}({symbol}): EXTEND→HOLD — {reason} "
                                f"({update.current_horizon}→{update.next_horizon}, "
                                f"다음 심사 {update.extension_until_days}일, AI 신뢰도: {conf:.2f})"
                            )
                else:
                    to_sell.append(h)
                    log_lines.append(
                        f"  - {stock_name}({symbol}): SELL — {reason} "
                        f"(AI 신뢰도: {conf:.2f})"
                    )
                logger.info("스마트 청산 {}: {} — {}", action, symbol, reason)
            else:
                # LLM 응답에서 누락 → 코드 룰 폴백
                fallback = evaluate_overnight_hold(h, trade_result, current_price, settings)
                if fallback.action == "HOLD":
                    to_hold.append(h)
                else:
                    to_sell.append(h)
                log_lines.append(
                    f"  - {stock_name}({symbol}): {fallback.action} — "
                    f"{fallback.reason} (폴백)"
                )
                logger.info(
                    "스마트 청산 폴백 {}: {} — {}",
                    fallback.action, symbol, fallback.reason,
                )

        # ── 4) 활동 로그 ──
        provider_text = f"\nLLM: {llm_provider} ({llm_elapsed_ms}ms)" if llm_provider else "\n(코드 룰 폴백)"
        await activity_logger.log(
            ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
            f"📊 스마트 청산 AI 판정:\n" + "\n".join(log_lines) + provider_text,
        )

        return to_sell, to_hold

    async def _intraday_holdings_review(self) -> None:
        """장중 보유종목 AI 재평가 (30분 간격)

        LLM Tier1으로 보유 논거 유효성 + 손절/익절 임계값 적정성을 판단.
        SELL → 즉시 매도, HOLD + 임계값 조정 → event_detector 업데이트,
        ADD_BUY → trading_agent 파이프라인 연계.
        """
        import asyncio
        import time

        from services.ai_skip_metric_service import ai_skip_metric_service
        from services.activity_logger import activity_logger
        from services.holdings_precheck_service import holdings_precheck_service
        from services.holdings_review_cache_service import holdings_review_cache_service
        from util.time_util import now_kst
        from scheduler.market_calendar import market_calendar

        current_dt = now_kst()
        try:
            is_trading_hours = market_calendar.is_krx_trading_hours(current_dt)
        except TypeError:
            is_trading_hours = market_calendar.is_krx_trading_hours()
        if not is_trading_hours:
            return
        try:
            is_automated_session = market_calendar.is_automated_trading_session(current_dt)
        except TypeError:
            is_automated_session = market_calendar.is_automated_trading_session()
        if not is_automated_session:
            return

        try:
            from trading.account_manager import account_manager

            holdings = await account_manager.get_holdings()
            if not holdings:
                return

            sellable = [h for h in holdings if h.quantity > 0]
            if not sellable:
                return

            # ── 1) 데이터 수집 ──
            holdings_data, holdings_map, review_required = await self._collect_holdings_data(sellable)
            if review_required:
                review_lines = [
                    f"{getattr(item['holding'], 'name', item['holding'].symbol)}"
                    f"({item['holding'].symbol}): {item['reason']}"
                    for item in review_required
                ]
                await activity_logger.log(
                    ActivityType.SCHEDULE, ActivityPhase.PROGRESS,
                    "📊 장중 보유 재평가 데이터 확인 필요:\n" + "\n".join(review_lines),
                )

            if not holdings_data:
                return

            # 잔여 거래 시간 계산
            close_time = current_dt.replace(
                hour=settings.FORCE_LIQUIDATION_HOUR,
                minute=settings.FORCE_LIQUIDATION_MINUTE,
                second=0, microsecond=0,
            )
            minutes_left = max(0, int((close_time - current_dt).total_seconds() / 60))

            # ── 2) LLM Tier1 호출 ──
            llm_decisions = {}
            cached_decisions = {}
            prechecked_decisions = {}
            llm_provider = ""
            llm_elapsed_ms = 0

            try:
                from analysis.llm.llm_factory import llm_factory
                from analysis.llm.prompts.holdings_review import (
                    HOLDINGS_REVIEW_SYSTEM,
                    build_holdings_review_prompt,
                )
                from core.json_utils import parse_llm_json

                from agent.trading_agent import trading_agent
                market_regime = trading_agent._market_regime or ""
                market_context = trading_agent._market_context or ""

                llm_candidates = []
                for data in holdings_data:
                    symbol = data["symbol"]
                    h, trade_result, current_price = holdings_map[symbol]
                    precheck = holdings_precheck_service.evaluate(
                        holding=h,
                        trade_result=trade_result,
                        current_price=current_price,
                        settings=settings,
                    )
                    if precheck.should_skip_llm:
                        prechecked_decisions[symbol] = {
                            "action": precheck.action,
                            "reason": precheck.reason,
                            "confidence": 0.0,
                            "adjusted_stop_loss_price": None,
                            "adjusted_take_profit_price": None,
                        }
                        await ai_skip_metric_service.record(
                            stage="HOLDINGS_PRECHECK",
                            reason_code=precheck.action,
                            skipped_tier="TIER1",
                            symbol=symbol,
                            detail={
                                "source": precheck.source,
                                "reason": precheck.reason,
                            },
                        )
                    else:
                        cache_key = holdings_review_cache_service.build_key(
                            holding_data=data,
                            market_regime=market_regime,
                            market_context=market_context,
                            minutes_left=minutes_left,
                        )
                        cached = holdings_review_cache_service.get(cache_key)
                        if cached:
                            cached_decisions[symbol] = dict(cached)
                            await ai_skip_metric_service.record(
                                stage="HOLDINGS_REVIEW_CACHE",
                                reason_code="CACHE_HIT",
                                skipped_tier="TIER1",
                                symbol=symbol,
                                detail={
                                    "action": cached.get("action"),
                                    "confidence": cached.get("confidence") or 0,
                                },
                            )
                        else:
                            llm_candidates.append(data)

                if llm_candidates:
                    prompt = build_holdings_review_prompt(
                        llm_candidates, market_regime, market_context, minutes_left,
                    )

                    start = time.time()
                    result_text, llm_provider = await llm_factory.generate_tier1(
                        prompt, system_prompt=HOLDINGS_REVIEW_SYSTEM,
                    )
                    llm_elapsed_ms = int((time.time() - start) * 1000)

                    parsed = parse_llm_json(result_text)
                    if parsed and "decisions" in parsed:
                        for d in parsed["decisions"]:
                            symbol = d.get("symbol", "")
                            if symbol and symbol in holdings_map:
                                llm_decisions[symbol] = {
                                    "action": d.get("action", "HOLD").upper(),
                                    "reason": d.get("reason", ""),
                                    "confidence": d.get("confidence", 0.0),
                                    "partial_exit_pct": d.get("partial_exit_pct"),
                                    "adjusted_stop_loss_price": d.get("adjusted_stop_loss_price"),
                                    "adjusted_take_profit_price": d.get("adjusted_take_profit_price"),
                                    "trailing_stop_pct": d.get("trailing_stop_pct"),
                                }
                                cache_key = holdings_review_cache_service.build_key(
                                    holding_data=next(item for item in holdings_data if item["symbol"] == symbol),
                                    market_regime=market_regime,
                                    market_context=market_context,
                                    minutes_left=minutes_left,
                                )
                                holdings_review_cache_service.put(cache_key, llm_decisions[symbol])

                logger.info(
                    "장중 보유 재평가 완료: LLM {}건 / 캐시 {}건 / 정책 사전판단 {}건 / {} ({}ms)",
                    len(llm_decisions), len(cached_decisions), len(prechecked_decisions), llm_provider, llm_elapsed_ms,
                )
            except Exception as e:
                logger.warning("장중 보유 재평가 LLM 실패 → 폴백: {}", str(e))

            # ── 3) 판정 결과 처리 ──
            from agent.decision_maker import decision_maker
            from agent.trading_agent import trading_agent
            from realtime.event_detector import event_detector
            from strategy.holding_policy import evaluate_overnight_hold

            log_lines = []

            for data in holdings_data:
                symbol = data["symbol"]
                h, trade_result, current_price = holdings_map[symbol]
                stock_name = data["stock_name"]

                if symbol in prechecked_decisions:
                    decision = prechecked_decisions[symbol]
                    action = decision["action"]
                    reason = decision["reason"]
                    conf = decision["confidence"]
                    await self._record_holdings_review_decision_event(
                        data=data,
                        holding=h,
                        trade_result=trade_result,
                        current_price=current_price,
                        decision=decision,
                        source="holdings_precheck",
                        reason_code=f"PRECHECK_{action}",
                    )
                elif symbol in cached_decisions:
                    decision = cached_decisions[symbol]
                    action = decision["action"]
                    reason = f"{decision['reason']} (캐시)"
                    conf = decision["confidence"]
                    await self._record_holdings_review_decision_event(
                        data=data,
                        holding=h,
                        trade_result=trade_result,
                        current_price=current_price,
                        decision=decision,
                        source="holdings_review_cache",
                        reason_code="CACHE_HIT",
                    )
                elif symbol in llm_decisions:
                    decision = llm_decisions[symbol]
                    action = decision["action"]
                    reason = decision["reason"]
                    conf = decision["confidence"]
                else:
                    # LLM 누락/실패 → 코드 룰 폴백
                    fallback = evaluate_overnight_hold(h, trade_result, current_price, settings)
                    action = fallback.action
                    reason = f"{fallback.reason} (폴백)"
                    conf = 0.0
                    decision = {}

                if action in {"SELL", "PARTIAL_SELL"} and settings.TRADING_ENABLED:
                    # 즉시 시장가 매도
                    if not await trading_agent._acquire_sell(symbol):
                        log_lines.append(f"  - {stock_name}({symbol}): {action} → 이미 매도 진행 중")
                        continue
                    try:
                        sell_quantity = int(h.quantity)
                        exit_reason = "HOLDINGS_REVIEW"
                        if action == "PARTIAL_SELL":
                            partial_pct = self._coerce_partial_exit_pct(decision.get("partial_exit_pct"))
                            sell_quantity = max(1, min(int(h.quantity), int(int(h.quantity) * partial_pct / 100)))
                            exit_reason = "PARTIAL_TAKE_PROFIT"
                        sell_resp = await self._place_market_sell(symbol, sell_quantity)
                        if sell_resp.success:
                            confirmed = await decision_maker.confirm_and_record(
                                symbol=symbol, side="SELL",
                                order_id=str(getattr(sell_resp, "order_id", "") or ""), quantity=sell_quantity,
                                expected_price=current_price,
                                exit_reason=exit_reason,
                            )
                            confirmed = True if confirmed is None else bool(confirmed)
                            if confirmed:
                                if action == "SELL" or sell_quantity >= int(h.quantity):
                                    event_detector.remove_levels(symbol)
                                # UI에 개별 매도 표시
                                await activity_logger.log(
                                    ActivityType.ORDER, ActivityPhase.COMPLETE,
                                    f"🔄 장중 재평가 매도: {stock_name}({symbol}) {sell_quantity}주 — {reason}",
                                    symbol=symbol,
                                )
                                log_lines.append(
                                    f"  - {stock_name}({symbol}): {action} 매도 성공 ({sell_quantity}주) — {reason} "
                                    f"(AI {conf:.2f})"
                                )
                                # 매도 성공 → 재스캔 트리거
                                asyncio.create_task(self._trigger_rescan_after_sell())
                            else:
                                await activity_logger.log(
                                    ActivityType.ORDER, ActivityPhase.ERROR,
                                    f"⚠️ 장중 재평가 매도 체결 확인 실패: {stock_name}({symbol}) "
                                    f"{sell_quantity}주 — {reason}",
                                    symbol=symbol,
                                )
                                log_lines.append(
                                    f"  - {stock_name}({symbol}): {action} 매도 체결 확인 실패/취소 "
                                    f"({sell_quantity}주) — {reason} (AI {conf:.2f})"
                                )
                        else:
                            log_lines.append(
                                f"  - {stock_name}({symbol}): {action} 매도 실패 — "
                                f"{sell_resp.error or ''}"
                            )
                    except Exception as e:
                        log_lines.append(
                            f"  - {stock_name}({symbol}): {action} 매도 오류 — {str(e)[:50]}"
                        )
                    finally:
                        trading_agent._release_sell(symbol)

                elif action in {"HOLD", "TIGHTEN_STOP"}:
                    # 임계값 동적 조정
                    kwargs = {}
                    adj_sl = decision.get("adjusted_stop_loss_price")
                    adj_tp = decision.get("adjusted_take_profit_price")
                    trailing = decision.get("trailing_stop_pct")
                    if adj_sl is not None and isinstance(adj_sl, (int, float)) and float(adj_sl) > 0:
                        kwargs["stop_loss"] = float(adj_sl)
                    if adj_tp is not None and isinstance(adj_tp, (int, float)) and float(adj_tp) > 0:
                        kwargs["take_profit"] = float(adj_tp)
                    if trailing is not None and isinstance(trailing, (int, float)) and float(trailing) > 0:
                        kwargs["trailing_stop_pct"] = float(trailing)

                    if kwargs:
                        event_detector.set_thresholds(symbol, **kwargs)
                        # TradeResult에도 반영
                        try:
                            from core.database import AsyncSessionLocal
                            from repositories.trade_result_repository import TradeResultRepository
                            async with AsyncSessionLocal() as session:
                                repo = TradeResultRepository(session)
                                tr = await repo.get_open_buy(symbol)
                                if tr:
                                    if "stop_loss" in kwargs:
                                        tr.ai_stop_loss_price = kwargs["stop_loss"]
                                    if "take_profit" in kwargs:
                                        tr.ai_target_price = kwargs["take_profit"]
                                    await session.flush()
                                    await session.commit()
                        except Exception as e:
                            logger.warning("임계값 DB 반영 오류 {}: {}", symbol, str(e))

                        adj_text = ", ".join(f"{k}={v:,.0f}" for k, v in kwargs.items())
                        log_lines.append(
                            f"  - {stock_name}({symbol}): {action} + 임계값 조정 [{adj_text}] — "
                            f"{reason} (AI {conf:.2f})"
                        )
                    else:
                        log_lines.append(
                            f"  - {stock_name}({symbol}): {action} — {reason} (AI {conf:.2f})"
                        )

                elif action == "ADD_BUY":
                    # trading_agent 파이프라인으로 연계 (Tier1→Tier2 검증)
                    strategy_type = data.get("strategy_type", "STABLE_SHORT")
                    if strategy_type == "N/A":
                        strategy_type = "STABLE_SHORT"
                    asyncio.create_task(
                        trading_agent._analyze_and_trade(
                            symbol=symbol, name=stock_name,
                            strategy_type=strategy_type,
                        )
                    )
                    log_lines.append(
                        f"  - {stock_name}({symbol}): ADD_BUY → 분석 파이프라인 진행 — "
                        f"{reason} (AI {conf:.2f})"
                    )

                elif action in {"SELL", "PARTIAL_SELL"} and not settings.TRADING_ENABLED:
                    log_lines.append(
                        f"  - {stock_name}({symbol}): {action} → TRADING_ENABLED=false — "
                        f"{reason} (AI {conf:.2f})"
                    )

            # ── 4) 활동 로그 ──
            if log_lines:
                if llm_provider:
                    provider_text = f"\nLLM: {llm_provider} ({llm_elapsed_ms}ms)"
                elif cached_decisions:
                    provider_text = "\n(보유 재평가 캐시 재사용)"
                else:
                    provider_text = "\n(코드 룰 폴백)"
                await activity_logger.log(
                    ActivityType.HOLDINGS_CHECK, ActivityPhase.PROGRESS,
                    f"🔄 장중 보유 재평가 (잔여 {minutes_left}분):\n"
                    + "\n".join(log_lines) + provider_text,
                )

        except Exception as e:
            logger.warning("장중 보유 재평가 오류: {}", str(e))
            await activity_logger.log(
                ActivityType.HOLDINGS_CHECK, ActivityPhase.ERROR,
                f"❌ 장중 보유 재평가 오류: {str(e)[:100]}",
            )

    @staticmethod
    def _coerce_partial_exit_pct(value) -> float:
        try:
            pct = float(value)
        except (TypeError, ValueError):
            pct = 50.0
        return max(10.0, min(90.0, pct))

    async def _check_overnight_positions(self) -> None:
        """오버나이트 포지션 프리마켓 점검 (08:50)

        서버 재시작 대비 event_detector 임계값 재설정 + 보유일 경고.
        """
        from services.activity_logger import activity_logger

        try:
            from core.database import AsyncSessionLocal
            from realtime.event_detector import event_detector
            from repositories.trade_result_repository import TradeResultRepository

            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                open_positions = await repo.get_all_open()

                if not open_positions:
                    return

                # 실제 KIS 보유종목과 교차 검증 → 고아 레코드 정리
                actual_symbols = set()
                try:
                    from trading.account_manager import account_manager
                    actual_holdings = await account_manager.get_holdings()
                    actual_symbols = {
                        normalize_krx_symbol(getattr(h, "symbol", ""))
                        for h in actual_holdings
                        if h.quantity > 0 and normalize_krx_symbol(getattr(h, "symbol", ""))
                    }
                except Exception:
                    actual_symbols = {
                        normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                        for tr in open_positions
                        if normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    }

                orphan_count = 0
                # 고아 레코드에 대해 실제 매도 가격 추정 시도
                # SELL 레코드나 현재가로 exit_price/pnl 계산
                for tr in open_positions:
                    symbol = normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    if symbol not in actual_symbols:
                        from util.time_util import now_kst
                        now = now_kst()
                        tr.exit_at = now
                        tr.exit_reason = "ORPHAN_CLEANUP"

                        # exit_price 추정: 현재가 또는 마지막 SELL 레코드
                        exit_price = 0.0
                        try:
                            exit_price = await self._fetch_current_price(symbol)
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

                if orphan_count:
                    await session.commit()
                    logger.warning("프리마켓 고아 TradeResult {}건 정리 (손익 계산 포함)", orphan_count)
                    # 고아 제거 후 다시 조회
                    open_positions = [tr for tr in open_positions if tr.exit_at is None]

            if not open_positions:
                return

            restored = 0
            warnings = []
            for tr in open_positions:
                symbol = normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                # event_detector 임계값 재설정
                kwargs = {}
                if tr.ai_stop_loss_price and tr.ai_stop_loss_price > 0:
                    kwargs["stop_loss"] = tr.ai_stop_loss_price
                if tr.ai_target_price and tr.ai_target_price > 0:
                    kwargs["take_profit"] = tr.ai_target_price
                if kwargs:
                    event_detector.set_thresholds(symbol or tr.stock_symbol, **kwargs)
                    restored += 1

                # 최대 보유일 경고
                from strategy.holding_policy import _calc_hold_days, _get_max_hold_days_for_trade
                hold_days = _calc_hold_days(tr)
                max_days = _get_max_hold_days_for_trade(tr, settings)
                if hold_days >= max_days:
                    warnings.append(
                        f"{tr.stock_name}({symbol or tr.stock_symbol}): 보유 {hold_days}일 ≥ 최대 {max_days}일"
                    )

            msg = f"\U0001f30d 오버나이트 포지션 {len(open_positions)}건 점검"
            if restored:
                msg += f" | 임계값 복원 {restored}건"
            if warnings:
                msg += f" | ⚠️ 초과보유: {', '.join(warnings)}"

            logger.info(msg)
            await activity_logger.log(
                ActivityType.SCHEDULE, ActivityPhase.PROGRESS, msg,
            )
        except Exception as e:
            logger.warning("오버나이트 포지션 점검 오류: {}", str(e))

    async def _check_overnight_gap(self) -> None:
        """장 시작 갭 체크 (09:05) — 오버나이트 포지션 손절/익절 즉시 처리"""
        from services.activity_logger import activity_logger
        from util.time_util import now_kst

        try:
            from core.database import AsyncSessionLocal
            from repositories.trade_result_repository import TradeResultRepository
            from trading.account_manager import account_manager

            holdings = await account_manager.get_holdings()
            if not holdings:
                return

            current_dt = now_kst()
            opening_gap_window = current_dt.hour == 9 and current_dt.minute <= 20
            if not opening_gap_window:
                logger.debug(
                    "오버나이트 갭 체크 스킵: 장 시작 확인 윈도우 아님 ({})",
                    current_dt.strftime("%H:%M"),
                )
                return

            async with AsyncSessionLocal() as session:
                repo = TradeResultRepository(session)
                open_positions = await repo.get_all_open()

            # symbol → TradeResult 매핑
            open_map = {
                normalize_krx_symbol(getattr(tr, "stock_symbol", "")): tr
                for tr in open_positions
                if normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
            }

            alerts = []
            close_time = current_dt.replace(
                hour=settings.FORCE_LIQUIDATION_HOUR,
                minute=settings.FORCE_LIQUIDATION_MINUTE,
                second=0, microsecond=0,
            )
            minutes_left = max(0, int((close_time - current_dt).total_seconds() / 60))
            for h in holdings:
                if h.quantity <= 0:
                    continue
                symbol = normalize_krx_symbol(getattr(h, "symbol", ""))
                tr = open_map.get(symbol)
                if not tr:
                    continue  # 당일 매수 등 — 갭 체크 불필요

                current = await self._fetch_current_price(symbol)
                if current <= 0:
                    continue

                should_sell = False
                reason = ""

                # 갭 하락 → 손절가 이하
                if tr.ai_stop_loss_price and current <= tr.ai_stop_loss_price:
                    reason = f"갭 하락 손절 (현재 {current:,.0f} ≤ 손절 {tr.ai_stop_loss_price:,.0f})"
                    stop_loss_pct = -3.0
                    pnl_rate = 0.0
                    avg_buy_price = float(getattr(h, "avg_buy_price", 0.0) or 0.0)
                    if avg_buy_price > 0:
                        pnl_rate = (current - avg_buy_price) / avg_buy_price * 100
                        stop_loss_pct = ((tr.ai_stop_loss_price - avg_buy_price) / avg_buy_price) * 100
                    if avg_buy_price > 0 and not opening_gap_window:
                        defer_sell, defer_reason = self._should_defer_soft_stop(
                            symbol,
                            pnl_rate=pnl_rate,
                            stop_loss_pct=stop_loss_pct,
                            minutes_left=minutes_left,
                            observed_at=current_dt.timestamp(),
                            scope="gap_check",
                        )
                        if defer_sell:
                            alerts.append(
                                f"👀 {h.name}({symbol}): {reason} — 완충 확인 중 "
                                f"(얕은 이탈, 다음 점검까지 보류)"
                            )
                            continue
                        if defer_reason == "confirmed":
                            reason += " — 2회 연속 확인"
                        elif defer_reason == "hard_breach":
                            reason += " — 손절선 깊게 이탈"
                        elif defer_reason == "near_close":
                            reason += " — 장마감 임박"
                    should_sell = True

                # 갭 상승 → 익절가 이상
                elif tr.ai_target_price and current >= tr.ai_target_price:
                    should_sell = True
                    reason = f"갭 상승 익절 (현재 {current:,.0f} ≥ 목표 {tr.ai_target_price:,.0f})"

                if should_sell and settings.TRADING_ENABLED:
                    # P0-2: 이중 매도 방지
                    from agent.trading_agent import trading_agent
                    if not await trading_agent._acquire_sell(symbol):
                        alerts.append(f"\u26a0\ufe0f {h.name}({symbol}): {reason} → 이미 매도 진행 중")
                        continue
                    try:
                        sell_resp = await self._place_market_sell(symbol, h.quantity)
                        if sell_resp.success:
                            alerts.append(f"\U0001f6a8 {h.name}({symbol}): {reason} → 매도 주문 접수")
                            confirmed = await self._track_scheduler_sell_confirmation(
                                holding=h,
                                response=sell_resp,
                                symbol=symbol,
                                quantity=int(h.quantity),
                                expected_price=current,
                                exit_reason="GAP_CHECK",
                            )
                            if confirmed:
                                alerts.append(f"✅ {h.name}({symbol}): {reason} → 매도 체결 확인 완료")
                                from realtime.event_detector import event_detector
                                event_detector.remove_levels(symbol)
                                await activity_logger.log(
                                    ActivityType.ORDER,
                                    ActivityPhase.COMPLETE,
                                    (
                                        f"📉 [{h.name}] 갭 체크 매도 완료: "
                                        f"{reason} — {int(h.quantity)}주 체결"
                                    ),
                                    symbol=symbol,
                                    detail={
                                        "action": "SELL",
                                        "source": "GAP_CHECK",
                                        "reason": reason,
                                        "quantity": int(h.quantity),
                                        "price": current,
                                        "order_id": getattr(sell_resp, "order_id", None),
                                    },
                                )
                            else:
                                alerts.append(f"⚠️ {h.name}({symbol}): {reason} → 매도 체결 확인 실패/취소")
                                await activity_logger.log(
                                    ActivityType.ORDER,
                                    ActivityPhase.ERROR,
                                    (
                                        f"⚠️ [{h.name}] 갭 체크 매도 체결 확인 실패: "
                                        f"{reason} — {int(h.quantity)}주"
                                    ),
                                    symbol=symbol,
                                    detail={
                                        "action": "SELL_CONFIRM_FAILED",
                                        "source": "GAP_CHECK",
                                        "reason": reason,
                                        "quantity": int(h.quantity),
                                        "price": current,
                                        "order_id": getattr(sell_resp, "order_id", None),
                                    },
                                )
                        else:
                            alerts.append(f"\U0001f6a8 {h.name}({symbol}): {reason} → 매도 실패: {sell_resp.error or ''}")
                            await activity_logger.log(
                                ActivityType.ORDER,
                                ActivityPhase.ERROR,
                                f"❌ [{h.name}] 갭 체크 매도 실패: {reason} — {sell_resp.error or '오류 없음'}",
                                symbol=symbol,
                                detail={
                                    "action": "SELL",
                                    "source": "GAP_CHECK",
                                    "reason": reason,
                                    "quantity": int(h.quantity),
                                    "price": current,
                                    "error": sell_resp.error,
                                },
                            )
                    finally:
                        trading_agent._release_sell(h.symbol)
                elif should_sell:
                    alerts.append(f"\u26a0\ufe0f {h.name}({h.symbol}): {reason} (TRADING_ENABLED=false)")

            if alerts:
                msg = "\U0001f30d 오버나이트 갭 체크:\n" + "\n".join(alerts)
                logger.info(msg)
                await activity_logger.log(
                    ActivityType.SCHEDULE, ActivityPhase.PROGRESS, msg,
                )
        except Exception as e:
            logger.warning("오버나이트 갭 체크 오류: {}", str(e))

    async def _trigger_rescan_after_sell(self) -> None:
        """매도 완료 후 재스캔 (현금 충분 + 장중 + 매수 마감 전)"""
        import asyncio
        from datetime import time as _time

        await asyncio.sleep(5)  # 체결 확인 대기

        try:
            if not settings.TRADING_ENABLED:
                return

            from scheduler.market_calendar import market_calendar
            if not market_calendar.is_krx_trading_hours():
                return

            # 매수 마감 시간 체크
            from util.time_util import now_kst
            cutoff = _time(settings.BUY_CUTOFF_HOUR, settings.BUY_CUTOFF_MINUTE)
            if now_kst().time() >= cutoff:
                logger.debug("매수 마감 시간 경과 → 재스캔 스킵")
                return

            from trading.account_manager import account_manager
            balance = await account_manager.get_balance()
            min_order_amount = settings.MIN_BUY_QUANTITY * 1000  # 대략적 최소 주문 금액
            if balance.cash < min_order_amount:
                logger.debug("현금 부족 ({:,.0f}원) → 재스캔 스킵", balance.cash)
                return

            logger.debug("매도 후 재스캔 트리거 — 현금 {:,.0f}원", balance.cash)
            from agent.trading_agent import trading_agent
            await trading_agent.run_cycle()
        except Exception as e:
            logger.warning("매도 후 재스캔 실패: {}", str(e))

    async def _expire_recommendations(self) -> None:
        """만료된 추천 처리"""
        logger.debug("만료 추천 처리 실행")

    @property
    def is_running(self) -> bool:
        return self._running


trading_scheduler = TradingScheduler()
