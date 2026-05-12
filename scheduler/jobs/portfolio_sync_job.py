"""장 마감 후 포트폴리오 정산 — PENDING_CONFIRM 복구 + 계좌/DB 불일치 점검"""
import contextlib
from datetime import datetime, timedelta

from loguru import logger
from models.trade_result import TradeResult
from trading.symbols import normalize_krx_symbol
from util.time_util import now_kst


def _no_autoflush(session):
    """session.no_autoflush가 없는 mock 환경에서도 안전하게 동작하는 래퍼"""
    ctx = getattr(session, "no_autoflush", None)
    if ctx is None:
        return contextlib.nullcontext()
    return ctx


async def portfolio_sync_job() -> None:
    """KIS 계좌와 포트폴리오 DB 동기화"""
    logger.debug("포트폴리오 정산 시작")

    # 1. PENDING_CONFIRM 복구: 체결 확인 누락된 주문 재확인
    await _recover_pending_confirms()

    # 1-1. 계좌에는 있는데 DB에 없는 열린 매수 백필
    await _backfill_missing_open_buys_from_holdings()

    # 1-2. 과거 0원 체결가 복구: 현재 보유 평균단가와 정합할 때만 보정
    await _repair_confirmed_zero_entry_prices()

    # 1-3. 계좌에 없는 DB 미청산 BUY는 경고만 기록 (자동 변경 없음)
    await _close_open_buys_missing_from_holdings(dry_run=True)
    await _close_open_buy_quantity_excess_from_holdings(dry_run=True)

    # 2. 정산 현황 로깅 (계좌 vs DB 비교, 강제 변경 없음)
    await _check_account_db_consistency()

    logger.debug("포트폴리오 정산 완료")


PENDING_CONFIRM_CHUNK_SIZE = 5
BUY_PENDING_CONFIRM_STALE_AFTER = timedelta(seconds=90)


def _is_pending_confirm_stale(trade, *, now: datetime, stale_after: timedelta) -> bool:
    created_at = getattr(trade, "created_at", None) or getattr(trade, "entry_at", None)
    if not isinstance(created_at, datetime):
        return False
    comparable_now = now
    if getattr(created_at, "tzinfo", None) is not None and getattr(comparable_now, "tzinfo", None) is None:
        comparable_now = comparable_now.replace(tzinfo=created_at.tzinfo)
    if getattr(created_at, "tzinfo", None) is None and getattr(comparable_now, "tzinfo", None) is not None:
        comparable_now = comparable_now.replace(tzinfo=None)
    return comparable_now - created_at >= stale_after


def _mark_pending_confirm_failed(trade, *, reason: str) -> None:
    trade.status = "CONFIRM_FAILED"
    previous_notes = str(getattr(trade, "notes", "") or "").strip()
    note = f"CONFIRM_FAILED: {reason}"
    trade.notes = f"{note} | previous={previous_notes[:160]}" if previous_notes else note


