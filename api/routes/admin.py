"""관리자 대시보드 API — SSE 스트림 + 활동 조회 + 설정 + 리포트 + 계좌 + Q&A"""
import asyncio
import json as _json
import time as _time
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from admin.sse_manager import sse_manager
from analysis.llm.model_catalog import model_catalog_service
from core.config import settings
from core.database import AsyncSessionLocal, get_async_db, get_async_db_with_transaction
from core.runtime_settings import MUTABLE_SETTINGS
from exceptions.common import ServiceException
from models.agent_activity import AgentActivityLog
from models.analysis import AnalysisResult
from models.daily_report import DailyReport
from models.news_item import NewsItem
from models.order import Order
from models.recommendation import Recommendation
from models.trade_result import TradeResult
from repositories.agent_activity_repository import AgentActivityRepository
from repositories.daily_report_repository import DailyReportRepository
from repositories.news_item_repository import NewsItemRepository
from repositories.trade_result_repository import TradeResultRepository
from realtime.event_detector import event_detector
from schemas.activity_schema import ActivityResponse, CycleResponse
from schemas.common import SuccessResponse
from schemas.daily_report_schema import DailyReportResponse, ReportTradeComparisonResponse
from schemas.feedback_schema import TradeResultResponse
from schemas.news_schema import NewsBatchIngestRequest
from schemas.qa_schema import QARequest, QAResponse
from scheduler.jobs import portfolio_sync_job
from services.activity_logger import activity_logger
from services.bloomberg_news_service import bloomberg_news_service
from services.cnbc_news_service import cnbc_news_service
from services.investing_news_service import investing_news_service
from services.krx_kind_disclosure_service import krx_kind_disclosure_service
from services.llm_usage_service import llm_usage_service
from services.manual_trade_service import manual_trade_service
from services.nasdaq_news_service import nasdaq_news_service
from services.news_ingest_service import news_ingest_service
from services.open_dart_disclosure_service import open_dart_disclosure_service
from services.news_reporting_service import news_reporting_service
from services.news_runtime_service import news_runtime_service
from services.performance_reporting_service import performance_reporting_service
from services.runtime_settings_service import runtime_settings_service
from services.seeking_alpha_news_service import seeking_alpha_news_service
from services.yonhap_news_service import yonhap_news_service
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


def _coerce_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_contributors(value):
    contributors = []
    if not isinstance(value, list):
        return contributors
    for item in value[:3]:
        if isinstance(item, dict):
            headline = str(item.get("headline") or "").strip()
            if not headline:
                continue
            contributors.append({
                "headline": headline,
                "pressure": _coerce_float(item.get("pressure")),
                "source_code": str(item.get("source_code") or "").upper() or None,
            })
        elif isinstance(item, str) and item.strip():
            contributors.append({
                "headline": item.strip(),
                "pressure": None,
                "source_code": None,
            })
    return contributors


