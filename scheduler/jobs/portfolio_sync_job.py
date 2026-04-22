"""장 마감 후 포트폴리오 정산 — PENDING_CONFIRM 복구 + 계좌/DB 불일치 점검"""
from loguru import logger
from models.trade_result import TradeResult
from trading.symbols import normalize_krx_symbol
from util.time_util import now_kst


async def portfolio_sync_job() -> None:
    """KIS 계좌와 포트폴리오 DB 동기화"""
    logger.debug("포트폴리오 정산 시작")

    # 1. PENDING_CONFIRM 복구: 체결 확인 누락된 주문 재확인
    await _recover_pending_confirms()

    # 1-1. 계좌에는 있는데 DB에 없는 열린 매수 백필
    await _backfill_missing_open_buys_from_holdings()

    # 1-2. 과거 0원 체결가 복구: 현재 보유 평균단가와 정합할 때만 보정
    await _repair_confirmed_zero_entry_prices()

    # 2. 정산 현황 로깅 (계좌 vs DB 비교, 강제 변경 없음)
    await _check_account_db_consistency()

    logger.debug("포트폴리오 정산 완료")


async def _recover_pending_confirms() -> dict[str, int | str]:
    """PENDING_CONFIRM 상태 레코드 복구 — 체결 여부 재확인"""
    summary: dict[str, int | str] = {
        "provider": "UNKNOWN",
        "pending_total": 0,
        "recovered": 0,
        "failed": 0,
        "skipped": 0,
    }
    try:
        from agent.decision_maker import DecisionMaker
        from core.database import AsyncSessionLocal
        from repositories.trade_result_repository import TradeResultRepository
        from trading.enums import BrokerProvider, OrderConfirmStatus
        from trading.broker_factory import get_broker_adapter

        async with AsyncSessionLocal() as session:
            async with session.begin():
                repo = TradeResultRepository(session)
                pending = await repo.get_pending_confirms()
                summary["pending_total"] = len(pending)
                adapter = get_broker_adapter()
                summary["provider"] = adapter.provider.value

                if not pending:
                    return summary

                logger.debug("PENDING_CONFIRM 복구 대상: {}건", len(pending))

                pending_orders = await adapter.get_pending_orders()
                holdings = await adapter.get_holdings()
                order_map = {str(order.order_id): order for order in pending_orders if order.order_id}
                holding_map = {
                    normalize_krx_symbol(getattr(holding, "symbol", "")): holding
                    for holding in holdings
                    if int(getattr(holding, "quantity", 0) or 0) > 0
                }

                recovered = 0
                failed = 0
                for tr in pending:
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
                            recovered += 1
                            logger.debug(
                                "PENDING 복구: {} {} {}주 → CONFIRMED",
                                tr.stock_symbol, tr.side, filled_qty,
                            )
                            summary["recovered"] = int(summary["recovered"]) + 1
                            continue
                        if adapter.provider == BrokerProvider.KIWOOM:
                            logger.warning(
                                "PENDING 복구 보류: {} {} 주문번호={} — 키움 미체결 주문 유지",
                                tr.stock_symbol, tr.side, tr.order_id,
                            )
                            summary["skipped"] = int(summary["skipped"]) + 1
                            continue
                    elif tr.side == "SELL":
                        holding = holding_map.get(symbol)
                        current_qty = int(getattr(holding, "quantity", 0) or 0) if holding else 0
                        open_buys = await repo.get_all_open_buys(symbol)
                        total_open_qty = sum(int(getattr(open_buy, "quantity", 0) or 0) for open_buy in open_buys)
                        if (
                            adapter.provider == BrokerProvider.KIWOOM
                            and total_open_qty > 0
                            and 0 <= current_qty < total_open_qty
                        ):
                            inferred_qty = total_open_qty - current_qty
                            requested_qty = int(getattr(tr, "quantity", 0) or 0)
                            if inferred_qty <= 0 or (requested_qty > 0 and inferred_qty > requested_qty):
                                logger.warning(
                                    "PENDING 복구 보류: {} {} 주문번호={} — 키움 체결수량 추론 불일치 (요청 {}주 / 추론 {}주)",
                                    tr.stock_symbol, tr.side, tr.order_id, requested_qty, inferred_qty,
                                )
                                summary["skipped"] = int(summary["skipped"]) + 1
                                continue
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
                            recovered += 1
                            summary["recovered"] = int(summary["recovered"]) + 1
                            logger.debug(
                                "PENDING 복구({} 매도 추론): {} {} {}주 → CONFIRMED",
                                "부분" if sell_fill["partial_exit"] else "전량",
                                tr.stock_symbol,
                                tr.side,
                                int(sell_fill["applied_quantity"] or 0),
                            )
                            continue
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
                                recovered += 1
                                logger.debug(
                                    "PENDING 복구(보유수량 추론): {} {} {}주 → CONFIRMED",
                                    tr.stock_symbol, tr.side, inferred_qty,
                                )
                                summary["recovered"] = int(summary["recovered"]) + 1
                                continue
                        if adapter.provider == BrokerProvider.KIWOOM:
                            logger.warning(
                                "PENDING 복구 보류: {} {} 주문번호={} — 키움 보유/미체결 매칭 없음",
                                tr.stock_symbol, tr.side, tr.order_id,
                            )
                            summary["skipped"] = int(summary["skipped"]) + 1
                            continue
                    elif adapter.provider == BrokerProvider.KIWOOM:
                        logger.warning(
                            "PENDING 복구 보류: {} {} 주문번호={} — 키움 매칭 정보 부족",
                            tr.stock_symbol, tr.side, tr.order_id,
                        )
                        summary["skipped"] = int(summary["skipped"]) + 1
                        continue

                    if matched:
                        tr.status = OrderConfirmStatus.CONFIRM_FAILED.value
                        tr.notes = "CONFIRM_FAILED: 체결수량 0 (정산 시 복구)"
                        failed += 1
                        summary["failed"] = int(summary["failed"]) + 1
                        # 미체결 주문 취소 시도
                        await _cancel_unfilled_order(str(tr.order_id), tr.stock_symbol)
                    else:
                        tr.status = OrderConfirmStatus.CONFIRM_FAILED.value
                        tr.notes = "CONFIRM_FAILED: 주문내역/보유종목에서 미발견 (정산 시 복구)"
                        failed += 1
                        summary["failed"] = int(summary["failed"]) + 1
                        # 미체결 주문 취소 시도
                        await _cancel_unfilled_order(str(tr.order_id), tr.stock_symbol)

                if recovered or failed:
                    logger.debug(
                        "PENDING_CONFIRM 복구 결과: 성공 {}건, 실패 {}건",
                        recovered, failed,
                    )
    except Exception as e:
        logger.error("PENDING_CONFIRM 복구 오류: {}", str(e))
        summary["error"] = str(e)[:200]
    return summary


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

                    session.add(TradeResult(
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
                    summary["backfilled"] = int(summary["backfilled"]) + 1
    except Exception as e:
        logger.error("보유 백필 오류: {}", str(e))
        summary["error"] = str(e)[:200]
    return summary


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