async def _recover_pending_confirms() -> dict[str, int | str]:
    """PENDING_CONFIRM 상태 레코드 복구 — 체결 여부 재확인.

    SQLite write lock 점유 시간을 줄이기 위해 chunk 단위로 commit을 분리한다.
    한 chunk가 실패해도 이전 chunk의 결과는 보존된다.
    """
    summary: dict[str, int | str] = {
        "provider": "UNKNOWN",
        "pending_total": 0,
        "recovered": 0,
        "failed": 0,
        "skipped": 0,
    }
    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.broker_factory import get_broker_adapter

        async with AsyncSessionLocal() as session:
            repo = TradeResultRepository(session)
            pending = await repo.get_pending_confirms()
            pending_refs = [
                (getattr(trade, "id", None), trade)
                for trade in pending
            ]

        summary["pending_total"] = len(pending_refs)
        adapter = get_broker_adapter()
        summary["provider"] = adapter.provider.value

        if not pending_refs:
            return summary

        logger.debug(
            "PENDING_CONFIRM 복구 대상: {}건 (chunk={}건)",
            len(pending_refs), PENDING_CONFIRM_CHUNK_SIZE,
        )

        pending_orders = await adapter.get_pending_orders()
        holdings = await adapter.get_holdings()
        order_map = {str(order.order_id): order for order in pending_orders if order.order_id}
        holding_map = {
            normalize_krx_symbol(getattr(holding, "symbol", "")): holding
            for holding in holdings
            if int(getattr(holding, "quantity", 0) or 0) > 0
        }

        last_error: str | None = None
        for chunk_start in range(0, len(pending_refs), PENDING_CONFIRM_CHUNK_SIZE):
            chunk = pending_refs[chunk_start : chunk_start + PENDING_CONFIRM_CHUNK_SIZE]
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        repo = TradeResultRepository(session)
                        with _no_autoflush(session):
                            for trade_id, pending_trade in chunk:
                                tr = (
                                    await repo.get_by_id(trade_id)
                                    if trade_id is not None
                                    else pending_trade
                                )
                                await _process_one_pending(
                                    tr, repo, session, adapter, order_map, holding_map, summary,
                                )
                        flush = getattr(session, "flush", None)
                        if flush is not None:
                            await flush()
            except Exception as chunk_exc:
                last_error = str(chunk_exc)[:200]
                logger.error(
                    "PENDING_CONFIRM 복구 chunk 실패 (offset={}): {} — 다음 chunk 계속",
                    chunk_start, last_error,
                )

        if last_error:
            summary["error"] = last_error
        if int(summary["recovered"]) or int(summary["failed"]):
            logger.debug(
                "PENDING_CONFIRM 복구 결과: 성공 {}건, 실패 {}건, 보류 {}건",
                summary["recovered"], summary["failed"], summary["skipped"],
            )
    except Exception as e:
        logger.error("PENDING_CONFIRM 복구 오류: {}", str(e))
        summary["error"] = str(e)[:200]
    return summary