def _build_decision_insight(trades, activities, latest_signal):
    latest_buy_trade = next(
        (trade for trade in trades if str(getattr(trade, "side", "")).upper() == "BUY"),
        trades[0] if trades else None,
    )
    if not latest_signal and not latest_buy_trade:
        return None

    notes = _parse_json_detail(getattr(latest_buy_trade, "notes", None)) or {}
    edge_bps = _coerce_float(notes.get("estimated_edge_bps"))
    cost_bps = _coerce_float(notes.get("estimated_cost_bps"))
    ratio = _coerce_float(notes.get("edge_to_cost_ratio"))
    if ratio is None and edge_bps is not None and cost_bps not in (None, 0):
        ratio = round(edge_bps / cost_bps, 2)

    recommendation = (latest_signal or {}).get("recommendation") or getattr(latest_buy_trade, "ai_recommendation", "")
    confidence = (latest_signal or {}).get("confidence")
    if confidence is None:
        confidence = _coerce_float(getattr(latest_buy_trade, "ai_confidence", None))

    target_price = (latest_signal or {}).get("target_price")
    if target_price is None:
        target_price = _coerce_float(getattr(latest_buy_trade, "ai_target_price", None))

    stop_loss_price = (latest_signal or {}).get("stop_loss_price")
    if stop_loss_price is None:
        stop_loss_price = _coerce_float(getattr(latest_buy_trade, "ai_stop_loss_price", None))

    reason = (latest_signal or {}).get("reason") or ""
    horizon = str(notes.get("trade_horizon") or "MID").upper()

    chart = {
        "market_regime": str(getattr(latest_buy_trade, "market_regime", "") or "").upper() or None,
        "rsi": _coerce_float(getattr(latest_buy_trade, "entry_rsi", None)),
        "macd_hist": _coerce_float(getattr(latest_buy_trade, "entry_macd_hist", None)),
        "pattern": str(notes.get("entry_pattern") or getattr(latest_buy_trade, "entry_pattern", "") or "").strip() or None,
        "direction": str(notes.get("chart_signal_direction") or "").upper() or None,
        "signal_confidence": _coerce_float(notes.get("chart_signal_confidence")),
    }

    cost = {
        "edge_bps": edge_bps,
        "cost_bps": cost_bps,
        "ratio": ratio,
        "min_ratio": _coerce_float(notes.get("cost_gate_ratio")),
    }

    news = {
        "negative_pressure": _coerce_float(notes.get("news_negative_pressure")),
        "negative_count": int(notes.get("news_negative_count") or 0),
        "source_count": int(notes.get("news_source_count") or 0),
        "threshold": _coerce_float(notes.get("news_threshold")),
        "contributors": _normalize_contributors(notes.get("news_top_contributors")),
    }

    has_chart = any(value is not None for value in chart.values())
    has_cost = any(value is not None for value in cost.values())
    has_news = (
        news["negative_pressure"] is not None
        or news["negative_count"] > 0
        or news["source_count"] > 0
        or bool(news["contributors"])
    )
    if not any([recommendation, has_chart, has_cost, has_news]):
        return None

    return {
        "recommendation": recommendation or "대기",
        "confidence": confidence,
        "reason": reason,
        "target_price": target_price,
        "stop_loss_price": stop_loss_price,
        "horizon": horizon,
        "chart": chart,
        "cost": cost,
        "news": news,
    }


def _build_position_timeline(trades, activities):
    timeline = []

    for trade in trades:
        notes = _parse_json_detail(getattr(trade, "notes", None)) or {}
        trade_time = getattr(trade, "exit_at", None) or getattr(trade, "entry_at", None) or getattr(trade, "created_at", None)
        side = getattr(trade, "side", "")
        status = str(getattr(trade, "status", "") or "").upper()
        fill_type = str(notes.get("fill_type") or "").upper()
        remaining_open_quantity = int(notes.get("remaining_open_quantity") or 0)
        has_exit = getattr(trade, "exit_at", None) is not None

        if side == "SELL":
            if status == "PENDING_CONFIRM":
                title = "매도 대기중"
                kind_label = "매도 대기중"
                badge = status or "SELL"
                tone = "pending"
                icon = "대기"
            elif fill_type == "PARTIAL_EXIT" or remaining_open_quantity > 0:
                title = "부분 매도"
                kind_label = "부분 매도"
                badge = fill_type or "PARTIAL_EXIT"
                tone = "sell"
                icon = "부분"
            else:
                title = "매도 완료"
                kind_label = "매도 완료"
                badge = status or "SELL"
                tone = "sell"
                icon = "매도"
        else:
            if status == "PENDING_CONFIRM":
                title = "매수 대기중"
                kind_label = "매수 대기중"
                badge = status or "BUY"
                tone = "pending"
                icon = "대기"
            elif has_exit and (fill_type == "PARTIAL_EXIT" or remaining_open_quantity > 0):
                title = "부분 매도"
                kind_label = "부분 매도"
                badge = fill_type or "PARTIAL_EXIT"
                tone = "sell"
                icon = "부분"
            elif has_exit:
                title = "최종 청산 lot"
                kind_label = "최종 청산 lot"
                badge = "FINAL_EXIT"
                tone = "sell"
                icon = "청산"
            else:
                title = "매수 완료"
                kind_label = "매수 완료"
                badge = status or "BUY"
                tone = "buy"
                icon = "매수"

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
                "notes": getattr(trade, "notes", None),
                "fill_type": fill_type,
                "remaining_open_quantity": remaining_open_quantity,
                "trade_state_kind_label": kind_label,
                "trade_state_badge": badge,
                "trade_state_tone": tone,
                "trade_state_icon": icon,
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


