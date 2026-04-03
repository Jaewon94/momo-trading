"""관리자 대시보드 API — SSE 스트림 + 활동 조회 + 설정 + 리포트 + 계좌 + Q&A"""
import asyncio
import json as _json
import time as _time
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from admin.sse_manager import sse_manager
from analysis.llm.model_catalog import model_catalog_service
from core.config import normalize_llm_model_value, settings
from core.database import get_async_db
from repositories.agent_activity_repository import AgentActivityRepository
from repositories.daily_report_repository import DailyReportRepository
from repositories.trade_result_repository import TradeResultRepository
from schemas.activity_schema import ActivityResponse, CycleResponse
from schemas.common import SuccessResponse
from schemas.daily_report_schema import DailyReportResponse
from schemas.feedback_schema import TradeResultResponse
from schemas.qa_schema import QARequest, QAResponse
from scheduler.jobs import portfolio_sync_job
from services.activity_logger import activity_logger
from services.llm_usage_service import llm_usage_service
from strategy.risk_appetite_insights import build_strategy_insights
from trading.account_manager import account_manager
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType, LLMTier
from trading.mcp_client import mcp_client
from trading.symbols import normalize_krx_symbol
from scheduler.scheduler import trading_scheduler

router = APIRouter(prefix="/admin", tags=["admin"])
POSITION_DETAIL_HOLDING_TIMEOUT_SEC = 2.0
POSITION_DETAIL_HOLDING_CACHE_TTL_SEC = 15.0
_position_holdings_cache = {"items": None, "fetched_at": 0.0}


def _parse_json_detail(detail):
    if not detail:
        return None
    if isinstance(detail, dict):
        return detail
    try:
        return _json.loads(detail)
    except (TypeError, ValueError):
        return None


def _extract_latest_signal(trades, activities):
    for activity in activities:
        detail = _parse_json_detail(getattr(activity, "detail", None)) or {}
        recommendation = detail.get("recommendation")
        target_price = detail.get("target_price") or detail.get("ai_target_price")
        stop_loss_price = detail.get("stop_loss_price") or detail.get("ai_stop_loss_price")
        reason = detail.get("reason") or activity.summary
        if recommendation or target_price or stop_loss_price:
            return {
                "recommendation": recommendation or "",
                "confidence": getattr(activity, "confidence", None),
                "reason": reason,
                "target_price": target_price,
                "stop_loss_price": stop_loss_price,
                "llm_provider": getattr(activity, "llm_provider", None),
                "llm_tier": getattr(activity, "llm_tier", None),
                "created_at": getattr(activity, "created_at", None),
            }

    for trade in trades:
        if (
            getattr(trade, "ai_recommendation", "")
            or getattr(trade, "ai_target_price", None) is not None
            or getattr(trade, "ai_stop_loss_price", None) is not None
        ):
            return {
                "recommendation": getattr(trade, "ai_recommendation", ""),
                "confidence": getattr(trade, "ai_confidence", None),
                "reason": getattr(trade, "exit_reason", "") or getattr(trade, "strategy_type", ""),
                "target_price": getattr(trade, "ai_target_price", None),
                "stop_loss_price": getattr(trade, "ai_stop_loss_price", None),
                "llm_provider": None,
                "llm_tier": None,
                "created_at": getattr(trade, "created_at", None),
            }

    return None