async def _process_one_pending(tr, repo, session, adapter, order_map, holding_map, summary) -> None:
    """단일 PENDING_CONFIRM 레코드 복구 처리"""
    from agent.decision_maker import DecisionMaker
    from trading.enums import BrokerProvider, OrderConfirmStatus

    if not tr or tr.status != OrderConfirmStatus.PENDING_CONFIRM.value:
        return

    matched = order_map.get(str(tr.order_id))
    symbol = normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
    if matched:
        filled_qty = int(getattr(matched, "filled_qty", 0) or 0)
        if filled_qty > 0:
            tr.status = OrderConfirmStatus.CONFIRMED.value
            tr.quantity = filled_qty
            filled_price = float(getattr(matched, "order_price", 0.0) or 0.0)
            if filled_price > 0:
                if tr.side == "BUY":
                    tr.entry_price = filled_price
                elif tr.side == "SELL":
                    tr.exit_price = filled_price
            tr.notes = None
            logger.debug(
                "PENDING 복구: {} {} {}주 → CONFIRMED",
                tr.stock_symbol, tr.side, filled_qty,
            )
            summary["recovered"] = int(summary["recovered"]) + 1
            return
        if adapter.provider == BrokerProvider.KIWOOM:
            logger.warning(
                "PENDING 복구 보류: {} {} 주문번호={} — 키움 미체결 주문 유지",
                tr.stock_symbol, tr.side, tr.order_id,
            )
            summary["skipped"] = int(summary["skipped"]) + 1
            return
    elif tr.side == "SELL":
        holding = holding_map.get(symbol)
        current_qty = int(getattr(holding, "quantity", 0) or 0) if holding else 0
        open_buys = await repo.get_all_open_buys(symbol)
        total_open_qty = sum(int(getattr(open_buy, "quantity", 0) or 0) for open_buy in open_buys)
        requested_qty = int(getattr(tr, "quantity", 0) or 0)
        if (
            adapter.provider == BrokerProvider.KIWOOM
            and requested_qty > 0
            and total_open_qty > current_qty + requested_qty
        ):
            neutral_fill = DecisionMaker._neutral_close_excess_open_buys(
                session,
                open_buys,
                symbol=symbol,
                target_open_qty=current_qty + requested_qty,
                closed_at=now_kst(),
                note_reason="before pending sell recovery",
            )
            if neutral_fill["closed_quantity"] > 0:
                total_open_qty = sum(
                    int(getattr(open_buy, "quantity", 0) or 0)
                    for open_buy in open_buys
                    if getattr(open_buy, "exit_at", None) is None
                )
                logger.warning(
                    "PENDING 복구 전 DB 초과수량 중립 정리: {} {}주 ({}건)",
                    symbol,
                    neutral_fill["closed_quantity"],
                    neutral_fill["closed_count"],
                )
        if (
            adapter.provider == BrokerProvider.KIWOOM
            and total_open_qty > 0
            and 0 <= current_qty < total_open_qty
        ):
            inferred_qty = total_open_qty - current_qty
            if inferred_qty <= 0 or (requested_qty > 0 and inferred_qty > requested_qty):
                logger.warning(
                    "PENDING 복구 보류: {} {} 주문번호={} — 키움 체결수량 추론 불일치 (요청 {}주 / 추론 {}주)",
                    tr.stock_symbol, tr.side, tr.order_id, requested_qty, inferred_qty,
                )
                summary["skipped"] = int(summary["skipped"]) + 1
                return
            filled_price = float(getattr(tr, "exit_price", 0.0) or 0.0)
            tr.status = OrderConfirmStatus.CONFIRMED.value
            tr.quantity = inferred_qty
            tr.exit_at = tr.exit_at or now_kst()
            tr.exit_reason = getattr(tr, "exit_reason", "") or "SIGNAL"
            sell_fill = DecisionMaker._apply_sell_fill_to_open_buys(
                session,
                open_buys,
                symbol=symbol,
                filled_qty=inferred_qty,
                filled_price=filled_price,
                exit_reason=tr.exit_reason,
                closed_at=tr.exit_at,
            )
            tr.notes = DecisionMaker._build_sell_fill_notes(
                partial_exit=bool(sell_fill["partial_exit"]),
                filled_quantity=int(sell_fill["applied_quantity"] or 0),
                requested_quantity=requested_qty or inferred_qty,
                remaining_open_quantity=int(sell_fill["remaining_open_quantity"] or 0),
                closed_lot_count=int(sell_fill["closed_lot_count"] or 0),
            )
            summary["recovered"] = int(summary["recovered"]) + 1
            logger.debug(
                "PENDING 복구({} 매도 추론): {} {} {}주 → CONFIRMED",
                "부분" if sell_fill["partial_exit"] else "전량",
                tr.stock_symbol,
                tr.side,
                int(sell_fill["applied_quantity"] or 0),
            )
            return
    elif tr.side == "BUY":
        holding = holding_map.get(symbol)
        if holding is not None:
            inferred_qty = min(int(holding.quantity), int(tr.quantity or holding.quantity))
            if inferred_qty > 0:
                tr.status = OrderConfirmStatus.CONFIRMED.value
                tr.quantity = inferred_qty
                if tr.entry_price <= 0 and holding.avg_buy_price > 0:
                    tr.entry_price = float(holding.avg_buy_price)
                tr.notes = None
                logger.debug(
                    "PENDING 복구(보유수량 추론): {} {} {}주 → CONFIRMED",
                    tr.stock_symbol, tr.side, inferred_qty,
                )
                summary["recovered"] = int(summary["recovered"]) + 1
                return
        if adapter.provider == BrokerProvider.KIWOOM:
            if _is_pending_confirm_stale(
                tr,
                now=now_kst(),
                stale_after=BUY_PENDING_CONFIRM_STALE_AFTER,
            ):
                reason = "키움 보유/미체결 매칭 없음 (stale BUY pending)"
                _mark_pending_confirm_failed(tr, reason=reason)
                logger.warning(
                    "PENDING 복구 실패 처리: {} {} 주문번호={} — {}",
                    tr.stock_symbol, tr.side, tr.order_id, reason,
                )
                summary["failed"] = int(summary["failed"]) + 1
            else:
                logger.warning(
                    "PENDING 복구 보류: {} {} 주문번호={} — 키움 보유/미체결 매칭 없음",
                    tr.stock_symbol, tr.side, tr.order_id,
                )
                summary["skipped"] = int(summary["skipped"]) + 1
            return
    elif adapter.provider == BrokerProvider.KIWOOM:
        logger.warning(
            "PENDING 복구 보류: {} {} 주문번호={} — 키움 매칭 정보 부족",
            tr.stock_symbol, tr.side, tr.order_id,
        )
        summary["skipped"] = int(summary["skipped"]) + 1
        return

    if matched:
        tr.status = OrderConfirmStatus.CONFIRM_FAILED.value
        tr.notes = "CONFIRM_FAILED: 체결수량 0 (정산 시 복구)"
        summary["failed"] = int(summary["failed"]) + 1
        await _cancel_unfilled_order(str(tr.order_id), tr.stock_symbol)
    else:
        tr.status = OrderConfirmStatus.CONFIRM_FAILED.value
        tr.notes = "CONFIRM_FAILED: 주문내역/보유종목에서 미발견 (정산 시 복구)"
        summary["failed"] = int(summary["failed"]) + 1
        await _cancel_unfilled_order(str(tr.order_id), tr.stock_symbol)