def _build_news_timeline_entries(news_items):
    timeline = []

    for item in news_items:
        serialized = news_ingest_service.serialize_item(item)
        published_at = getattr(item, "published_at", None) or getattr(item, "created_at", None)
        timeline.append({
            "type": "news",
            "at": published_at.isoformat() if published_at else None,
            "title": serialized.get("display_title") or serialized.get("title") or "뉴스",
            "summary": serialized.get("display_summary") or serialized.get("summary") or "",
            "detail": {
                "source_code": getattr(item, "source_code", "") or "",
                "source_name": getattr(item, "source_name", "") or "",
                "source_tier": getattr(item, "source_tier", "") or "",
                "region": getattr(item, "region", "") or "",
                "official": bool(getattr(item, "official", False)),
                "language": getattr(item, "language", "") or "",
                "url": getattr(item, "url", "") or "",
                "sentiment_label": getattr(item, "sentiment_label", "") or "",
                "sentiment_score": float(getattr(item, "sentiment_score", 0.0) or 0.0),
                "impact_score": float(getattr(item, "impact_score", 0.0) or 0.0),
                "trust_score": float(getattr(item, "trust_score", 0.0) or 0.0),
                "original_title": serialized.get("original_title") or "",
                "original_summary": serialized.get("original_summary") or "",
                "translation_provider": serialized.get("translation_provider") or "",
                "translation_status": serialized.get("translation_status") or "",
            },
        })

    return timeline


def _report_looks_empty(report) -> bool:
    return (
        int(getattr(report, "buy_count", 0) or 0) == 0
        and int(getattr(report, "sell_count", 0) or 0) == 0
        and float(getattr(report, "total_pnl", 0.0) or 0.0) == 0.0
        and int(getattr(report, "open_position_count", 0) or 0) == 0
    )


async def _build_report_response(report, trade_repo: TradeResultRepository, open_symbols_cache: set[str] | None = None):
    payload = DailyReportResponse.model_validate(report)
    report_date = getattr(report, "report_date", None)
    completed = []
    if report_date:
        completed = await trade_repo.get_completed_by_date(report_date)
    trade_comparison = ReportTradeComparisonResponse.model_validate(
        performance_reporting_service.build_trade_comparison_from_results(completed)
    )

    if not _report_looks_empty(report):
        return payload.model_copy(update={
            "trade_comparison": trade_comparison,
        })

    if not report_date:
        return payload.model_copy(update={
            "trade_comparison": trade_comparison,
        })

    opened = await trade_repo.get_opened_by_date(report_date)
    trade_has_data = bool(opened or completed)
    if not trade_has_data:
        return payload.model_copy(update={
            "trade_comparison": trade_comparison,
        })

    if open_symbols_cache is None:
        all_open = await trade_repo.get_all_open()
        open_symbols_cache = {
            str(getattr(item, "stock_symbol", "")).strip()
            for item in all_open
            if str(getattr(item, "stock_symbol", "")).strip()
        }

    buy_count = len(opened)
    sell_count = len(completed)
    win_count = sum(1 for item in completed if bool(getattr(item, "is_win", False)))
    loss_count = max(0, sell_count - win_count)
    total_pnl = sum(float(getattr(item, "pnl", 0.0) or 0.0) for item in completed)
    open_position_count = len(open_symbols_cache)

    return payload.model_copy(update={
        "buy_count": buy_count,
        "sell_count": sell_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "total_pnl": total_pnl,
        "open_position_count": open_position_count,
        "total_orders": max(int(getattr(report, "total_orders", 0) or 0), buy_count + sell_count),
        "trade_comparison": trade_comparison,
    })


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
    report_repo = DailyReportRepository(db)
    trade_repo = TradeResultRepository(db)
    reports = await report_repo.get_reports(limit)

    all_open = await trade_repo.get_all_open()
    open_symbols_cache = {
        str(getattr(item, "stock_symbol", "")).strip()
        for item in all_open
        if str(getattr(item, "stock_symbol", "")).strip()
    }
    normalized = [
        await _build_report_response(report, trade_repo, open_symbols_cache=open_symbols_cache)
        for report in reports
    ]
    return SuccessResponse(data=normalized)


# ── 특정 날짜 리포트 ──
@router.get("/reports/latest", response_model=SuccessResponse[DailyReportResponse | None])
async def get_latest_report(db: AsyncSession = Depends(get_async_db)):
    """최신 리포트"""
    report_repo = DailyReportRepository(db)
    trade_repo = TradeResultRepository(db)
    report = await report_repo.get_latest()
    if not report:
        return SuccessResponse(data=None)
    return SuccessResponse(data=await _build_report_response(report, trade_repo))