def _build_position_timeline(trades, activities):
    timeline = []

    for trade in trades:
        trade_time = getattr(trade, "exit_at", None) or getattr(trade, "entry_at", None) or getattr(trade, "created_at", None)
        side = getattr(trade, "side", "")
        title = "매수 체결" if side == "BUY" else "매도 기록"
        summary = f"{getattr(trade, 'stock_name', getattr(trade, 'stock_symbol', ''))} · {getattr(trade, 'quantity', 0)}주"
        timeline.append({
            "type": "trade",
            "at": trade_time.isoformat() if trade_time else None,
            "title": title,
            "summary": summary,
            "side": side,
            "status": getattr(trade, "status", ""),
            "detail": {
                "strategy_type": getattr(trade, "strategy_type", ""),
                "entry_price": getattr(trade, "entry_price", 0.0),
                "exit_price": getattr(trade, "exit_price", 0.0),
                "pnl": getattr(trade, "pnl", 0.0),
                "return_pct": getattr(trade, "return_pct", 0.0),
                "exit_reason": getattr(trade, "exit_reason", ""),
            },
        })

    for activity in activities:
        timeline.append({
            "type": "activity",
            "at": getattr(activity, "created_at", None).isoformat() if getattr(activity, "created_at", None) else None,
            "title": getattr(activity, "activity_type", "EVENT"),
            "summary": getattr(activity, "summary", ""),
            "phase": getattr(activity, "phase", ""),
            "confidence": getattr(activity, "confidence", None),
            "detail": _parse_json_detail(getattr(activity, "detail", None)),
        })

    timeline.sort(key=lambda item: item.get("at") or "", reverse=True)
    return timeline


def _get_cached_holdings():
    items = _position_holdings_cache.get("items")
    fetched_at = float(_position_holdings_cache.get("fetched_at") or 0.0)
    if not items or (_time.monotonic() - fetched_at) > POSITION_DETAIL_HOLDING_CACHE_TTL_SEC:
        return None
    return items


async def _load_position_holdings():
    holdings = await asyncio.wait_for(
        get_broker_adapter().get_holdings(),
        timeout=POSITION_DETAIL_HOLDING_TIMEOUT_SEC,
    )
    _position_holdings_cache["items"] = holdings
    _position_holdings_cache["fetched_at"] = _time.monotonic()
    return holdings


# ── SSE 실시간 스트림 ──
@router.get("/stream")
async def sse_stream():
    """SSE 실시간 활동 스트림"""
    client_id, queue = sse_manager.connect()

    async def event_generator():
        try:
            yield f"data: {{\"type\": \"connected\", \"client_id\": \"{client_id}\"}}\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse_manager.disconnect(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 활동 목록 ──