async def _repair_confirmed_zero_entry_prices() -> dict[str, int | str]:
    """미청산 CONFIRMED BUY 중 0원 체결가를 안전하게 복구"""
    summary: dict[str, int | str] = {
        "provider": "UNKNOWN",
        "candidates": 0,
        "repaired": 0,
        "skipped": 0,
    }
    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.broker_factory import get_broker_adapter

        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                zero_trades = await repo.get_confirmed_open_buys_with_zero_entry_price()
                summary["candidates"] = len(zero_trades)
                if not zero_trades:
                    return summary

                adapter = get_broker_adapter()
                summary["provider"] = adapter.provider.value
                holdings = await adapter.get_holdings()
                holding_map = {
                    normalize_krx_symbol(getattr(holding, "symbol", "")): holding
                    for holding in holdings
                    if int(getattr(holding, "quantity", 0) or 0) > 0
                }

                pending_symbols = {
                    normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    for tr in await repo.get_pending_confirms()
                    if getattr(tr, "side", "") == "BUY"
                }

                grouped: dict[str, list] = {}
                for trade in zero_trades:
                    grouped.setdefault(normalize_krx_symbol(trade.stock_symbol), []).append(trade)

                for symbol, trades in grouped.items():
                    if symbol in pending_symbols:
                        logger.warning("0원 체결가 복구 보류: {} — pending confirm 존재", symbol)
                        summary["skipped"] = int(summary["skipped"]) + len(trades)
                        continue

                    holding = holding_map.get(symbol)
                    if holding is None:
                        logger.warning("0원 체결가 복구 보류: {} — 보유 정보 없음", symbol)
                        summary["skipped"] = int(summary["skipped"]) + len(trades)
                        continue

                    open_buys = await repo.get_all_open_buys(symbol)
                    if not open_buys:
                        summary["skipped"] = int(summary["skipped"]) + len(trades)
                        continue

                    holding_qty = int(getattr(holding, "quantity", 0) or 0)
                    open_qty = sum(int(getattr(tr, "quantity", 0) or 0) for tr in open_buys)
                    if holding_qty != open_qty:
                        logger.warning(
                            "0원 체결가 복구 보류: {} — 보유수량 {} != DB 미청산수량 {}",
                            symbol, holding_qty, open_qty,
                        )
                        summary["skipped"] = int(summary["skipped"]) + len(trades)
                        continue

                    known_value = sum(
                        float(getattr(tr, "entry_price", 0.0) or 0.0) * int(getattr(tr, "quantity", 0) or 0)
                        for tr in open_buys
                        if float(getattr(tr, "entry_price", 0.0) or 0.0) > 0
                    )
                    unknown_qty = sum(
                        int(getattr(tr, "quantity", 0) or 0)
                        for tr in open_buys
                        if float(getattr(tr, "entry_price", 0.0) or 0.0) <= 0
                    )
                    if unknown_qty <= 0:
                        continue

                    target_total_cost = float(getattr(holding, "avg_buy_price", 0.0) or 0.0) * holding_qty
                    repaired_price = (target_total_cost - known_value) / unknown_qty
                    if repaired_price <= 0:
                        logger.warning("0원 체결가 복구 보류: {} — 역산 가격 비정상 {}", symbol, repaired_price)
                        summary["skipped"] = int(summary["skipped"]) + len(trades)
                        continue

                    for trade in trades:
                        trade.entry_price = float(repaired_price)
                    logger.info(
                        "0원 체결가 복구 완료: {} {}건 → @{:.2f}원",
                        symbol, len(trades), repaired_price,
                    )
                    summary["repaired"] = int(summary["repaired"]) + len(trades)
    except Exception as e:
        logger.error("0원 체결가 복구 오류: {}", str(e))
        summary["error"] = str(e)[:200]
    return summary