@router.get("/reports/{report_date}", response_model=SuccessResponse[DailyReportResponse | None])
async def get_report_by_date(
    report_date: str,
    db: AsyncSession = Depends(get_async_db),
):
    """특정 날짜 리포트"""
    report_repo = DailyReportRepository(db)
    trade_repo = TradeResultRepository(db)
    d = date.fromisoformat(report_date)
    report = await report_repo.get_by_date(d)
    if not report:
        return SuccessResponse(data=None)
    return SuccessResponse(data=await _build_report_response(report, trade_repo))


@router.get("/performance/summary")
async def get_performance_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    """수익 검증용 성과 요약 (전략/호라이즌/KPI/리스크차단)"""
    data = await performance_reporting_service.build_summary(db, days=days)
    return SuccessResponse(data=data)


@router.get("/performance/periodic")
async def get_performance_periodic(
    period: str = Query("weekly"),
    size: int = Query(8, ge=1, le=24),
    db: AsyncSession = Depends(get_async_db),
):
    """주간/월간 버킷 성과 요약"""
    normalized = period.lower()
    if normalized not in {"weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="period must be weekly or monthly")
    data = await performance_reporting_service.build_periodic_summary(
        db,
        period=normalized,
        size=size,
    )
    return SuccessResponse(data=data)


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


@router.post("/trades/reconcile-holdings")
async def reconcile_holdings_trades():
    """계좌 보유수량 기준으로 누락 BUY lot/0원 체결가를 복구 시도"""
    backfill = await portfolio_sync_job._backfill_missing_open_buys_from_holdings()
    repaired = await portfolio_sync_job._repair_confirmed_zero_entry_prices()
    summary = {
        "backfill": backfill,
        "repair": repaired,
    }
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        "🧩 보유수량 기반 TradeResult 정합성 복구 실행",
        detail=summary,
    )
    message = (
        f"정합성 복구 완료 · 백필 {backfill.get('backfilled', 0)}건 / "
        f"체결가 복구 {repaired.get('repaired', 0)}건"
    )
    return SuccessResponse(data=summary, message=message)