@router.get("/activities", response_model=SuccessResponse[list[ActivityResponse]])
async def get_activities(
    target_date: str | None = Query(None, description="YYYY-MM-DD"),
    cycle_id: str | None = Query(None),
    activity_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """활동 로그 목록 조회"""
    repo = AgentActivityRepository(db)

    if cycle_id:
        activities = await repo.get_by_cycle(cycle_id)
    elif target_date:
        d = date.fromisoformat(target_date)
        activities = await repo.get_by_date(d, limit=limit, offset=offset)
    elif activity_type:
        activities = await repo.get_by_type(activity_type, limit=limit)
    else:
        from util.time_util import now_kst
        activities = await repo.get_by_date(now_kst().date(), limit=limit, offset=offset)

    return SuccessResponse(data=activities)


# ── 사이클 목록 ──
@router.get("/cycles", response_model=SuccessResponse[list[CycleResponse]])
async def get_cycles(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """최근 사이클 목록"""
    repo = AgentActivityRepository(db)
    cycles = await repo.get_recent_cycles(limit)
    return SuccessResponse(data=cycles)


# ── 사이클 타임라인 ──
@router.get("/cycles/{cycle_id}/timeline", response_model=SuccessResponse[list[ActivityResponse]])
async def get_cycle_timeline(
    cycle_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    """사이클 내 전체 활동 타임라인"""
    repo = AgentActivityRepository(db)
    activities = await repo.get_by_cycle(cycle_id)
    return SuccessResponse(data=activities)


# ── 일일 리포트 목록 ──
@router.get("/reports", response_model=SuccessResponse[list[DailyReportResponse]])
async def get_reports(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """일일 리포트 목록"""
    repo = DailyReportRepository(db)
    reports = await repo.get_reports(limit)
    return SuccessResponse(data=reports)


# ── 특정 날짜 리포트 ──
@router.get("/reports/latest", response_model=SuccessResponse[DailyReportResponse | None])
async def get_latest_report(db: AsyncSession = Depends(get_async_db)):
    """최신 리포트"""
    repo = DailyReportRepository(db)
    report = await repo.get_latest()
    return SuccessResponse(data=report)


@router.get("/reports/{report_date}", response_model=SuccessResponse[DailyReportResponse | None])
async def get_report_by_date(
    report_date: str,
    db: AsyncSession = Depends(get_async_db),
):
    """특정 날짜 리포트"""
    repo = DailyReportRepository(db)
    d = date.fromisoformat(report_date)
    report = await repo.get_by_date(d)
    return SuccessResponse(data=report)


# ── 매매 내역 ──
@router.get("/trades")
async def get_trades(
    target_date: str | None = Query(None, description="조회 날짜 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_async_db),
):
    """특정 날짜의 매매 내역 (매수 진입 + 청산 완료)"""
    from util.time_util import now_kst

    d = date.fromisoformat(target_date) if target_date else now_kst().date()
    repo = TradeResultRepository(db)

    # 오늘 진입한 매수
    opened = await repo.get_opened_by_date(d)
    # 오늘 청산된 포지션 (BUY 레코드, pnl 계산됨)
    completed = await repo.get_completed_by_date(d)
    # 오늘 체결 확인 대기
    pending_confirms = await repo.get_pending_confirms_by_date(d)
    # 미청산 포지션
    open_positions = await repo.get_all_open()

    return SuccessResponse(data={
        "date": str(d),
        "opened": [TradeResultResponse.model_validate(t) for t in opened],
        "completed": [TradeResultResponse.model_validate(t) for t in completed],
        "pending_confirms": [TradeResultResponse.model_validate(t) for t in pending_confirms],
        "open_positions": [TradeResultResponse.model_validate(t) for t in open_positions],
    })


@router.post("/trades/reconcile-pending")
async def reconcile_pending_trades():
    """PENDING_CONFIRM 거래를 수동으로 복구 시도"""
    summary = await portfolio_sync_job._recover_pending_confirms()
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        "🔄 PENDING_CONFIRM 수동 복구 실행",
        detail=summary,
    )
    message = (
        f"복구 완료 · 성공 {summary.get('recovered', 0)}건 / "
        f"보류 {summary.get('skipped', 0)}건 / 실패 {summary.get('failed', 0)}건"
    )
    return SuccessResponse(data=summary, message=message)


# ── 계좌 정보 ──
@router.get("/account/balance")
async def get_account_balance():
    """계좌 잔고 조회"""
    try:
        balance = await get_broker_adapter().get_balance()
        return SuccessResponse(data={
            "total_asset": balance.total_asset,
            "cash": balance.cash,
            "stock_value": balance.stock_value,
            "total_pnl": balance.total_pnl,
            "total_pnl_rate": balance.total_pnl_rate,
        })
    except Exception as e:
        logger.error("계좌 잔고 조회 실패: {}", str(e))
        return SuccessResponse(data=None, message=f"잔고 조회 실패: {str(e)[:100]}")


@router.get("/account/holdings")
async def get_account_holdings():
    """보유 종목 조회"""
    try:
        holdings = await get_broker_adapter().get_holdings()
        return SuccessResponse(data=[
            {
                "symbol": normalize_krx_symbol(getattr(h, "symbol", "")),
                "name": h.name,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
                "current_price": h.current_price,
                "pnl": h.pnl,
                "pnl_rate": h.pnl_rate,
            }
            for h in holdings
        ])
    except Exception as e:
        logger.error("보유 종목 조회 실패: {}", str(e))
        return SuccessResponse(data=[], message=f"보유 종목 조회 실패: {str(e)[:100]}")


@router.get("/account/pending-orders")
async def get_pending_orders():
    """미체결 주문 조회"""
    try:
        orders = await get_broker_adapter().get_pending_orders()
        return SuccessResponse(data=[
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "name": o.name,
                "side": o.side,
                "order_qty": o.order_qty,
                "filled_qty": o.filled_qty,
                "remaining_qty": o.remaining_qty,
                "order_price": o.order_price,
                "order_time": o.order_time,
            }
            for o in orders
        ])
    except Exception as e:
        logger.error("미체결 주문 조회 실패: {}", str(e))
        return SuccessResponse(data=[], message=f"미체결 주문 조회 실패: {str(e)[:100]}")


@router.get("/positions/{symbol}")
async def get_position_detail(
    symbol: str,
    timeline_limit: int = Query(20, ge=1, le=100),
    timeline_offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """보유/관심 종목 상세 요약 + 타임라인"""
    normalized_symbol = normalize_krx_symbol(symbol)
    trade_repo = TradeResultRepository(db)
    activity_repo = AgentActivityRepository(db)

    source_fetch_limit = timeline_limit + timeline_offset + 1
    trades = await trade_repo.get_by_symbol(normalized_symbol, limit=source_fetch_limit)
    activities = await activity_repo.get_by_symbol(normalized_symbol, limit=source_fetch_limit)
    open_buys = await trade_repo.get_all_open_buys(normalized_symbol)

    holding_payload = None
    holding_status = "unavailable"
    holding_message = "실시간 보유 정보 없음"
    try:
        holdings = await _load_position_holdings()
        for holding in holdings:
            if normalize_krx_symbol(getattr(holding, "symbol", "")) == normalized_symbol:
                current_price = float(getattr(holding, "current_price", 0.0) or 0.0)
                quantity = int(getattr(holding, "quantity", 0) or 0)
                holding_payload = {
                    "symbol": normalized_symbol,
                    "name": getattr(holding, "name", normalized_symbol),
                    "quantity": quantity,
                    "avg_buy_price": float(getattr(holding, "avg_buy_price", 0.0) or 0.0),
                    "current_price": current_price,
                    "pnl": float(getattr(holding, "pnl", 0.0) or 0.0),
                    "pnl_rate": float(getattr(holding, "pnl_rate", 0.0) or 0.0),
                    "market_value": current_price * quantity,
                }
                holding_status = "ok"
                holding_message = ""
                break
        if holding_payload is None and holdings is not None:
            holding_status = "missing"
            holding_message = "실시간 보유 목록에는 현재 보이지 않습니다."
    except asyncio.TimeoutError:
        holdings = _get_cached_holdings()
        if holdings:
            for holding in holdings:
                if normalize_krx_symbol(getattr(holding, "symbol", "")) == normalized_symbol:
                    current_price = float(getattr(holding, "current_price", 0.0) or 0.0)
                    quantity = int(getattr(holding, "quantity", 0) or 0)
                    holding_payload = {
                        "symbol": normalized_symbol,
                        "name": getattr(holding, "name", normalized_symbol),
                        "quantity": quantity,
                        "avg_buy_price": float(getattr(holding, "avg_buy_price", 0.0) or 0.0),
                        "current_price": current_price,
                        "pnl": float(getattr(holding, "pnl", 0.0) or 0.0),
                        "pnl_rate": float(getattr(holding, "pnl_rate", 0.0) or 0.0),
                        "market_value": current_price * quantity,
                    }
                    break
            if holding_payload:
                holding_status = "cached"
                holding_message = "최근 캐시된 보유 정보를 표시합니다."
            else:
                holding_status = "timeout"
                holding_message = "실시간 보유 정보 조회가 지연되어 최근 거래 이력만 표시합니다."
        else:
            holding_status = "timeout"
            holding_message = "실시간 보유 정보 조회가 지연되어 최근 거래 이력만 표시합니다."
    except Exception as exc:
        logger.warning("종목 상세 보유 정보 조회 실패 ({}): {}", normalized_symbol, str(exc))
        holding_status = "error"
        holding_message = f"실시간 보유 정보 조회 실패: {str(exc)[:80]}"

    latest_signal = _extract_latest_signal(trades, activities)
    name = (
        (holding_payload or {}).get("name")
        or (getattr(trades[0], "stock_name", None) if trades else None)
        or normalized_symbol
    )
    realized_pnl = sum(
        float(getattr(trade, "pnl", 0.0) or 0.0)
        for trade in trades
        if getattr(trade, "exit_at", None) is not None
    )

    full_timeline = _build_position_timeline(trades, activities)
    timeline_slice = full_timeline[timeline_offset: timeline_offset + timeline_limit]
    has_more_timeline = len(full_timeline) > (timeline_offset + timeline_limit)

    return SuccessResponse(data={
        "symbol": normalized_symbol,
        "name": name,
        "summary": {
            "holding": holding_payload,
            "holding_status": holding_status,
            "holding_message": holding_message,
            "latest_signal": latest_signal,
            "trade_stats": {
                "total_trades": len(trades),
                "open_buy_count": len(open_buys),
                "completed_count": sum(1 for trade in trades if getattr(trade, "exit_at", None) is not None),
                "realized_pnl": realized_pnl,
            },
            "settings_shortcut_tab": "strategy",
        },
        "timeline": timeline_slice,
        "timeline_page": {
            "limit": timeline_limit,
            "offset": timeline_offset,
            "returned": len(timeline_slice),
            "has_more": has_more_timeline,
            "next_offset": timeline_offset + len(timeline_slice),
        },
    })


# ── 설정 조회/변경 ──
MUTABLE_SETTINGS = [
    "TRADING_ENABLED", "AUTONOMY_MODE",
    "RECOMMENDATION_EXPIRE_MIN",
    "SCHEDULER_ENABLED",
    "RISK_APPETITE",
    "LLM_PROVIDER_TIER1",
    "LLM_PROVIDER_TIER2",
    "LLM_FALLBACK_PROVIDER_TIER1",
    "LLM_FALLBACK_PROVIDER_TIER2",
    "LLM_FALLBACK_MODEL_TIER1",
    "LLM_FALLBACK_MODEL_TIER2",
    "CLAUDE_CODE_MODEL",
    "CLAUDE_CODE_MODEL_TIER1",
    "CLAUDE_CODE_MODEL_TIER2",
    "CODEX_MODEL",
    "CODEX_MODEL_TIER1",
    "CODEX_MODEL_TIER2",
    "MANUAL_LLM_PROVIDER",
]


@router.get("/settings")
async def get_settings():
    """런타임 설정 조회"""
    data = {}
    for key in MUTABLE_SETTINGS:
        data[key] = getattr(settings, key, None)
    data["strategy_insights"] = build_strategy_insights(settings.RISK_APPETITE)
    return SuccessResponse(data=data)


@router.put("/settings")
async def update_settings(updates: dict):
    """런타임 설정 변경 (재시작 불필요)"""
    changed = {}
    for key, value in updates.items():
        if key not in MUTABLE_SETTINGS:
            continue
        old = getattr(settings, key, None)
        # 타입 변환
        if isinstance(old, bool):
            value = str(value).lower() in ("true", "1", "yes")
        elif isinstance(old, int):
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{key} must be an integer") from exc
        elif isinstance(old, float):
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc
        elif key in {
            "LLM_PROVIDER_TIER1",
            "LLM_PROVIDER_TIER2",
            "LLM_FALLBACK_PROVIDER_TIER1",
            "LLM_FALLBACK_PROVIDER_TIER2",
        }:
            value = str(value).upper()
            if key.startswith("LLM_FALLBACK_PROVIDER_") and value in {"", "NONE"}:
                value = ""
            elif value not in {"CLAUDE_CODE", "CODEX"}:
                continue
        elif key == "MANUAL_LLM_PROVIDER":
            value = str(value).upper()
            if value not in {"AUTOMATIC", "CLAUDE_CODE", "CODEX"}:
                continue
        elif key in {
            "LLM_FALLBACK_MODEL_TIER1",
            "LLM_FALLBACK_MODEL_TIER2",
            "CLAUDE_CODE_MODEL",
            "CLAUDE_CODE_MODEL_TIER1",
            "CLAUDE_CODE_MODEL_TIER2",
            "CODEX_MODEL",
            "CODEX_MODEL_TIER1",
            "CODEX_MODEL_TIER2",
        }:
            value = normalize_llm_model_value(str(value))
        setattr(settings, key, value)
        changed[key] = {"old": old, "new": value}
        logger.info("설정 변경: {} = {} → {}", key, old, value)

    if changed:
        await activity_logger.log(
            ActivityType.EVENT, ActivityPhase.PROGRESS,
            f"\u2699\ufe0f 설정 변경: {', '.join(changed.keys())}",
            detail=changed,
        )

    return SuccessResponse(data=changed, message=f"{len(changed)}개 설정 변경됨")


# ── Claude Code 사용량 ──
@router.get("/llm/usage")
async def get_llm_usage():
    """Claude Code / Codex 사용량 및 로그인 상태"""
    try:
        return SuccessResponse(data=await llm_usage_service.get_snapshot())
    except Exception as e:
        logger.error("LLM 사용량 조회 실패: {}", str(e))
        return SuccessResponse(data=None, message=f"조회 실패: {str(e)[:100]}")


# ── LLM 상태 ──
@router.get("/llm/status")
async def get_llm_status():
    """LLM 프로바이더 상태 및 설정 조회"""
    from analysis.llm.llm_factory import llm_factory
    return SuccessResponse(data=llm_factory.get_llm_status())


@router.get("/llm/catalog")
async def get_llm_catalog(
    force_refresh: bool = Query(False, description="공식 모델 카탈로그 강제 동기화"),
):
    """공식 문서 기반 LLM 모델 카탈로그"""
    try:
        return SuccessResponse(data=await model_catalog_service.get_catalog(force_refresh=force_refresh))
    except Exception as exc:
        logger.error("LLM 카탈로그 조회 실패: {}", str(exc))
        return SuccessResponse(
            data=model_catalog_service.fallback_catalog(str(exc)),
            message="LLM catalog fallback returned after upstream failure",
        )


# ── 시스템 상태 ──
@router.get("/system/status")
async def get_system_status():
    """시스템 전체 상태"""
    from agent.trading_agent import trading_agent

    from scheduler.market_calendar import market_calendar

    return SuccessResponse(data={
        "broker_provider": settings.BROKER_PROVIDER.upper(),
        "mcp_required": settings.BROKER_PROVIDER.upper() == "KIS",
        "trading_enabled": settings.TRADING_ENABLED,
        "autonomy_mode": settings.AUTONOMY_MODE,
        "mcp_connected": mcp_client.is_connected,
        "scheduler_running": trading_scheduler.is_running,
        "agent_running": trading_agent._running,
        "last_cycle_time": trading_agent.last_cycle_time.isoformat() if trading_agent.last_cycle_time else None,
        "sse_clients": sse_manager.client_count,
        "environment": settings.ENVIRONMENT,
        "market_open": market_calendar.is_krx_trading_hours(),
        "market_holiday": market_calendar.get_holiday_name(),
        "next_market_open": market_calendar.next_krx_open().strftime("%m/%d %H:%M"),
    })


@router.post("/mcp/reconnect")
async def reconnect_mcp():
    """런타임 MCP 연결 재시도"""
    connected = await mcp_client.ensure_connected(force_reconnect=True)
    detail = {
        "connected": connected,
        "mcp_connected": mcp_client.is_connected,
    }
    await activity_logger.log(
        ActivityType.EVENT, ActivityPhase.PROGRESS,
        "🔌 MCP 재연결 요청",
        detail=detail,
    )
    return SuccessResponse(
        data=detail,
        message="MCP 재연결 성공" if connected else "MCP 재연결 실패",
    )


@router.post("/scheduler/start")
async def start_scheduler():
    """런타임 스케줄러 시작"""
    settings.SCHEDULER_ENABLED = True
    await trading_scheduler.start()
    await activity_logger.log(
        ActivityType.EVENT, ActivityPhase.PROGRESS,
        "⏯️ 스케줄러 시작 요청",
        detail={"enabled": settings.SCHEDULER_ENABLED, "running": trading_scheduler.is_running},
    )
    return SuccessResponse(
        data={"enabled": settings.SCHEDULER_ENABLED, "running": trading_scheduler.is_running},
        message="스케줄러 시작",
    )


@router.post("/scheduler/stop")
async def stop_scheduler():
    """런타임 스케줄러 중지"""
    settings.SCHEDULER_ENABLED = False
    await trading_scheduler.stop()
    await activity_logger.log(
        ActivityType.EVENT, ActivityPhase.PROGRESS,
        "⏸️ 스케줄러 중지 요청",
        detail={"enabled": settings.SCHEDULER_ENABLED, "running": trading_scheduler.is_running},
    )
    return SuccessResponse(
        data={"enabled": settings.SCHEDULER_ENABLED, "running": trading_scheduler.is_running},
        message="스케줄러 중지",
    )


# ── 수동 사이클 트리거 ──
@router.post("/agent/trigger")
async def trigger_agent_cycle():
    """수동으로 에이전트 사이클 실행"""
    from agent.trading_agent import trading_agent

    await activity_logger.log(
        ActivityType.EVENT, ActivityPhase.PROGRESS,
        "\U0001f3ae 수동 사이클 트리거 (관리자)",
    )

    # 비동기로 실행 (즉시 응답)
    manual_provider_override = settings.MANUAL_LLM_PROVIDER
    asyncio.create_task(
        trading_agent.run_cycle(manual_provider_override=manual_provider_override)
    )
    return SuccessResponse(message="에이전트 사이클이 트리거되었습니다")


# ── 수동 일일 리포트 생성 ──
@router.post("/reports/generate")
async def generate_report(target_date: str | None = Query(None)):
    """수동 일일 리포트 생성"""
    from services.daily_report_service import daily_report_service
    d = date.fromisoformat(target_date) if target_date else None
    report = await daily_report_service.generate_daily_report(
        d,
        manual_provider_override=settings.MANUAL_LLM_PROVIDER,
    )
    if report:
        return SuccessResponse(
            data=DailyReportResponse.model_validate(report),
            message="리포트 생성 완료",
        )
    return SuccessResponse(message="리포트 생성 실패 또는 이미 존재")


# ── Q&A: 분석 결과에 대한 질문 ──
@router.post("/qa/ask", response_model=SuccessResponse[QAResponse])
async def ask_question(
    req: QARequest,
    db: AsyncSession = Depends(get_async_db),
):
    """활동 기록 기반 Q&A — LLM(Tier1)으로 답변"""
    start = _time.time()
    repo = AgentActivityRepository(db)

    # 1. 컨텍스트 결정: cycle_id → symbol → 오늘 전체
    if req.cycle_id:
        activities = await repo.get_by_cycle(req.cycle_id)
        context_label = f"사이클 {req.cycle_id[:8]}"
    elif req.symbol:
        activities = await repo.get_by_symbol(req.symbol, limit=50)
        context_label = f"종목 {req.symbol}"
    else:
        from util.time_util import now_kst
        activities = await repo.get_by_date(now_kst().date(), limit=100)
        context_label = "오늘 전체"

    # 2. 핵심 필드 추출 (프롬프트에 전달할 컨텍스트)
    context_lines = []
    for a in activities[-80:]:  # 최근 80건 (역순 → 시간순)
        line = f"[{a.activity_type}/{a.phase}] {a.summary}"
        if a.symbol:
            line = f"[{a.symbol}] " + line
        if a.confidence is not None:
            line += f" (확신도: {a.confidence:.0%})"
        # detail에서 recommendation, reason 추출
        if a.detail:
            try:
                detail = _json.loads(a.detail) if isinstance(a.detail, str) else a.detail
                for key in ("recommendation", "reason", "signal", "action", "exit_reason"):
                    if key in detail:
                        line += f" | {key}: {detail[key]}"
            except (ValueError, TypeError):
                pass
        context_lines.append(line)

    context_text = "\n".join(context_lines) if context_lines else "(활동 기록 없음)"

    # 2.5 포트폴리오 실시간 컨텍스트
    portfolio_text = ""
    try:
        balance, holdings = await account_manager.get_account_snapshot()
        parts = []
        if balance.is_valid:
            parts.append(
                f"총자산: {balance.total_asset:,.0f}원 | 현금: {balance.cash:,.0f}원 | "
                f"주식평가: {balance.stock_value:,.0f}원 | 총손익: {balance.total_pnl:+,.0f}원 ({balance.total_pnl_rate:+.2f}%)"
            )
        if holdings:
            parts.append(f"보유 {len(holdings)}종목:")
            for h in holdings:
                parts.append(f"- {h.name}({h.symbol}) {h.quantity}주 평균단가:{h.avg_buy_price:,.0f} 현재가:{h.current_price:,.0f} 수익률:{h.pnl_rate:+.2f}%")
        else:
            parts.append("보유 종목 없음")
        portfolio_text = "\n".join(parts)
    except Exception as e:
        logger.warning("Q&A 포트폴리오 조회 실패: {}", str(e))
        portfolio_text = "(포트폴리오 조회 실패)"

    has_portfolio = bool(portfolio_text and "조회 실패" not in portfolio_text)
    context_summary = f"{context_label} — {len(activities)}건의 활동 기록"
    if has_portfolio:
        context_summary += " + 포트폴리오"

    # 3. LLM 호출 (Tier1, 속도 우선)
    from analysis.llm.llm_factory import llm_factory

    system_prompt = (
        "너는 AI 트레이딩 시스템의 운영 어시스턴트다. "
        "아래 포트폴리오 현황과 활동 기록을 바탕으로 사용자의 질문에 간결하고 정확하게 답변해라. "
        "추측하지 말고, 제공된 데이터에 근거한 답변만 해라. "
        "한국어로 답변하되, 핵심만 2-3문단 이내로."
    )
    prompt = (
        f"## 포트폴리오 현황 (실시간)\n{portfolio_text}\n\n"
        f"## 활동 기록 ({context_summary})\n{context_text}\n\n"
        f"## 질문\n{req.question}"
    )

    try:
        answer, provider = await llm_factory.generate_manual(
            prompt,
            system_prompt,
            default_tier=LLMTier.TIER1,
            manual_provider_override=settings.MANUAL_LLM_PROVIDER,
        )
    except Exception as e:
        logger.error("Q&A LLM 호출 실패: {}", str(e))
        answer = f"LLM 호출에 실패했습니다: {str(e)[:100]}"
        provider = "error"

    elapsed_ms = int((_time.time() - start) * 1000)

    # 4. 활동 로그 기록
    await activity_logger.log(
        ActivityType.QA, ActivityPhase.COMPLETE,
        f"Q&A: {req.question[:80]}",
        detail={
            "question": req.question,
            "answer": answer[:1000],
            "context_summary": context_summary,
            "llm_provider": provider,
        },
        execution_time_ms=elapsed_ms,
    )

    return SuccessResponse(data=QAResponse(
        question=req.question,
        answer=answer,
        context_summary=context_summary,
        llm_provider=provider,
        execution_time_ms=elapsed_ms,
    ))