async def _backfill_missing_open_buys_from_holdings() -> dict[str, int | str]:
    """계좌 보유수량이 DB 미청산수량보다 많을 때 합성 BUY 레코드로 메움"""
    summary: dict[str, int | str] = {
        "provider": "UNKNOWN",
        "backfilled": 0,
        "skipped": 0,
    }
    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.broker_factory import get_broker_adapter

        now = now_kst()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                adapter = get_broker_adapter()
                summary["provider"] = adapter.provider.value
                holdings = await adapter.get_holdings()
                pending_symbols = {
                    normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    for tr in await repo.get_pending_confirms()
                    if getattr(tr, "side", "") == "BUY"
                }

                backfill_rows: list[TradeResult] = []
                for holding in holdings:
                    symbol = normalize_krx_symbol(getattr(holding, "symbol", ""))
                    holding_qty = int(getattr(holding, "quantity", 0) or 0)
                    if not symbol or holding_qty <= 0:
                        continue
                    if symbol in pending_symbols:
                        logger.warning("보유 백필 보류: {} — pending confirm 존재", symbol)
                        summary["skipped"] = int(summary["skipped"]) + 1
                        continue

                    open_buys = await repo.get_all_open_buys(symbol)
                    open_qty = sum(int(getattr(tr, "quantity", 0) or 0) for tr in open_buys)
                    missing_qty = holding_qty - open_qty
                    if missing_qty <= 0:
                        continue

                    avg_buy_price = float(getattr(holding, "avg_buy_price", 0.0) or 0.0)
                    if avg_buy_price <= 0:
                        logger.warning("보유 백필 보류: {} — 평균단가 없음", symbol)
                        summary["skipped"] = int(summary["skipped"]) + 1
                        continue

                    backfill_rows.append(TradeResult(
                        order_id=None,
                        stock_symbol=symbol,
                        stock_name=getattr(holding, "name", symbol) or symbol,
                        side="BUY",
                        strategy_type="HOLDING_SYNC",
                        entry_price=avg_buy_price,
                        exit_price=0.0,
                        quantity=missing_qty,
                        pnl=0.0,
                        return_pct=0.0,
                        is_win=False,
                        hold_days=0,
                        exit_reason="",
                        ai_recommendation="",
                        ai_confidence=0.0,
                        ai_target_price=None,
                        ai_stop_loss_price=None,
                        market_regime="",
                        notes=f"HOLDING_SYNC_BACKFILL: holding_qty={holding_qty}, db_qty={open_qty}",
                        status="CONFIRMED",
                        entry_at=now,
                    ))
                    logger.warning(
                        "보유 백필 생성: {} {}주 @{:.2f}원 (계좌 {}주 / DB {}주)",
                        symbol, missing_qty, avg_buy_price, holding_qty, open_qty,
                    )
                if backfill_rows:
                    for row in backfill_rows:
                        session.add(row)
                    summary["backfilled"] = len(backfill_rows)
    except Exception as e:
        logger.error("보유 백필 오류: {}", str(e))
        summary["error"] = str(e)[:200]
    return summary