@router.post("/system/reset-operational-baseline")
async def reset_operational_baseline():
    """설정은 유지하고 운영 이력 DB를 초기화한 뒤 현재 보유 기준선으로 재구성"""
    deleted: dict[str, int] = {}
    models_to_clear = [
        ("recommendations", Recommendation),
        ("analysis_results", AnalysisResult),
        ("orders", Order),
        ("trade_results", TradeResult),
        ("daily_reports", DailyReport),
        ("agent_activity_logs", AgentActivityLog),
        ("news_items", NewsItem),
    ]

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for key, model in models_to_clear:
                result = await session.execute(delete(model))
                deleted[key] = int(result.rowcount or 0)

    account_manager.invalidate_cache()
    try:
        get_broker_adapter().invalidate_cache()
    except Exception:
        pass
    news_runtime_service.reset()

    backfill = await portfolio_sync_job._backfill_missing_open_buys_from_holdings()
    repair = await portfolio_sync_job._repair_confirmed_zero_entry_prices()

    summary = {
        "deleted": deleted,
        "backfill": backfill,
        "repair": repair,
        "preserved": {
            "runtime_settings": True,
            "stocks": True,
            "portfolios": True,
        },
    }
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.COMPLETE,
        "🧹 운영 데이터 초기화 및 기준선 리셋 실행",
        detail=summary,
    )
    message = (
        f"운영 DB 초기화 완료 · 거래 {deleted.get('trade_results', 0)}건 / "
        f"뉴스 {deleted.get('news_items', 0)}건 삭제, "
        f"보유 백필 {backfill.get('backfilled', 0)}건"
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


@router.post("/account/holdings/{symbol}/sell")
async def sell_account_holding(symbol: str):
    result = await manual_trade_service.sell_position(symbol)
    return SuccessResponse(data=result, message=f"{result['symbol']} 즉시 매도 주문 접수")


@router.post("/account/pending-orders/{order_id}/cancel-buy")
async def cancel_pending_buy_order(order_id: str):
    result = await manual_trade_service.cancel_pending_buy(order_id)
    return SuccessResponse(data=result, message="미체결 매수 주문 취소 완료")


@router.post("/account/pending-orders/{order_id}/cancel-and-sell")
async def cancel_pending_sell_and_resubmit(order_id: str):
    result = await manual_trade_service.replace_pending_sell_with_market_order(order_id)
    return SuccessResponse(data=result, message="취소 후 즉시 매도 주문 접수")


@router.get("/events/radar")
async def get_event_radar(
    limit: int = Query(8, ge=1, le=50),
):
    snapshot = event_detector.get_radar_snapshot()
    events = list(snapshot.get("events") or [])[:limit]
    return SuccessResponse(data={
        "summary": snapshot.get("summary") or {},
        "events": events,
    })


@router.get("/news/sources")
async def get_news_sources():
    """뉴스 수집 소스 카탈로그 및 LLM 운영 설정"""
    return SuccessResponse(data={
        "domestic_media_enabled": bool(settings.NEWS_DOMESTIC_MEDIA_ENABLED),
        "include_foreign": bool(settings.NEWS_INCLUDE_FOREIGN),
        "nasdaq_enabled": bool(settings.NEWS_NASDAQ_ENABLED),
        "llm": {
            "enabled": bool(settings.NEWS_LLM_ENABLED),
            "provider": settings.NEWS_LLM_PROVIDER,
        },
        "sources": news_ingest_service.get_source_catalog(
            include_foreign=bool(settings.NEWS_INCLUDE_FOREIGN)
        ),
    })


@router.get("/news/items")
async def get_news_items(
    symbol: str | None = Query(None),
    source_code: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """저장된 뉴스 아이템 조회"""
    items = await news_ingest_service.list_items(
        db,
        limit=limit,
        offset=offset,
        symbol=symbol,
        source_code=source_code,
    )
    return SuccessResponse(data=[news_ingest_service.serialize_item(item) for item in items])


@router.get("/news/overview")
async def get_news_overview(
    recent_limit: int = Query(5, ge=1, le=20),
    performance_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    data = await news_reporting_service.build_overview(
        db,
        recent_limit=recent_limit,
        performance_days=performance_days,
    )
    return SuccessResponse(data=data)


@router.post("/news/ingest")
async def ingest_news_items(
    req: NewsBatchIngestRequest,
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """수집기/운영 테스트용 뉴스 수동 적재"""
    summary = await news_ingest_service.ingest_items(
        db,
        [item.model_dump() for item in req.items],
    )
    return SuccessResponse(data=summary, message="뉴스 적재 완료")


@router.post("/news/fetch/dart")
async def fetch_dart_news(
    days: int = Query(1, ge=1, le=30),
    page_count: int = Query(50, ge=1, le=100),
    corp_code: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """OpenDART 공시를 수집해 news_items에 적재"""
    try:
        summary = await open_dart_disclosure_service.fetch_and_ingest(
            db,
            days=days,
            page_count=page_count,
            corp_code=corp_code,
        )
    except RuntimeError as exc:
        news_runtime_service.record_source_result(
            "DART",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise ServiceException.bad_request(str(exc)) from exc
    except Exception as exc:
        news_runtime_service.record_source_result(
            "DART",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "DART",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="신규 공시 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="OpenDART 뉴스 수집 완료")


@router.post("/news/fetch/krx")
async def fetch_krx_news(
    page_count: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """KIND 오늘의공시를 수집해 news_items에 적재"""
    try:
        summary = await krx_kind_disclosure_service.fetch_and_ingest(
            db,
            page_count=page_count,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "KRX",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "KRX",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="신규 KIND 공시 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="KIND 뉴스 수집 완료")


@router.post("/news/fetch/yonhap")
async def fetch_yonhap_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """연합뉴스TV 경제 RSS를 수집해 news_items에 적재"""
    try:
        summary = await yonhap_news_service.fetch_and_ingest(
            db,
            limit=limit,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "YONHAP",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "YONHAP",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="연합뉴스TV 경제 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="연합뉴스TV 뉴스 수집 완료")


@router.post("/news/fetch/bloomberg")
async def fetch_bloomberg_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """Bloomberg sitemap 뉴스를 수집해 news_items에 적재"""
    try:
        summary = await bloomberg_news_service.fetch_and_ingest(
            db=db,
            limit=limit,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "BLOOMBERG",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "BLOOMBERG",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="Bloomberg 해외 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="Bloomberg 뉴스 수집 완료")


@router.post("/news/fetch/cnbc")
async def fetch_cnbc_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """CNBC Markets RSS 뉴스를 수집해 news_items에 적재"""
    try:
        summary = await cnbc_news_service.fetch_and_ingest(
            db=db,
            limit=limit,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "CNBC",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "CNBC",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="CNBC 해외 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="CNBC 뉴스 수집 완료")


@router.post("/news/fetch/nasdaq")
async def fetch_nasdaq_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """Nasdaq Markets RSS 뉴스를 수집해 news_items에 적재"""
    try:
        summary = await nasdaq_news_service.fetch_and_ingest(
            db=db,
            limit=limit,
        )
    except RuntimeError as exc:
        news_runtime_service.record_source_result(
            "NASDAQ",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        return JSONResponse(
            status_code=502,
            content={
                "result": "ERROR",
                "data": {},
                "message": str(exc),
            },
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "NASDAQ",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "NASDAQ",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="Nasdaq 해외 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="Nasdaq 뉴스 수집 완료")


@router.post("/news/fetch/investing")
async def fetch_investing_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """Investing.com Stock Market News RSS를 수집해 news_items에 적재"""
    try:
        summary = await investing_news_service.fetch_and_ingest(
            db=db,
            limit=limit,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "INVESTING",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "INVESTING",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="Investing.com 해외 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="Investing.com 뉴스 수집 완료")


@router.post("/news/fetch/seeking-alpha")
async def fetch_seeking_alpha_news(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """Seeking Alpha All News RSS를 수집해 news_items에 적재"""
    try:
        summary = await seeking_alpha_news_service.fetch_and_ingest(
            db=db,
            limit=limit,
        )
    except Exception as exc:
        news_runtime_service.record_source_result(
            "SEEKING_ALPHA",
            status="ERROR",
            mode="MANUAL",
            message=str(exc),
        )
        raise

    news_runtime_service.record_source_result(
        "SEEKING_ALPHA",
        status="SUCCESS" if summary.get("received") else "EMPTY",
        mode="MANUAL",
        message="Seeking Alpha 해외 뉴스 적재 완료" if summary.get("created") else "조회된 데이터 없음",
        counts=summary,
    )
    return SuccessResponse(data=summary, message="Seeking Alpha 뉴스 수집 완료")


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
    news_repo = NewsItemRepository(db)

    source_fetch_limit = timeline_limit + timeline_offset + 1
    trades = await trade_repo.get_by_symbol(normalized_symbol, limit=source_fetch_limit)
    activities = await activity_repo.get_by_symbol(normalized_symbol, limit=source_fetch_limit)
    try:
        news_items = await news_repo.get_recent(
            limit=source_fetch_limit,
            offset=0,
            symbol=normalized_symbol,
        )
    except OperationalError as exc:
        logger.debug("종목 상세 뉴스 조회 생략 ({}): {}", normalized_symbol, str(getattr(exc, "orig", exc)))
        news_items = []
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
    decision_insight = _build_decision_insight(trades, activities, latest_signal)
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

    full_timeline = _build_position_timeline(trades, activities) + _build_news_timeline_entries(news_items)
    full_timeline.sort(key=lambda item: item.get("at") or "", reverse=True)
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
            "decision_insight": decision_insight,
            "trade_stats": {
                "total_trades": len(trades),
                "open_buy_count": len(open_buys),
                "completed_count": sum(1 for trade in trades if getattr(trade, "exit_at", None) is not None),
                "realized_pnl": realized_pnl,
            },
            "recent_events": [
                item for item in (event_detector.get_radar_snapshot().get("events") or [])
                if item.get("symbol") == normalized_symbol
            ][:3],
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
    changed = await runtime_settings_service.update_settings(updates)

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
async def get_system_status(db: AsyncSession = Depends(get_async_db)):
    """시스템 전체 상태"""
    from agent.trading_agent import trading_agent

    from scheduler.market_calendar import market_calendar

    broker_provider = settings.BROKER_PROVIDER.upper()
    mcp_required = broker_provider == "KIS"
    mcp_connected = mcp_client.is_connected
    activity_repo = AgentActivityRepository(db)
    latest_order_error = await activity_repo.get_latest_error(activity_type=ActivityType.ORDER)
    news_runtime = news_runtime_service.get_snapshot(
        include_foreign=bool(settings.NEWS_INCLUDE_FOREIGN)
    )
    news_overall = news_runtime.get("overall") or {}
    news_sources = news_runtime.get("sources") or {}
    news_error_sources = [
        code for code, state in news_sources.items()
        if str((state or {}).get("status") or "").upper() == "ERROR"
    ]

    if not mcp_required:
        broker_ops = {
            "status": "OK",
            "label": "브로커 정상",
            "message": f"{broker_provider}는 MCP 없이 직접 연동합니다.",
        }
    elif mcp_connected:
        broker_ops = {
            "status": "OK",
            "label": "브로커 정상",
            "message": "MCP 연결이 살아 있어 브로커 호출 준비가 되어 있습니다.",
        }
    else:
        broker_ops = {
            "status": "ERROR",
            "label": "브로커 확인 필요",
            "message": "KIS MCP 연결이 끊겨 있어 브로커 호출이 실패할 수 있습니다.",
        }

    news_last_status = str(news_overall.get("last_status") or "IDLE").upper()
    if news_error_sources:
        news_ops = {
            "status": "ERROR",
            "label": "뉴스 폴링 오류",
            "message": f"오류 소스 {len(news_error_sources)}개: {', '.join(news_error_sources[:3])}",
            "last_run_at": news_overall.get("last_run_at"),
        }
    elif news_last_status == "ERROR":
        news_ops = {
            "status": "ERROR",
            "label": "뉴스 폴링 오류",
            "message": str(news_overall.get("last_message") or "최근 뉴스 수집이 실패했습니다."),
            "last_run_at": news_overall.get("last_run_at"),
        }
    elif not settings.NEWS_POLL_ENABLED:
        news_ops = {
            "status": "WARN",
            "label": "뉴스 폴링 꺼짐",
            "message": "자동 뉴스 폴링이 비활성화되어 수동 수집만 동작합니다.",
            "last_run_at": news_overall.get("last_run_at"),
        }
    elif news_overall.get("last_run_at"):
        news_ops = {
            "status": "OK",
            "label": "뉴스 폴링 정상",
            "message": str(news_overall.get("last_message") or "최근 폴링 기록이 있습니다."),
            "last_run_at": news_overall.get("last_run_at"),
        }
    else:
        news_ops = {
            "status": "WARN",
            "label": "뉴스 폴링 대기",
            "message": "아직 자동 뉴스 수집 이력이 없습니다.",
            "last_run_at": None,
        }

    if latest_order_error is not None:
        order_ops = {
            "status": "WARN",
            "label": "최근 주문 오류",
            "message": latest_order_error.error_message or latest_order_error.summary,
            "symbol": latest_order_error.symbol,
            "created_at": latest_order_error.created_at.isoformat() if latest_order_error.created_at else None,
        }
    else:
        order_ops = {
            "status": "OK",
            "label": "주문 오류 없음",
            "message": "최근 주문 오류 로그가 없습니다.",
            "symbol": None,
            "created_at": None,
        }

    return SuccessResponse(data={
        "broker_provider": broker_provider,
        "mcp_required": mcp_required,
        "trading_enabled": settings.TRADING_ENABLED,
        "autonomy_mode": settings.AUTONOMY_MODE,
        "mcp_connected": mcp_connected,
        "scheduler_running": trading_scheduler.is_running,
        "agent_running": trading_agent._running,
        "last_cycle_time": trading_agent.last_cycle_time.isoformat() if trading_agent.last_cycle_time else None,
        "sse_clients": sse_manager.client_count,
        "environment": settings.ENVIRONMENT,
        "market_open": market_calendar.is_krx_trading_hours(),
        "market_holiday": market_calendar.get_holiday_name(),
        "next_market_open": market_calendar.next_krx_open().strftime("%m/%d %H:%M"),
        "operations": {
            "broker": broker_ops,
            "news_polling": news_ops,
            "orders": order_ops,
        },
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
    await runtime_settings_service.update_settings({"SCHEDULER_ENABLED": True})
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
    await runtime_settings_service.update_settings({"SCHEDULER_ENABLED": False})
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
async def generate_report(
    target_date: str | None = Query(None),
    force: bool = Query(False, description="기존 리포트가 있어도 재생성"),
):
    """수동 일일 리포트 생성"""
    from services.daily_report_service import daily_report_service
    d = date.fromisoformat(target_date) if target_date else None
    report = await daily_report_service.generate_daily_report(
        d,
        manual_provider_override=settings.MANUAL_LLM_PROVIDER,
        force_regenerate=force,
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
