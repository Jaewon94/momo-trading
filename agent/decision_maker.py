"""매매 결정 + 자율/반자율 모드 분기 + 체결 확인/기록"""
import asyncio
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from loguru import logger

from core.config import settings
from core.database import AsyncSessionLocal
from core.events import Event, EventType, event_bus
from core.order_submission import decide_order_submission
from models.order import Order
from models.recommendation import Recommendation
from models.trade_result import TradeResult
from repositories.trade_result_repository import TradeResultRepository
from services.activity_logger import activity_logger
from services.decision_event_service import decision_event_service
from strategy.signal import TradeSignal
from trading.adapters.base import BrokerAdapter
from trading.broker_factory import get_broker_adapter
from trading.enums import (
    ActivityPhase,
    ActivityType,
    AutonomyMode,
    Market,
    OrderConfirmStatus,
    OrderSide,
    OrderSource,
    OrderType,
    RecommendationStatus,
)
from trading.models import OrderRequest, PendingOrderInfo
from trading.symbols import normalize_krx_symbol
from util.time_util import now_kst


class DecisionMaker:
    """
    자율/반자율 모드에 따라 실행 방식을 분기.

    AUTONOMOUS: 스캔 → 분석 → 매매까지 전자동
    SEMI_AUTO: 스캔 → 분석 → 추천 생성 → 사용자 승인 대기
    """

    def __init__(self, broker_adapter: BrokerAdapter | None = None):
        self._pending_tasks: set[asyncio.Task] = set()
        self._broker_adapter = broker_adapter or get_broker_adapter()

    async def execute(
        self, signal: TradeSignal, analysis_id: str = "", cycle_id: str | None = None,
        analysis_context: dict | None = None,
        on_settled: "Callable[[str, bool], Any] | None" = None,
    ) -> dict:
        """시그널에 따라 실행"""
        mode = AutonomyMode(settings.AUTONOMY_MODE)

        if mode == AutonomyMode.AUTONOMOUS:
            return await self._execute_autonomous(signal, cycle_id, analysis_context, on_settled=on_settled)
        else:
            return await self._create_recommendation(signal, analysis_id, cycle_id)

    async def _execute_autonomous(
        self, signal: TradeSignal, cycle_id: str | None = None,
        analysis_context: dict | None = None,
        on_settled: Callable[[str, bool], Any] | None = None,
    ) -> dict:
        """완전자율: MCP로 즉시 주문 실행"""
        logger.info(
            "[AUTONOMOUS] 주문 실행: {} {} x{} {}",
            signal.symbol, signal.action.value,
            signal.suggested_quantity,
            f"@{signal.suggested_price}" if signal.suggested_price else "시장가",
        )

        qty = signal.suggested_quantity or 0
        price = signal.suggested_price or 0
        amount = price * qty
        price_display = f"@{price:,.0f}원" if price else "시장가"
        await activity_logger.log(
            ActivityType.DECISION, ActivityPhase.START,
            f"\U0001f4b0 [{signal.symbol}] 자동 주문 실행: "
            f"{signal.action.value} {qty}주 "
            f"{price_display}" + (f" ({amount:,.0f}원)" if amount else ""),
            cycle_id=cycle_id,
            symbol=signal.symbol,
        )

        if qty <= 0:
            error_msg = "주문 수량이 유효하지 않습니다"
            await activity_logger.log(
                ActivityType.DECISION, ActivityPhase.ERROR,
                f"\u274c [{signal.symbol}] 주문 실패: {error_msg}",
                cycle_id=cycle_id, symbol=signal.symbol,
                error_message=error_msg,
            )
            result = {
                "mode": "AUTONOMOUS",
                "symbol": signal.symbol,
                "action": signal.action.value,
                "success": False,
                "order_id": "",
                "message": error_msg,
                "data": None,
            }
            await event_bus.publish(Event(
                type=EventType.ORDER_EXECUTED,
                data=result,
                source="decision_maker",
            ))
            await self._record_decision_event(
                signal,
                cycle_id=cycle_id,
                decision_stage="ORDER_VALIDATION",
                risk_gate_result="BLOCKED",
                final_action="SKIP",
                status="SKIPPED",
                reason=error_msg,
                result=result,
                analysis_context=analysis_context,
            )
            return result

        submission_decision = decide_order_submission(signal.action.value)
        if not submission_decision.allowed:
            skip_msg = f"주문 제출 차단: {submission_decision.reason}"
            result = {
                "mode": "AUTONOMOUS",
                "symbol": signal.symbol,
                "action": signal.action.value,
                "success": False,
                "order_id": "",
                "message": skip_msg,
                "data": submission_decision.as_detail(),
            }
            await activity_logger.log(
                ActivityType.DECISION, ActivityPhase.SKIP,
                f"\u23f8\ufe0f [{signal.symbol}] {skip_msg}",
                cycle_id=cycle_id, symbol=signal.symbol,
                detail=result,
            )
            await event_bus.publish(Event(
                type=EventType.ORDER_EXECUTED,
                data=result,
                source="decision_maker",
            ))
            await self._record_decision_event(
                signal,
                cycle_id=cycle_id,
                decision_stage="ORDER_GATE",
                risk_gate_result="BLOCKED",
                final_action="SKIP",
                status="SKIPPED",
                reason=skip_msg,
                result=result,
                analysis_context=analysis_context,
            )
            return result

        if signal.action.value == OrderSide.BUY.value:
            existing_pending_buy = await self._find_existing_pending_buy(signal.symbol)
            if existing_pending_buy is not None:
                skip_msg = (
                    "기존 미체결 매수 주문 존재 → 신규 주문 차단 "
                    f"(주문번호: {existing_pending_buy.order_id}, 잔량 {existing_pending_buy.remaining_qty}주)"
                )
                result = {
                    "mode": "AUTONOMOUS",
                    "symbol": signal.symbol,
                    "action": signal.action.value,
                    "success": False,
                    "order_id": "",
                    "message": skip_msg,
                    "data": {
                        "pending_order_id": existing_pending_buy.order_id,
                        "pending_remaining_qty": existing_pending_buy.remaining_qty,
                        "pending_order_price": existing_pending_buy.order_price,
                    },
                }
                await activity_logger.log(
                    ActivityType.DECISION, ActivityPhase.SKIP,
                    f"\u23f8\ufe0f [{signal.symbol}] {skip_msg}",
                    cycle_id=cycle_id, symbol=signal.symbol,
                    detail=result,
                )
                await event_bus.publish(Event(
                    type=EventType.ORDER_EXECUTED,
                    data=result,
                    source="decision_maker",
                ))
                await self._record_decision_event(
                    signal,
                    cycle_id=cycle_id,
                    decision_stage="ORDER_GATE",
                    risk_gate_result="BLOCKED",
                    final_action="SKIP",
                    status="SKIPPED",
                    reason=skip_msg,
                    result=result,
                    analysis_context=analysis_context,
                )
                return result

        order_result = await self._broker_adapter.place_order(self._build_order_request(signal))

        order_id = order_result.order_id or ""
        is_submitted = order_result.success and bool(order_id)
        order_data = order_result.model_dump(mode="json")

        result = {
            "mode": "AUTONOMOUS",
            "symbol": signal.symbol,
            "action": signal.action.value,
            "success": is_submitted,
            "order_id": order_id,
            "message": "주문 접수" if is_submitted else (order_result.message or "주문 응답 없음"),
            "data": order_data,
        }

        if is_submitted:
            await activity_logger.log(
                ActivityType.DECISION, ActivityPhase.COMPLETE,
                f"\u2705 [{signal.symbol}] 주문 접수 완료 (체결 대기) — 주문번호: {order_id}",
                cycle_id=cycle_id, symbol=signal.symbol,
                detail=result,
            )
            # PENDING_CONFIRM 레코드 즉시 생성 (체결 확인 실패해도 DB에 기록 남음)
            pending_record_id = await self._create_pending_record(
                symbol=signal.symbol,
                side=signal.action.value,
                order_id=order_id,
                quantity=qty,
                expected_price=price,
                analysis_context=analysis_context,
            )
            # 체결 확인 + TradeResult 업데이트 (백그라운드, 매매 흐름 차단 안 함)
            task = asyncio.create_task(
                self.confirm_and_record(
                    symbol=signal.symbol,
                    side=signal.action.value,
                    order_id=order_id,
                    quantity=qty,
                    expected_price=price,
                    analysis_context=analysis_context,
                    cycle_id=cycle_id,
                    pending_record_id=pending_record_id,
                    on_settled=on_settled,
                )
            )
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        else:
            error_msg = order_result.message or "주문번호 없음"
            # 매매불가 종목 → 런타임 블록리스트 등록 (이후 스캔에서 제외)
            if "매매불가" in error_msg:
                from agent.market_scanner import market_scanner
                market_scanner.add_untradeable(signal.symbol)
                logger.warning("매매불가 종목 블록리스트 등록: {} → 이후 스캔에서 제외", signal.symbol)
            await activity_logger.log(
                ActivityType.DECISION, ActivityPhase.ERROR,
                f"\u274c [{signal.symbol}] 주문 실패: {error_msg}",
                cycle_id=cycle_id, symbol=signal.symbol,
                error_message=error_msg,
            )

        await event_bus.publish(Event(
            type=EventType.ORDER_EXECUTED,
            data=result,
            source="decision_maker",
        ))
        await self._record_decision_event(
            signal,
            cycle_id=cycle_id,
            decision_stage="ORDER_SUBMISSION",
            risk_gate_result="PASS" if is_submitted else "ORDER_REJECTED",
            final_action=signal.action.value if is_submitted else "SKIP",
            status="ORDER_SUBMITTED" if is_submitted else "ORDER_REJECTED",
            reason=result["message"],
            result=result,
            analysis_context=analysis_context,
        )

        return result

    async def _record_decision_event(
        self,
        signal: TradeSignal,
        *,
        cycle_id: str | None,
        decision_stage: str,
        risk_gate_result: str,
        final_action: str,
        status: str,
        reason: str,
        result: dict | None = None,
        analysis_context: dict | None = None,
    ) -> None:
        context = {**(analysis_context or {}), **(signal.metadata or {})}
        result_data = (result or {}).get("data") or {}
        if not isinstance(result_data, dict):
            result_data = {}
        metadata = {
            "signal_strength": signal.strength,
            "urgency": getattr(signal.urgency, "value", str(signal.urgency)),
            "order_result": result,
            "analysis_context": analysis_context or {},
            "signal_metadata": signal.metadata or {},
        }
        try:
            await decision_event_service.record_event(
                cycle_id=cycle_id,
                symbol=signal.symbol,
                stock_name=str(context.get("stock_name") or context.get("name") or signal.symbol),
                market=str(context.get("market") or "KRX"),
                decision_stage=decision_stage,
                source="decision_maker",
                strategy_type=signal.strategy_type or context.get("strategy_type"),
                scanner_score=context.get("scanner_score"),
                tier1_decision=context.get("tier1_decision") or context.get("recommendation") or signal.action.value,
                tier2_decision=context.get("tier2_decision"),
                risk_gate_result=risk_gate_result,
                final_action=final_action,
                confidence=signal.confidence,
                reference_price=signal.suggested_price,
                quantity=signal.suggested_quantity,
                provider=context.get("provider") or context.get("llm_provider") or result_data.get("provider"),
                model=context.get("model") or context.get("llm_model") or result_data.get("model"),
                elapsed_ms=context.get("elapsed_ms") or context.get("llm_elapsed_ms"),
                status=status,
                reason=reason,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("decision event 기록 실패 ({}): {}", signal.symbol, str(exc))

    async def _find_existing_pending_buy(self, symbol: str) -> PendingOrderInfo | None:
        normalized_symbol = normalize_krx_symbol(symbol)
        try:
            pending_orders = await self._broker_adapter.get_pending_orders()
        except Exception as e:
            logger.warning("[{}] 미체결 주문 조회 실패 — 중복 매수 차단 검사 생략: {}", normalized_symbol, str(e))
            return None

        for order in pending_orders:
            if normalize_krx_symbol(order.symbol) != normalized_symbol:
                continue
            side_text = str(order.side or "").upper()
            if "매수" not in str(order.side or "") and side_text != OrderSide.BUY.value:
                continue
            if int(order.remaining_qty or 0) <= 0:
                continue
            return order
        return None

    @staticmethod
    def _build_order_request(signal: TradeSignal) -> OrderRequest:
        market_code = str(signal.metadata.get("market", Market.KRX.value)).upper()
        try:
            market = Market(market_code)
        except ValueError:
            market = Market.KRX

        return OrderRequest(
            symbol=signal.symbol,
            market=market,
            side=OrderSide(signal.action.value),
            order_type=OrderType.LIMIT if signal.suggested_price else OrderType.MARKET,
            quantity=signal.suggested_quantity or 0,
            price=signal.suggested_price,
        )

    @staticmethod
    def _build_trade_notes(analysis_context: dict | None, *, pending: bool = False) -> str | None:
        ctx = analysis_context or {}
        payload = {
            "trade_horizon": str(ctx.get("trade_horizon", "") or "").upper() or None,
            "estimated_edge_bps": ctx.get("estimated_edge_bps"),
            "estimated_cost_bps": ctx.get("estimated_cost_bps"),
            "edge_to_cost_ratio": ctx.get("edge_to_cost_ratio"),
            "cost_gate_ratio": ctx.get("cost_gate_ratio"),
            "news_negative_pressure": ctx.get("news_negative_pressure"),
            "news_negative_count": ctx.get("news_negative_count"),
            "news_source_count": ctx.get("news_source_count"),
            "news_threshold": ctx.get("news_threshold"),
            "news_top_contributors": ctx.get("news_top_contributors"),
            "chart_signal_direction": ctx.get("chart_signal_direction"),
            "chart_signal_confidence": ctx.get("chart_signal_confidence"),
            "entry_pattern": ctx.get("entry_pattern"),
        }
        payload = {k: v for k, v in payload.items() if v is not None and v != ""}
        if not payload:
            return "PENDING_CONFIRM: 체결 확인 대기 중" if pending else None
        if pending:
            payload["status"] = "PENDING_CONFIRM"
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _build_sell_fill_notes(
        *,
        partial_exit: bool,
        filled_quantity: int,
        requested_quantity: int,
        remaining_open_quantity: int,
        closed_lot_count: int,
    ) -> str | None:
        if not partial_exit:
            return None
        return json.dumps({
            "fill_type": "PARTIAL_EXIT",
            "filled_quantity": int(filled_quantity),
            "requested_quantity": int(requested_quantity),
            "remaining_open_quantity": int(remaining_open_quantity),
            "closed_lot_count": int(closed_lot_count),
        }, ensure_ascii=False)

    @staticmethod
    def _build_partial_close_clone(open_buy: TradeResult, *, close_qty: int, symbol: str) -> TradeResult:
        return TradeResult(
            order_id=None,
            stock_symbol=str(getattr(open_buy, "stock_symbol", "") or symbol),
            stock_name=str(getattr(open_buy, "stock_name", "") or symbol),
            side="BUY",
            strategy_type=str(getattr(open_buy, "strategy_type", "") or ""),
            entry_price=float(getattr(open_buy, "entry_price", 0.0) or 0.0),
            exit_price=0.0,
            quantity=int(close_qty),
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="",
            ai_recommendation=str(getattr(open_buy, "ai_recommendation", "") or ""),
            ai_confidence=float(getattr(open_buy, "ai_confidence", 0.0) or 0.0),
            ai_target_price=getattr(open_buy, "ai_target_price", None),
            ai_stop_loss_price=getattr(open_buy, "ai_stop_loss_price", None),
            entry_rsi=getattr(open_buy, "entry_rsi", None),
            entry_macd_hist=getattr(open_buy, "entry_macd_hist", None),
            entry_bb_position=getattr(open_buy, "entry_bb_position", None),
            entry_pattern=getattr(open_buy, "entry_pattern", None),
            market=str(getattr(open_buy, "market", "KRX") or "KRX"),
            market_regime=str(getattr(open_buy, "market_regime", "") or ""),
            notes=getattr(open_buy, "notes", None),
            status=str(getattr(open_buy, "status", OrderConfirmStatus.CONFIRMED.value) or OrderConfirmStatus.CONFIRMED.value),
            entry_at=getattr(open_buy, "entry_at", None),
        )

    @classmethod
    def _apply_sell_fill_to_open_buys(
        cls,
        session,
        open_buys: list[TradeResult],
        *,
        symbol: str,
        filled_qty: int,
        filled_price: float,
        exit_reason: str,
        closed_at,
    ) -> dict[str, int | float | bool]:
        remaining_to_close = max(int(filled_qty or 0), 0)
        closed_lot_count = 0
        total_pnl = 0.0
        total_return_pct = 0.0
        partial_exit = False

        for open_buy in open_buys:
            if remaining_to_close <= 0:
                break
            lot_qty = int(getattr(open_buy, "quantity", 0) or 0)
            if lot_qty <= 0:
                continue

            close_qty = min(lot_qty, remaining_to_close)
            target = open_buy
            if close_qty < lot_qty:
                partial_exit = True
                target = cls._build_partial_close_clone(open_buy, close_qty=close_qty, symbol=symbol)
                session.add(target)
                open_buy.quantity = lot_qty - close_qty

            entry_price = float(getattr(open_buy, "entry_price", 0.0) or 0.0)
            pnl = (filled_price - entry_price) * close_qty
            return_pct = ((filled_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

            target.exit_price = filled_price
            target.pnl = pnl
            target.return_pct = round(return_pct, 2)
            target.is_win = pnl > 0
            target.hold_days = (closed_at - open_buy.entry_at).days if getattr(open_buy, "entry_at", None) else 0
            target.exit_reason = exit_reason or "SIGNAL"
            target.exit_at = closed_at

            total_pnl += pnl
            total_return_pct += round(return_pct, 2)
            closed_lot_count += 1
            remaining_to_close -= close_qty

        applied_quantity = max(int(filled_qty or 0), 0) - max(remaining_to_close, 0)
        remaining_open_quantity = sum(
            int(getattr(open_buy, "quantity", 0) or 0)
            for open_buy in open_buys
            if getattr(open_buy, "exit_at", None) is None
        )
        return {
            "applied_quantity": applied_quantity,
            "closed_lot_count": closed_lot_count,
            "remaining_open_quantity": remaining_open_quantity,
            "total_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "partial_exit": partial_exit,
        }

    async def _create_pending_record(
        self,
        symbol: str,
        side: str,
        order_id: str,
        quantity: int,
        expected_price: float,
        analysis_context: dict | None = None,
    ) -> str | None:
        """PENDING_CONFIRM 상태의 TradeResult를 즉시 DB에 저장 (고아 주문 방지)"""
        ctx = analysis_context or {}
        now = now_kst()
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    repo = TradeResultRepository(session)
                    # 중복 체크 (P2-7)
                    existing = await repo.get_by_order_id(order_id)
                    if existing:
                        logger.warning("[{}] 주문번호 {} 이미 존재 → pending 생성 스킵", symbol, order_id)
                        return existing.id
                    tr = TradeResult(
                        order_id=order_id,
                        stock_symbol=symbol,
                        stock_name=ctx.get("stock_name", symbol),
                        side=side,
                        strategy_type=ctx.get("strategy_type", ""),
                        entry_price=expected_price if side == "BUY" else 0.0,
                        exit_price=expected_price if side == "SELL" else 0.0,
                        quantity=quantity,
                        status=OrderConfirmStatus.PENDING_CONFIRM.value,
                        ai_recommendation=ctx.get("ai_recommendation", ""),
                        ai_confidence=ctx.get("ai_confidence", 0.0),
                        ai_target_price=ctx.get("ai_target_price"),
                        ai_stop_loss_price=ctx.get("ai_stop_loss_price"),
                        entry_pattern=ctx.get("entry_pattern"),
                        market_regime=ctx.get("market_regime", ""),
                        entry_at=now if side == "BUY" else None,
                        exit_at=now if side == "SELL" else None,
                        notes=self._build_trade_notes(ctx, pending=True),
                    )
                    session.add(tr)
                    await session.flush()
                    logger.debug("[{}] PENDING_CONFIRM 레코드 생성: order_id={}", symbol, order_id)
                    return tr.id
        except Exception as e:
            logger.error("[{}] PENDING_CONFIRM 레코드 생성 실패: {}", symbol, str(e))
            return None

    async def confirm_and_record(
        self,
        symbol: str,
        side: str,
        order_id: str,
        quantity: int,
        expected_price: float,
        analysis_context: dict | None = None,
        cycle_id: str | None = None,
        exit_reason: str = "",
        pending_record_id: str | None = None,
        on_settled: Callable[[str, bool], Any] | None = None,
    ) -> None:
        """주문 접수 후 체결 확인 → TradeResult 기록

        pending_record_id가 있으면 기존 PENDING_CONFIRM 레코드를 UPDATE.
        없으면 기존 방식(새 레코드 생성)으로 폴백.
        3초 대기 → 브로커 어댑터로 체결 확인 → 체결 시 기록.
        on_settled: 체결 확인 완료 시 호출되는 콜백 (order_id, success)
        """
        try:
            await asyncio.sleep(3)  # KIS 체결 처리 대기

            order_status = await self._broker_adapter.get_order_status(order_id)
            if not order_status:
                logger.info("[{}] 주문 {} 미체결 (체결내역에서 미발견)", symbol, order_id)
                await self._cancel_unfilled_order(order_id, symbol)
                if on_settled:
                    await on_settled(order_id, False)
                return

            filled_qty = (
                quantity if order_status.filled_qty is None else order_status.filled_qty
            )
            filled_price = (
                order_status.filled_price
                if order_status.filled_price > 0
                else (order_status.order_price or expected_price)
            )

            if filled_qty <= 0:
                logger.debug("[{}] 주문 {} 체결수량 0 → 미체결 → 취소 시도", symbol, order_id)
                await self._cancel_unfilled_order(order_id, symbol)
                if on_settled:
                    await on_settled(order_id, False)
                return

            logger.info(
                "[체결확인] {} {} {}주 @{:,.0f}원 체결 완료 (주문번호: {})",
                symbol, side, filled_qty, filled_price, order_id,
            )

            # pending 레코드가 있으면 UPDATE, 없으면 CREATE
            if pending_record_id:
                await self._confirm_pending_record(
                    pending_record_id=pending_record_id,
                    symbol=symbol,
                    side=side,
                    filled_qty=filled_qty,
                    filled_price=filled_price,
                    analysis_context=analysis_context,
                    exit_reason=exit_reason,
                    cycle_id=cycle_id,
                )
            else:
                await self._record_trade_result(
                    symbol=symbol,
                    side=side,
                    order_id=order_id,
                    filled_qty=filled_qty,
                    filled_price=filled_price,
                    analysis_context=analysis_context,
                    exit_reason=exit_reason,
                    cycle_id=cycle_id,
                )

            self._broker_adapter.invalidate_cache()

            # 체결 성공 콜백 → 예약 금액 해제
            if on_settled:
                await on_settled(order_id, True)

        except Exception as e:
            logger.error("[{}] 체결 확인/기록 실패: {}", symbol, str(e))
            await self._mark_pending_failed(pending_record_id, str(e))
            # 체결 실패 콜백 → 예약 환불
            if on_settled:
                await on_settled(order_id, False)

    async def _cancel_unfilled_order(self, order_id: str, symbol: str) -> None:
        """미체결 주문 취소 시도"""
        if not order_id:
            return
        try:
            result = await self._broker_adapter.cancel_order(str(order_id))
            if result.success:
                logger.debug("[{}] 미체결 주문 취소 완료: {}", symbol, order_id)
            else:
                logger.warning("[{}] 미체결 주문 취소 실패: {} — {}", symbol, order_id, result.message)
        except Exception as e:
            logger.warning("[{}] 미체결 주문 취소 오류: {} — {}", symbol, order_id, str(e))

    async def _confirm_pending_record(
        self,
        pending_record_id: str,
        symbol: str,
        side: str,
        filled_qty: int,
        filled_price: float,
        analysis_context: dict | None = None,
        exit_reason: str = "",
        cycle_id: str | None = None,
    ) -> None:
        """PENDING_CONFIRM → CONFIRMED 업데이트"""
        now = now_kst()
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    repo = TradeResultRepository(session)
                    tr = await repo.filter_by_one(id=pending_record_id)
                    if not tr:
                        logger.warning("[{}] pending 레코드 {} 미발견 → 새 레코드 생성", symbol, pending_record_id)
                        await self._record_trade_result(
                            symbol=symbol, side=side, order_id="",
                            filled_qty=filled_qty, filled_price=filled_price,
                            analysis_context=analysis_context,
                            exit_reason=exit_reason, cycle_id=cycle_id,
                        )
                        return

                    # 체결 정보 업데이트
                    tr.status = OrderConfirmStatus.CONFIRMED.value
                    tr.quantity = filled_qty
                    if side == "BUY":
                        tr.entry_price = filled_price
                        tr.entry_at = tr.entry_at or now
                        tr.entry_pattern = tr.entry_pattern or (analysis_context or {}).get("entry_pattern")
                        tr.notes = self._build_trade_notes(analysis_context, pending=False)
                    elif side == "SELL":
                        tr.exit_price = filled_price
                        tr.exit_at = now
                        tr.exit_reason = exit_reason or "SIGNAL"
                        open_buys = await repo.get_all_open_buys(symbol)
                        sell_fill = self._apply_sell_fill_to_open_buys(
                            session,
                            open_buys,
                            symbol=symbol,
                            filled_qty=filled_qty,
                            filled_price=filled_price,
                            exit_reason=exit_reason,
                            closed_at=now,
                        )
                        applied_qty = int(sell_fill["applied_quantity"] or 0) or int(filled_qty or 0)
                        tr.quantity = applied_qty
                        tr.notes = self._build_sell_fill_notes(
                            partial_exit=bool(sell_fill["partial_exit"]),
                            filled_quantity=applied_qty,
                            requested_quantity=filled_qty,
                            remaining_open_quantity=int(sell_fill["remaining_open_quantity"] or 0),
                            closed_lot_count=int(sell_fill["closed_lot_count"] or 0),
                        )
                        if open_buys:
                            logger.debug(
                                "[{}] 미청산 BUY {}건 {} 청산 완료",
                                symbol,
                                int(sell_fill["closed_lot_count"] or 0),
                                "부분" if sell_fill["partial_exit"] else "전량",
                            )
                    logger.debug("[{}] PENDING → CONFIRMED: {}주 @{:,.0f}원", symbol, tr.quantity, filled_price)

                    await activity_logger.log(
                        ActivityType.TRADE_RESULT, ActivityPhase.COMPLETE,
                        f"\U0001f4dd [{symbol}] {side} 체결 확인: {filled_qty}주 @{filled_price:,.0f}원",
                        cycle_id=cycle_id, symbol=symbol,
                    )
        except Exception as e:
            logger.error("[{}] PENDING→CONFIRMED 업데이트 실패: {}", symbol, str(e))

    async def _mark_pending_failed(self, pending_record_id: str | None, reason: str) -> None:
        """PENDING_CONFIRM → CONFIRM_FAILED 마킹"""
        if not pending_record_id:
            return
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    repo = TradeResultRepository(session)
                    tr = await repo.filter_by_one(id=pending_record_id)
                    if tr and tr.status == OrderConfirmStatus.PENDING_CONFIRM.value:
                        tr.status = OrderConfirmStatus.CONFIRM_FAILED.value
                        tr.notes = f"CONFIRM_FAILED: {reason[:200]}"
                        logger.warning("[{}] PENDING → CONFIRM_FAILED: {}", tr.stock_symbol, reason[:100])
        except Exception as e:
            logger.error("PENDING→FAILED 마킹 실패: {}", str(e))

    async def _record_trade_result(
        self,
        symbol: str,
        side: str,
        order_id: str,
        filled_qty: int,
        filled_price: float,
        analysis_context: dict | None = None,
        exit_reason: str = "",
        cycle_id: str | None = None,
    ) -> None:
        """체결 확인 후 TradeResult 생성/업데이트"""
        ctx = analysis_context or {}
        now = now_kst()

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    repo = TradeResultRepository(session)

                    # 중복 체크 (P2-7: order_id UNIQUE)
                    if order_id:
                        existing = await repo.get_by_order_id(order_id)
                        if existing:
                            logger.debug("[{}] 주문번호 {} 이미 기록됨 → 스킵", symbol, order_id)
                            return

                    if side == "BUY":
                        # 매수 체결 → 새 TradeResult 생성 (미청산 상태)
                        tr = TradeResult(
                            order_id=order_id,
                            stock_symbol=symbol,
                            stock_name=ctx.get("stock_name", symbol),
                            side="BUY",
                            strategy_type=ctx.get("strategy_type", ""),
                            entry_price=filled_price,
                            exit_price=0.0,
                            quantity=filled_qty,
                            pnl=0.0,
                            return_pct=0.0,
                            is_win=False,
                            hold_days=0,
                            ai_recommendation=ctx.get("ai_recommendation", ""),
                            ai_confidence=ctx.get("ai_confidence", 0.0),
                            ai_target_price=ctx.get("ai_target_price"),
                            ai_stop_loss_price=ctx.get("ai_stop_loss_price"),
                            entry_rsi=ctx.get("entry_rsi"),
                            entry_macd_hist=ctx.get("entry_macd_hist"),
                            entry_pattern=ctx.get("entry_pattern"),
                            market_regime=ctx.get("market_regime", ""),
                            entry_at=now,
                            notes=self._build_trade_notes(ctx, pending=False),
                        )
                        session.add(tr)

                        logger.info(
                            "[TradeResult] 매수 기록 생성: {} {}주 @{:,.0f}원",
                            symbol, filled_qty, filled_price,
                        )
                        await activity_logger.log(
                            ActivityType.TRADE_RESULT, ActivityPhase.COMPLETE,
                            f"\U0001f4dd [{symbol}] 매수 체결 기록: "
                            f"{filled_qty}주 @{filled_price:,.0f}원",
                            cycle_id=cycle_id,
                            symbol=symbol,
                        )

                    elif side == "SELL":
                        # 매도 체결 → 미청산 BUY 전체 일괄 청산
                        open_buys = await repo.get_all_open_buys(symbol)
                        if not open_buys:
                            logger.warning(
                                "[TradeResult] {} 미청산 매수 기록 없음 → 매도 기록만 생성",
                                symbol,
                            )
                            # 매수 기록 없이 매도만 온 경우 → 독립 기록
                            tr = TradeResult(
                                order_id=order_id,
                                stock_symbol=symbol,
                                stock_name=ctx.get("stock_name", symbol),
                                side="SELL",
                                strategy_type=ctx.get("strategy_type", ""),
                                entry_price=0.0,
                                exit_price=filled_price,
                                quantity=filled_qty,
                                exit_reason=exit_reason or "SIGNAL",
                                exit_at=now,
                                entry_at=now,
                            )
                            session.add(tr)
                            return

                        sell_fill = self._apply_sell_fill_to_open_buys(
                            session,
                            open_buys,
                            symbol=symbol,
                            filled_qty=filled_qty,
                            filled_price=filled_price,
                            exit_reason=exit_reason,
                            closed_at=now,
                        )
                        applied_qty = int(sell_fill["applied_quantity"] or 0)
                        total_pnl = float(sell_fill["total_pnl"] or 0.0)
                        closed_lot_count = int(sell_fill["closed_lot_count"] or 0)

                        # 마지막 BUY 기준으로 로깅
                        last_buy = open_buys[-1]
                        pnl_sign = "+" if total_pnl >= 0 else ""
                        avg_return = float(sell_fill["total_return_pct"] or 0.0) / max(closed_lot_count, 1)
                        logger.info(
                            "[TradeResult] 매도 청산: {} {}건 BUY {} 청산@{:,.0f} "
                            "= {}{:,.0f}원 ({}{:.1f}%)",
                            symbol, closed_lot_count, "부분" if sell_fill["partial_exit"] else "전량", filled_price,
                            pnl_sign, total_pnl, pnl_sign, avg_return,
                        )
                        await activity_logger.log(
                            ActivityType.TRADE_RESULT, ActivityPhase.COMPLETE,
                            f"{'✅' if total_pnl > 0 else '❌'} [{symbol}] 매도 청산: "
                            f"{closed_lot_count}건 BUY {'부분' if sell_fill['partial_exit'] else '전량'} — "
                            f"{pnl_sign}{total_pnl:,.0f}원 ({pnl_sign}{avg_return:.1f}%) "
                            f"| {exit_reason or 'SIGNAL'}"
                            + (f" | 체결 {applied_qty}주 / 잔량 {int(sell_fill['remaining_open_quantity'] or 0)}주" if sell_fill["partial_exit"] else ""),
                            cycle_id=cycle_id,
                            symbol=symbol,
                            detail={
                                "closed_count": closed_lot_count,
                                "exit_price": filled_price,
                                "total_pnl": total_pnl,
                                "avg_return_pct": avg_return,
                                "filled_quantity": applied_qty,
                                "remaining_open_quantity": int(sell_fill["remaining_open_quantity"] or 0),
                                "partial_exit": bool(sell_fill["partial_exit"]),
                            },
                        )

        except Exception as e:
            logger.error("[TradeResult] 기록 실패 ({}): {}", symbol, str(e))

    async def _create_recommendation(
        self, signal: TradeSignal, analysis_id: str, cycle_id: str | None = None,
    ) -> dict:
        """반자율: 추천 생성 → 사용자 승인 대기"""
        expires_at = now_kst() + timedelta(minutes=settings.RECOMMENDATION_EXPIRE_MIN)

        rec_data = {
            "stock_id": signal.stock_id,
            "analysis_id": analysis_id,
            "action": signal.action.value,
            "suggested_price": signal.suggested_price or 0,
            "suggested_quantity": signal.suggested_quantity or 0,
            "reason": signal.reason,
            "confidence": signal.confidence,
            "status": RecommendationStatus.PENDING.value,
            "expires_at": expires_at,
        }

        qty = signal.suggested_quantity or 0
        price = signal.suggested_price or 0
        amount = price * qty

        logger.info(
            "[SEMI_AUTO] 추천 생성: {} {} x{} (만료: {})",
            signal.symbol, signal.action.value,
            qty, expires_at,
        )

        await activity_logger.log(
            ActivityType.DECISION, ActivityPhase.COMPLETE,
            f"\U0001f4dd {'매도' if signal.action.value == 'SELL' else '매수'} 추천 생성: {signal.symbol} {qty}주 "
            f"@{price:,.0f}원 ({amount:,.0f}원)"
            f"\n   \u2192 사용자 승인 대기 (SEMI_AUTO 모드)",
            cycle_id=cycle_id,
            symbol=signal.symbol,
            confidence=signal.confidence,
            detail=rec_data,
        )

        await event_bus.publish(Event(
            type=EventType.RECOMMENDATION_CREATED,
            data={**rec_data, "symbol": signal.symbol},
            source="decision_maker",
        ))
        await self._record_decision_event(
            signal,
            cycle_id=cycle_id,
            decision_stage="RECOMMENDATION",
            risk_gate_result="PENDING_APPROVAL",
            final_action=signal.action.value,
            status="RECOMMENDED",
            reason=signal.reason,
            result={"mode": "SEMI_AUTO", "recommendation": rec_data},
            analysis_context={"analysis_id": analysis_id},
        )

        return {
            "mode": "SEMI_AUTO",
            "symbol": signal.symbol,
            "action": signal.action.value,
            "recommendation": rec_data,
        }


decision_maker = DecisionMaker()