async def _close_open_buys_missing_from_holdings(*, dry_run: bool = True) -> dict[str, object]:
    """브로커 계좌에 없는 DB 미청산 BUY를 수동 정리 후보로 산출/종료.

    apply 모드에서도 실제 주문은 내지 않는다. 포지션 상태 오염을 막기 위한 DB 정합성 정리이며,
    성과 리포트 왜곡을 피하려고 진입가로 중립 종료 처리한다.
    """
    summary: dict[str, object] = {
        "mode": "dry_run" if dry_run else "apply",
        "provider": "UNKNOWN",
        "holding_symbol_count": 0,
        "open_symbol_count": 0,
        "candidate_count": 0,
        "closed_count": 0,
        "skipped_count": 0,
    }
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.broker_factory import get_broker_adapter

        adapter = get_broker_adapter()
        summary["provider"] = adapter.provider.value
        holdings = await adapter.get_holdings()
        pending_orders = await adapter.get_pending_orders()
        holding_symbols = {
            normalize_krx_symbol(getattr(holding, "symbol", ""))
            for holding in holdings
            if int(getattr(holding, "quantity", 0) or 0) > 0
        }
        broker_pending_symbols = {
            normalize_krx_symbol(getattr(order, "symbol", ""))
            for order in pending_orders
            if int(getattr(order, "remaining_qty", 0) or 0) > 0
        }
        summary["holding_symbol_count"] = len(holding_symbols)

        now = now_kst()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                open_buys = await repo.get_all_open()
                pending_symbols = {
                    normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    for tr in await repo.get_pending_confirms()
                }
                open_symbols = {
                    normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    for tr in open_buys
                }
                summary["open_symbol_count"] = len(open_symbols)

                for trade in open_buys:
                    symbol = normalize_krx_symbol(getattr(trade, "stock_symbol", ""))
                    if not symbol or symbol in holding_symbols:
                        continue

                    item = {
                        "trade_id": getattr(trade, "id", None),
                        "stock_symbol": symbol,
                        "stock_name": getattr(trade, "stock_name", symbol),
                        "quantity": int(getattr(trade, "quantity", 0) or 0),
                        "entry_price": float(getattr(trade, "entry_price", 0.0) or 0.0),
                        "entry_at": getattr(trade, "entry_at", None).isoformat()
                        if getattr(trade, "entry_at", None) else None,
                    }

                    if symbol in pending_symbols:
                        skipped.append({**item, "reason": "db_pending_confirm_exists"})
                        continue
                    if symbol in broker_pending_symbols:
                        skipped.append({**item, "reason": "broker_pending_order_exists"})
                        continue

                    candidates.append(item)
                    if dry_run:
                        continue

                    entry_price = float(getattr(trade, "entry_price", 0.0) or 0.0)
                    trade.exit_price = entry_price
                    trade.pnl = 0.0
                    trade.return_pct = 0.0
                    trade.is_win = False
                    entry_at = getattr(trade, "entry_at", None)
                    if entry_at:
                        comparable_now = now
                        if getattr(entry_at, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
                            comparable_now = now.replace(tzinfo=None)
                        trade.hold_days = max((comparable_now - entry_at).days, 0)
                    else:
                        trade.hold_days = 0
                    trade.exit_reason = "BROKER_HOLDING_MISSING"
                    trade.exit_at = now
                    previous_notes = str(getattr(trade, "notes", "") or "").strip()
                    note = "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close"
                    trade.notes = f"{note} | previous={previous_notes[:160]}" if previous_notes else note
                    summary["closed_count"] = int(summary["closed_count"]) + 1

                summary["candidate_count"] = len(candidates)
                summary["skipped_count"] = len(skipped)
    except Exception as e:
        logger.error("브로커 미보유 DB BUY 정리 오류: {}", str(e))
        summary["error"] = str(e)[:200]

    return {
        "summary": summary,
        "candidates": candidates,
        "skipped": skipped,
    }


def _set_neutral_close(trade, *, closed_at, exit_reason: str, note: str) -> None:
    entry_price = float(getattr(trade, "entry_price", 0.0) or 0.0)
    trade.exit_price = entry_price
    trade.pnl = 0.0
    trade.return_pct = 0.0
    trade.is_win = False
    entry_at = getattr(trade, "entry_at", None)
    if entry_at:
        comparable_now = closed_at
        if getattr(entry_at, "tzinfo", None) is None and getattr(closed_at, "tzinfo", None) is not None:
            comparable_now = closed_at.replace(tzinfo=None)
        trade.hold_days = max((comparable_now - entry_at).days, 0)
    else:
        trade.hold_days = 0
    trade.exit_reason = exit_reason
    trade.exit_at = closed_at
    previous_notes = str(getattr(trade, "notes", "") or "").strip()
    trade.notes = f"{note} | previous={previous_notes[:160]}" if previous_notes else note


def _build_partial_reconciliation_close(open_buy, *, close_qty: int, symbol: str) -> TradeResult:
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
        status=str(getattr(open_buy, "status", "CONFIRMED") or "CONFIRMED"),
        entry_at=getattr(open_buy, "entry_at", None),
    )


async def _close_open_buy_quantity_excess_from_holdings(*, dry_run: bool = True) -> dict[str, object]:
    """브로커 보유수량보다 DB 미청산 BUY 수량이 많은 lot을 산출/중립 종료."""
    summary: dict[str, object] = {
        "mode": "dry_run" if dry_run else "apply",
        "provider": "UNKNOWN",
        "holding_symbol_count": 0,
        "candidate_count": 0,
        "closed_count": 0,
        "closed_quantity": 0,
        "split_count": 0,
        "skipped_count": 0,
    }
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.broker_factory import get_broker_adapter

        adapter = get_broker_adapter()
        summary["provider"] = adapter.provider.value
        holdings = await adapter.get_holdings()
        pending_orders = await adapter.get_pending_orders()
        holding_qty_by_symbol = {
            normalize_krx_symbol(getattr(holding, "symbol", "")): int(getattr(holding, "quantity", 0) or 0)
            for holding in holdings
            if int(getattr(holding, "quantity", 0) or 0) > 0
        }
        broker_pending_symbols = {
            normalize_krx_symbol(getattr(order, "symbol", ""))
            for order in pending_orders
            if int(getattr(order, "remaining_qty", 0) or 0) > 0
        }
        summary["holding_symbol_count"] = len(holding_qty_by_symbol)

        now = now_kst()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                db_pending_symbols = {
                    normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                    for tr in await repo.get_pending_confirms()
                }

                for symbol, holding_qty in holding_qty_by_symbol.items():
                    if not symbol or holding_qty <= 0:
                        continue

                    open_buys = await repo.get_all_open_buys(symbol)
                    open_buys = [tr for tr in open_buys if int(getattr(tr, "quantity", 0) or 0) > 0]
                    db_qty = sum(int(getattr(tr, "quantity", 0) or 0) for tr in open_buys)
                    excess_qty = db_qty - holding_qty
                    if excess_qty <= 0:
                        continue

                    item = {
                        "stock_symbol": symbol,
                        "stock_name": getattr(open_buys[0], "stock_name", symbol) if open_buys else symbol,
                        "holding_quantity": holding_qty,
                        "db_open_quantity": db_qty,
                        "excess_quantity": excess_qty,
                    }
                    if symbol in db_pending_symbols:
                        skipped.append({**item, "reason": "db_pending_confirm_exists"})
                        continue
                    if symbol in broker_pending_symbols:
                        skipped.append({**item, "reason": "broker_pending_order_exists"})
                        continue

                    candidates.append(item)
                    if dry_run:
                        continue

                    remaining_to_close = excess_qty
                    sorted_buys = sorted(
                        open_buys,
                        key=lambda tr: (
                            getattr(tr, "entry_at", None) is None,
                            getattr(tr, "entry_at", None),
                            str(getattr(tr, "id", "")),
                        ),
                    )
                    for open_buy in sorted_buys:
                        if remaining_to_close <= 0:
                            break
                        lot_qty = int(getattr(open_buy, "quantity", 0) or 0)
                        close_qty = min(lot_qty, remaining_to_close)
                        if close_qty <= 0:
                            continue

                        note = (
                            "HOLDING_RECONCILIATION_CLOSE: broker holding quantity lower; "
                            f"neutral close | holding_qty={holding_qty}, db_qty={db_qty}, close_qty={close_qty}"
                        )
                        target = open_buy
                        if close_qty < lot_qty:
                            target = _build_partial_reconciliation_close(open_buy, close_qty=close_qty, symbol=symbol)
                            session.add(target)
                            open_buy.quantity = lot_qty - close_qty
                            summary["split_count"] = int(summary["split_count"]) + 1

                        _set_neutral_close(
                            target,
                            closed_at=now,
                            exit_reason="BROKER_HOLDING_QUANTITY_MISMATCH",
                            note=note,
                        )
                        remaining_to_close -= close_qty
                        summary["closed_quantity"] = int(summary["closed_quantity"]) + close_qty
                        summary["closed_count"] = int(summary["closed_count"]) + 1

                summary["candidate_count"] = len(candidates)
                summary["skipped_count"] = len(skipped)
    except Exception as e:
        logger.error("브로커 보유수량 초과 DB BUY 정리 오류: {}", str(e))
        summary["error"] = str(e)[:200]

    return {
        "summary": summary,
        "candidates": candidates,
        "skipped": skipped,
    }


async def _cancel_unfilled_order(order_id: str, symbol: str) -> None:
    """미체결 주문 취소 시도 (정산용)"""
    if not order_id:
        return
    try:
        from trading.broker_factory import get_broker_adapter

        result = await get_broker_adapter().cancel_order(order_id)
        if result.success:
            logger.debug("[정산] {} 미체결 주문 취소 완료: {}", symbol, order_id)
        else:
            logger.warning("[정산] {} 미체결 주문 취소 실패: {} — {}", symbol, order_id, result.message)
    except Exception as e:
        logger.warning("[정산] {} 미체결 주문 취소 오류: {} — {}", symbol, order_id, str(e))


async def _check_account_db_consistency() -> None:
    """계좌 보유종목 vs DB 미청산 포지션 비교 (경고 로그만, 수정 없음)"""
    try:
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.account_manager import account_manager

        holdings = await account_manager.get_holdings()
        holding_symbols = {
            normalize_krx_symbol(getattr(h, "symbol", ""))
            for h in holdings
            if int(getattr(h, "quantity", 0) or 0) > 0
        }

        async with AsyncSessionLocal() as session:
            repo = TradeResultRepository(session)
            open_positions = await repo.get_all_open()
            db_symbols = {
                normalize_krx_symbol(getattr(tr, "stock_symbol", ""))
                for tr in open_positions
            }

        # 계좌에만 있는 종목 (DB에 기록 없음)
        only_account = holding_symbols - db_symbols
        # DB에만 있는 종목 (계좌에 없음 = stale 레코드 가능)
        only_db = db_symbols - holding_symbols

        if only_account:
            logger.warning(
                "계좌에만 존재 (DB 미등록): {} — 수동 확인 필요",
                ", ".join(only_account),
            )
        if only_db:
            logger.warning(
                "DB에만 존재 (계좌 미보유): {} — stale 레코드 가능성",
                ", ".join(only_db),
            )
        if not only_account and not only_db:
            logger.debug("계좌/DB 포지션 일치 ({}종목)", len(holding_symbols))
    except Exception as e:
        logger.error("계좌/DB 일관성 체크 오류: {}", str(e))
