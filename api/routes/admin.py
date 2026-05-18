"""관리자 대시보드 API — SSE 스트림 + 활동 조회 + 설정 + 리포트 + 계좌 + Q&A"""
import asyncio
import json as _json
import time as _time
from datetime import date, datetime, time
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from admin.sse_manager import sse_manager
from analysis.llm.model_catalog import model_catalog_service
from analysis.llm.ollama_provider import OllamaProvider
from core.config import settings
from core.database import AsyncSessionLocal, get_async_db, get_async_db_with_transaction
from core.order_submission import effective_order_submission_mode, runtime_order_override_active
from core.runtime_settings import MUTABLE_SETTINGS
from exceptions.common import ServiceException
from models.account_day_baseline import AccountDayBaseline
from models.account_equity_snapshot import AccountEquitySnapshot
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
from repositories.runtime_setting_repository import RuntimeSettingRepository
from repositories.trade_result_repository import TradeResultRepository
from realtime.event_detector import event_detector
from realtime.stream_manager import stream_manager
from schemas.activity_schema import ActivityResponse, CycleResponse
from schemas.common import SuccessResponse
from schemas.daily_report_schema import DailyReportResponse, ReportTradeComparisonResponse
from schemas.feedback_schema import TradeResultResponse
from schemas.news_schema import NewsBatchIngestRequest
from schemas.observability_schema import ErrorIncidentUpdateRequest
from schemas.qa_schema import QARequest, QAResponse
from scheduler.jobs import portfolio_sync_job
from services.activity_logger import activity_logger
from services.bloomberg_news_service import bloomberg_news_service
from services.cnbc_news_service import cnbc_news_service
from services.broker_runtime_service import broker_runtime_service
from services.error_capture_service import error_capture_service
from services.investing_news_service import investing_news_service
from services.krx_kind_disclosure_service import krx_kind_disclosure_service
from services.llm_usage_service import llm_usage_service
from services.manual_trade_service import manual_trade_service
from services.nasdaq_news_service import nasdaq_news_service
from services.news_enrichment_backfill_service import news_enrichment_backfill_service
from services.news_ingest_service import news_ingest_service
from services.open_dart_disclosure_service import open_dart_disclosure_service
from services.news_reporting_service import news_reporting_service
from services.news_runtime_service import news_runtime_service
from services.order_reconciliation_service import order_reconciliation_service
from services.stale_pending_cleanup_service import stale_pending_cleanup_service
from services.stock_universe_bootstrap_service import stock_universe_bootstrap_service
from services.error_incident_service import error_incident_service
from services.decision_benchmark_service import decision_benchmark_service
from services.observability_reporting_service import observability_reporting_service
from services.performance_reporting_service import performance_reporting_service
from services.trade_close_reconciliation_service import trade_close_reconciliation_service
from services.trade_lifecycle_integrity_service import trade_lifecycle_integrity_service
from services.account_equity_service import account_equity_service, classify_account_snapshot_freshness
from services.admin_action_confirmation_service import admin_action_confirmation_service
from services.runtime_settings_service import runtime_settings_service
from services.runtime_reconfiguration_service import runtime_reconfiguration_service
from services.runtime_backup_service import runtime_backup_service
from services.seeking_alpha_news_service import seeking_alpha_news_service
from services.system_preflight_service import system_preflight_service
from services.yonhap_news_service import yonhap_news_service
from strategy.risk_appetite_insights import build_strategy_insights
from trading.account_manager import account_manager
from trading.broker_factory import get_broker_adapter
from trading.enums import ActivityPhase, ActivityType, LLMTier
from trading.symbols import normalize_krx_symbol
from util.time_util import ensure_kst
from scheduler.scheduler import trading_scheduler

router = APIRouter(prefix="/admin", tags=["admin"])
POSITION_DETAIL_HOLDING_TIMEOUT_SEC = 2.0
POSITION_DETAIL_HOLDING_CACHE_TTL_SEC = 15.0
ORDER_ERROR_RECENT_WINDOW_HOURS = 24
_position_holdings_cache = {"items": None, "fetched_at": 0.0}


class AdminActionConfirmationCreateRequest(BaseModel):
    action: str
    resource_id: str
    quantity: str | int | None = None


class AdminActionConfirmationVerifyRequest(BaseModel):
    confirmation_token: str | None = None


class LLMApiKeyUpdateRequest(BaseModel):
    provider: str
    api_key: str
    label: str | None = None
    enabled: bool = True
    confirmation_token: str | None = None


_RUNTIME_SETTINGS_CONFIRMATION_ACTION = "APPLY_RUNTIME_SETTINGS"
_RUNTIME_SETTINGS_CONFIRMATION_RESOURCE = "RUNTIME_SETTINGS"
_PROTECTED_RUNTIME_SETTING_KEYS = {
    "TRADING_ENABLED",
    "ORDER_SUBMISSION_MODE",
    "AUTONOMY_MODE",
    "ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED",
    "ADMIN_ACTION_CONFIRMATION_TTL_SEC",
    "POST_LIQUIDATION_BUY_BLOCK_ENABLED",
    "DAY_TRADING_ONLY",
    "SCHEDULER_ENABLED",
    "BUY_ORDER_EXECUTION_MODE",
    "BUY_SLIPPAGE_GUARD_BPS",
    "SELL_ORDER_CONFIRM_WAIT_SEC",
    "ORDER_CONFIRM_STATUS_TIMEOUT_SEC",
    "AUTO_RISK_KILL_SWITCH_ENABLED",
    "MAX_DAILY_DRAWDOWN_PCT",
    "ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE",
    "ACCOUNT_EQUITY_DRAWDOWN_BLOCK_BUY_PCT",
    "ACCOUNT_EQUITY_DRAWDOWN_KILL_SWITCH_PCT",
    "RISK_APPETITE",
    "RISK_PER_TRADE_PCT",
    "POSITION_EXIT_MANAGEMENT_ENABLED",
}
_PROTECTED_RUNTIME_SETTING_PREFIXES = (
    "BUY_ORDER_CONFIRM_WAIT_SEC_",
    "LOSS_STREAK_RECOVERY_",
    "MIN_STRATEGY_EXPECTANCY",
    "EXPECTANCY_",
    "STRATEGY_EXPECTANCY_",
    "NEGATIVE_EXPECTANCY_",
    "VOLATILITY_POSITION_SIZING_",
    "RISK_MULTIPLIER_",
    "FAST_HOLDINGS_GUARD_",
    "PARTIAL_TAKE_PROFIT_",
    "BREAKEVEN_",
    "TRAILING_PROFIT_",
    "DEFAULT_STOP_LOSS_",
    "DEFAULT_TAKE_PROFIT_",
    "SCALE_IN_",
    "COST_GATE_",
    "ESTIMATED_",
    "MIN_EDGE_TO_COST_RATIO_",
)


_LLM_API_KEY_SETTINGS = {
    "CODEX": "OPENAI_API_KEY",
    "CLAUDE_CODE": "ANTHROPIC_API_KEY",
}
_LLM_API_KEY_REGISTRY_SETTING = "LLM_API_KEY_REGISTRY"
_LLM_API_PROVIDERS = {
    "CLAUDE_API": {
        "label": "Claude API",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "OPENAI_API": {
        "label": "OpenAI API",
        "env_key": "OPENAI_API_KEY",
    },
}


def _resolve_llm_api_key_setting(provider: str) -> tuple[str, str]:
    normalized = str(provider or "").upper().strip()
    setting_key = _LLM_API_KEY_SETTINGS.get(normalized)
    if not setting_key:
        raise HTTPException(status_code=400, detail="지원하지 않는 LLM provider입니다")
    return normalized, setting_key


def _mask_secret(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _load_llm_api_key_registry() -> list[dict]:
    raw = getattr(settings, _LLM_API_KEY_REGISTRY_SETTING, [])
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except (TypeError, ValueError):
            raw = []
    if not isinstance(raw, list):
        return []

    items: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").upper().strip()
        api_key = str(item.get("api_key") or "")
        if provider not in _LLM_API_PROVIDERS or not api_key:
            continue
        items.append({
            "id": str(item.get("id") or uuid4()),
            "provider": provider,
            "label": str(item.get("label") or _LLM_API_PROVIDERS[provider]["label"]),
            "api_key": api_key,
            "enabled": bool(item.get("enabled", True)),
            "created_at": str(item.get("created_at") or datetime.now().isoformat()),
        })
    return items


def _redact_llm_api_key_item(item: dict) -> dict:
    provider = str(item.get("provider") or "").upper()
    provider_meta = _LLM_API_PROVIDERS.get(provider, {})
    api_key = str(item.get("api_key") or "")
    return {
        "id": item.get("id"),
        "provider": provider,
        "provider_label": provider_meta.get("label", provider),
        "label": item.get("label") or provider_meta.get("label", provider),
        "env_key": provider_meta.get("env_key", ""),
        "configured": bool(api_key),
        "masked": _mask_secret(api_key),
        "enabled": bool(item.get("enabled", True)),
        "created_at": item.get("created_at"),
    }


async def _persist_llm_api_key_registry(items: list[dict]) -> None:
    setattr(settings, _LLM_API_KEY_REGISTRY_SETTING, items)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            repository = RuntimeSettingRepository(session)
            await repository.upsert_value(_LLM_API_KEY_REGISTRY_SETTING, _json.dumps(items))


async def _persist_runtime_secret(setting_key: str, value: str) -> None:
    setattr(settings, setting_key, value)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            repository = RuntimeSettingRepository(session)
            await repository.upsert_value(setting_key, _json.dumps(value))


def _parse_json_detail(detail):
    if not detail:
        return None
    if isinstance(detail, dict):
        return detail
    try:
        return _json.loads(detail)
    except (TypeError, ValueError):
        return None


def _trade_horizon_from_trade_result(trade: TradeResult | None) -> str:
    if not trade:
        return "MID"
    notes = _parse_json_detail(getattr(trade, "notes", None)) or {}
    horizon = str(notes.get("trade_horizon") or "").upper()
    if horizon in {"SHORT", "MID", "LONG"}:
        return horizon
    strategy_type = str(getattr(trade, "strategy_type", "") or "").upper()
    if "AGGRESSIVE" in strategy_type:
        return "SHORT"
    return "MID"


def _trade_horizon_label(horizon: str) -> str:
    return {
        "SHORT": "단기",
        "MID": "중기",
        "LONG": "장기",
    }.get(str(horizon or "").upper(), "중기")


def _representative_trade_horizon(open_buys: list[TradeResult]) -> str:
    weighted: dict[str, int] = {"SHORT": 0, "MID": 0, "LONG": 0}
    for trade in open_buys:
        horizon = _trade_horizon_from_trade_result(trade)
        quantity = int(getattr(trade, "quantity", 0) or 0)
        weighted[horizon] = weighted.get(horizon, 0) + max(quantity, 0)
    if not any(weighted.values()):
        return "MID"
    return max(weighted.items(), key=lambda item: item[1])[0]


def _require_admin_action_confirmation(
    payload: AdminActionConfirmationVerifyRequest | None,
    *,
    action: str,
    resource_id: str,
    quantity: str | int | None = None,
    always: bool = False,
) -> None:
    if not always and not bool(getattr(settings, "ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", False)):
        return
    try:
        admin_action_confirmation_service.verify_token(
            getattr(payload, "confirmation_token", None),
            action=action,
            resource_id=resource_id,
            quantity=quantity,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "ADMIN_ACTION_CONFIRMATION_REQUIRED",
                "message": str(exc),
                "action": action,
                "resource_id": str(resource_id),
            },
        ) from exc


def _split_confirmation_token(payload: dict | None) -> tuple[dict, str | None]:
    updates = dict(payload or {})
    token = updates.pop("confirmation_token", None)
    return updates, token


def _protected_runtime_setting_keys(updates: dict) -> list[str]:
    protected: list[str] = []
    mutable_keys = set(MUTABLE_SETTINGS)
    for key in updates:
        if key not in mutable_keys:
            continue
        if key in _PROTECTED_RUNTIME_SETTING_KEYS or key.startswith(_PROTECTED_RUNTIME_SETTING_PREFIXES):
            protected.append(key)
    return sorted(protected)


def _runtime_settings_confirmation_quantity(keys: list[str]) -> str:
    return ",".join(keys) if keys else "NONE"


def _require_runtime_settings_confirmation(updates: dict, token: str | None) -> None:
    protected_keys = _protected_runtime_setting_keys(updates)
    if not protected_keys:
        return
    _require_admin_action_confirmation(
        AdminActionConfirmationVerifyRequest(confirmation_token=token),
        action=_RUNTIME_SETTINGS_CONFIRMATION_ACTION,
        resource_id=_RUNTIME_SETTINGS_CONFIRMATION_RESOURCE,
        quantity=_runtime_settings_confirmation_quantity(protected_keys),
        always=True,
    )


def _extract_latest_signal(trades, activities):
    fallback_trade = next(
        (
            trade for trade in trades
            if (
                getattr(trade, "ai_recommendation", "")
                or getattr(trade, "ai_target_price", None) is not None
                or getattr(trade, "ai_stop_loss_price", None) is not None
            )
        ),
        None,
    )
    for activity in activities:
        detail = _parse_json_detail(getattr(activity, "detail", None)) or {}
        recommendation = detail.get("recommendation")
        target_price = (
            detail.get("target_price")
            or detail.get("ai_target_price")
            or getattr(fallback_trade, "ai_target_price", None)
        )
        stop_loss_price = (
            detail.get("stop_loss_price")
            or detail.get("stop_loss")
            or detail.get("ai_stop_loss_price")
            or getattr(fallback_trade, "ai_stop_loss_price", None)
        )
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

    if fallback_trade:
        return {
            "recommendation": getattr(fallback_trade, "ai_recommendation", ""),
            "confidence": getattr(fallback_trade, "ai_confidence", None),
            "reason": getattr(fallback_trade, "exit_reason", "") or getattr(fallback_trade, "strategy_type", ""),
            "target_price": getattr(fallback_trade, "ai_target_price", None),
            "stop_loss_price": getattr(fallback_trade, "ai_stop_loss_price", None),
            "llm_provider": None,
            "llm_tier": None,
            "created_at": getattr(fallback_trade, "created_at", None),
        }

    return None


async def _capture_admin_api_error(
    operation: str,
    exc: Exception,
    *,
    symbol: str | None = None,
    detail: dict | None = None,
) -> None:
    provider = None
    try:
        provider = getattr(getattr(get_broker_adapter(), "provider", None), "value", None)
    except Exception:
        provider = None

    await error_capture_service.capture_exception(
        component="admin_api",
        operation=operation,
        exc=exc,
        symbol=normalize_krx_symbol(symbol) if symbol else None,
        provider=provider,
        detail=detail,
    )


def _coerce_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_balance_payload_fallback(balance) -> dict[str, object]:
    return {
        "total_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
        "cash": float(getattr(balance, "cash", 0.0) or 0.0),
        "stock_value": float(getattr(balance, "stock_value", 0.0) or 0.0),
        "total_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
        "total_pnl_rate": float(getattr(balance, "total_pnl_rate", 0.0) or 0.0),
        "session_metrics": {
            "available": False,
            "reason": "metrics_unavailable",
            "trading_date": None,
            "baseline_at": None,
            "baseline_total_asset": 0.0,
            "asset_delta": 0.0,
            "asset_delta_rate": 0.0,
            "realized_today_pnl": 0.0,
            "broker_unrealized_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
            "daily_unrealized_delta": 0.0,
            "cash_or_snapshot_delta": 0.0,
            "current_exposure_krw": float(getattr(balance, "stock_value", 0.0) or 0.0),
            "current_exposure_pct": (
                (float(getattr(balance, "stock_value", 0.0) or 0.0) / float(getattr(balance, "total_asset", 0.0) or 0.0) * 100.0)
                if float(getattr(balance, "total_asset", 0.0) or 0.0) > 0 else 0.0
            ),
            "market_exposure": float(getattr(balance, "stock_value", 0.0) or 0.0) > 0,
            "risk_label": "EXPOSED" if float(getattr(balance, "stock_value", 0.0) or 0.0) > 0 else "NO_EXPOSURE",
            "risk_message": "세션 메트릭 계산 실패로 노출 요약만 제공합니다.",
            "intraday_high_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
            "intraday_low_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
            "latest_snapshot_at": None,
            "snapshot_age_sec": None,
            "snapshot_freshness_status": "MISSING",
            "snapshot_stale_reason": "metrics_unavailable",
            "snapshot_stale_message": "세션 메트릭을 계산할 수 없어 계좌 스냅샷 최신성을 판단하지 못했습니다.",
            "snapshot_stale_blocks_buy": True,
            "is_stale": False,
        },
    }


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
        side = str(getattr(trade, "side", "") or "").upper()
        status = str(getattr(trade, "status", "") or "").upper()
        exit_price = float(getattr(trade, "exit_price", 0.0) or 0.0)
        fill_type = str(notes.get("fill_type") or "").upper()
        remaining_open_quantity = int(notes.get("remaining_open_quantity") or 0)
        has_exit = getattr(trade, "exit_at", None) is not None or (side == "BUY" and status == "CONFIRMED" and exit_price > 0)

        if side == "SELL":
            if status == "CONFIRM_FAILED":
                title = "매도 미체결"
                kind_label = "매도 미체결"
                badge = status or "CONFIRM_FAILED"
                tone = "pending"
                icon = "미체결"
                detail_label = "체결 실패 또는 주문 취소"
            elif status == "PENDING_CONFIRM":
                title = "매도 대기중"
                kind_label = "매도 대기중"
                badge = status or "SELL"
                tone = "pending"
                icon = "대기"
                detail_label = "체결 확인 대기"
            elif fill_type == "PARTIAL_EXIT" or remaining_open_quantity > 0:
                title = "부분 매도"
                kind_label = "부분 매도"
                badge = fill_type or "PARTIAL_EXIT"
                tone = "sell"
                icon = "부분"
                detail_label = f"잔량 {remaining_open_quantity}주 보유 중" if remaining_open_quantity > 0 else "일부 수량 청산"
            else:
                title = "매도 완료"
                kind_label = "매도 완료"
                badge = status or "SELL"
                tone = "sell"
                icon = "매도"
                detail_label = ""
        else:
            if status == "PENDING_CONFIRM":
                title = "매수 대기중"
                kind_label = "매수 대기중"
                badge = status or "BUY"
                tone = "pending"
                icon = "대기"
                detail_label = "체결 확인 대기"
            elif has_exit and (fill_type == "PARTIAL_EXIT" or remaining_open_quantity > 0):
                title = "부분 매도 후 정리"
                kind_label = "부분 매도 후 정리"
                badge = fill_type or "PARTIAL_EXIT"
                tone = "sell"
                icon = "부분"
                detail_label = f"잔량 {remaining_open_quantity}주 보유 중" if remaining_open_quantity > 0 else ""
            elif has_exit:
                title = "매도 완료"
                kind_label = "매도 완료"
                badge = "FINAL_EXIT"
                tone = "sell"
                icon = "매도"
                detail_label = ""
            else:
                title = "매수 완료"
                kind_label = "매수 완료"
                badge = status or "BUY"
                tone = "buy"
                icon = "매수"
                detail_label = ""

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
                "exit_price": exit_price,
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
                "trade_state_detail_label": detail_label,
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


async def _load_live_report_snapshot(report_date: date) -> dict[str, float | int]:
    from util.time_util import now_kst

    if report_date != now_kst().date():
        return {}

    try:
        adapter = get_broker_adapter()
        balance, holdings = await asyncio.gather(
            adapter.get_balance(),
            adapter.get_holdings(),
        )
    except Exception as exc:
        logger.warning("오늘 리포트 실시간 계좌 보정 실패: {}", str(exc))
        return {}

    return {
        "unrealized_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
        "open_position_count": len(holdings or []),
    }


def _extract_report_metric_contract(report) -> dict | None:
    raw_stats = getattr(report, "strategy_stats", None)
    if not raw_stats:
        return None
    try:
        stats = _json.loads(raw_stats) if isinstance(raw_stats, str) else raw_stats
    except (TypeError, _json.JSONDecodeError):
        return None
    if not isinstance(stats, dict):
        return None
    contract = stats.get("metric_contract")
    return contract if isinstance(contract, dict) else None


async def _build_report_response(report, trade_repo: TradeResultRepository, open_symbols_cache: set[str] | None = None):
    payload = DailyReportResponse.model_validate(report)
    report_date = getattr(report, "report_date", None)
    metric_contract = _extract_report_metric_contract(report)
    completed = []
    if report_date:
        completed = await trade_repo.get_completed_by_date(report_date)
    trade_comparison = ReportTradeComparisonResponse.model_validate(
        performance_reporting_service.build_trade_comparison_from_results(completed)
    )
    live_snapshot = await _load_live_report_snapshot(report_date) if report_date else {}

    if not _report_looks_empty(report):
        return payload.model_copy(update={
            "metric_contract": metric_contract,
            "trade_comparison": trade_comparison,
            **live_snapshot,
        })

    if not report_date:
        return payload.model_copy(update={
            "metric_contract": metric_contract,
            "trade_comparison": trade_comparison,
            **live_snapshot,
        })

    opened = await trade_repo.get_opened_by_date(report_date)
    trade_has_data = bool(opened or completed)
    if not trade_has_data:
        return payload.model_copy(update={
            "metric_contract": metric_contract,
            "trade_comparison": trade_comparison,
            **live_snapshot,
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
        "metric_contract": metric_contract,
        "trade_comparison": trade_comparison,
        **live_snapshot,
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


@router.get("/performance/decision-benchmark")
async def get_performance_decision_benchmark(
    days: int = Query(30, ge=1, le=365),
    horizon: str = Query("close"),
    min_sample_size: int = Query(12, ge=1, le=10000),
):
    """Decision event + forward return 기반 stage/provider/action benchmark."""
    normalized_horizon = horizon.strip().lower()
    if normalized_horizon not in {"5m", "15m", "30m", "60m", "close"}:
        raise HTTPException(status_code=400, detail="horizon must be one of 5m, 15m, 30m, 60m, close")
    data = await decision_benchmark_service.build_report(
        AsyncSessionLocal,
        days=days,
        horizon=normalized_horizon,
        min_sample_size=min_sample_size,
    )
    return SuccessResponse(data=data)


@router.get("/observability/overview")
async def get_observability_overview(
    hours: int = Query(24, ge=1, le=24 * 30),
    points: int = Query(120, ge=10, le=1000),
    db: AsyncSession = Depends(get_async_db),
):
    data = await observability_reporting_service.build_overview(
        db,
        hours=hours,
        points=points,
    )
    data["realtime"] = {
        "connected": stream_manager.is_connected,
        "subscription_count": stream_manager.subscription_count,
        "skipped_subscription_count": stream_manager.skipped_subscription_count,
        "polling_fallback_symbols": stream_manager.polling_fallback_symbols,
    }
    return SuccessResponse(data=data)


@router.post("/actions/confirmations")
async def create_admin_action_confirmation(payload: AdminActionConfirmationCreateRequest):
    data = admin_action_confirmation_service.create_challenge(
        action=payload.action,
        resource_id=payload.resource_id,
        quantity=payload.quantity,
    )
    return SuccessResponse(data=data, message="고위험 관리자 액션 확인 토큰 생성 완료")


@router.patch("/observability/incidents/{fingerprint}")
async def update_observability_incident(
    fingerprint: str,
    payload: ErrorIncidentUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        data = await error_incident_service.update_incident(
            db,
            fingerprint=fingerprint,
            status=payload.status,
            owner_note=payload.owner_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if data is None:
        raise HTTPException(status_code=404, detail="incident not found")
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
    # 오늘 매도 체결 (SELL 레코드 기준)
    sell_executions = await repo.get_sell_executions_by_date(d)
    # 오늘 청산된 포지션 (BUY 레코드, pnl 계산됨)
    completed = await repo.get_completed_by_date(d)
    # 오늘 체결 확인 대기
    pending_confirms = await repo.get_pending_confirms_by_date(d)
    # 미청산 포지션
    open_positions = await repo.get_all_open()

    return SuccessResponse(data={
        "date": str(d),
        "opened": [TradeResultResponse.model_validate(t) for t in opened],
        "sell_executions": [TradeResultResponse.model_validate(t) for t in sell_executions],
        "completed": [TradeResultResponse.model_validate(t) for t in completed],
        "pending_confirms": [TradeResultResponse.model_validate(t) for t in pending_confirms],
        "open_positions": [TradeResultResponse.model_validate(t) for t in open_positions],
    })


@router.post("/trades/reconcile-pending")
async def reconcile_pending_trades(confirmation: AdminActionConfirmationVerifyRequest | None = None):
    """PENDING_CONFIRM 거래를 수동으로 복구 시도"""
    _require_admin_action_confirmation(
        confirmation,
        action="RECOVER_PENDING_CONFIRMS",
        resource_id="TRADE_RECONCILIATION",
        quantity="ALL",
        always=True,
    )
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


@router.get("/trades/reconciliation")
async def get_trade_reconciliation_report(db: AsyncSession = Depends(get_async_db)):
    """브로커 미체결과 DB PENDING_CONFIRM 간 read-only 대사 리포트"""
    broker_pending_orders = await get_broker_adapter().get_pending_orders()
    repo = TradeResultRepository(db)
    db_pending_confirms = await repo.get_pending_confirms()
    db_order_linked_trades = await repo.get_by_order_ids([
        str(getattr(order, "order_id", "") or "")
        for order in broker_pending_orders
    ])
    report = order_reconciliation_service.build_report(
        broker_pending_orders=broker_pending_orders,
        db_pending_confirms=db_pending_confirms,
        db_order_linked_trades=db_order_linked_trades,
    )
    return SuccessResponse(data=report, message="주문 대사 리포트 조회 완료")


@router.get("/trades/close-reconciliation")
async def get_trade_close_reconciliation_report(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    """SELL 체결과 BUY lot 청산 손익 간 read-only dry-run 대사 리포트"""
    report = await trade_close_reconciliation_service.build_dry_run(db, days=days)
    return SuccessResponse(data=report, message="청산 대사 dry-run 리포트 조회 완료")


@router.get("/trades/lifecycle-integrity")
async def get_trade_lifecycle_integrity_report(
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
):
    """초기화 이후 BUY→SELL→성과 반영 흐름의 무결성 점검"""
    broker_position_snapshot = await _build_broker_position_snapshot_for_integrity()
    report = await trade_lifecycle_integrity_service.build_report(
        db,
        days=days,
        broker_position_snapshot=broker_position_snapshot,
    )
    return SuccessResponse(data=report, message="거래 라이프사이클 무결성 점검 완료")


async def _build_broker_position_snapshot_for_integrity() -> dict:
    try:
        adapter = get_broker_adapter()
        holdings = await adapter.get_holdings()
        pending_orders = await adapter.get_pending_orders()
        return {
            "provider": getattr(getattr(adapter, "provider", None), "value", None) or str(getattr(adapter, "provider", "")),
            "holding_quantities": {
                normalize_krx_symbol(getattr(holding, "symbol", "")): int(getattr(holding, "quantity", 0) or 0)
                for holding in holdings
                if normalize_krx_symbol(getattr(holding, "symbol", ""))
                and int(getattr(holding, "quantity", 0) or 0) > 0
            },
            "pending_symbols": [
                normalize_krx_symbol(getattr(order, "symbol", ""))
                for order in pending_orders
                if normalize_krx_symbol(getattr(order, "symbol", ""))
                and int(getattr(order, "remaining_qty", 0) or 0) > 0
            ],
        }
    except Exception as exc:
        logger.warning("라이프사이클 브로커 포지션 스냅샷 조회 실패: {}", str(exc))
        return {"error": str(exc)[:200]}


@router.post("/trades/close-reconciliation/apply")
async def apply_trade_close_reconciliation(
    days: int = Query(30, ge=1, le=365),
    confirmation: AdminActionConfirmationVerifyRequest | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    """SELL→BUY 청산 손익 보정을 적용한다. 완전 매칭 SELL만 변경한다."""
    confirmation_action = "APPLY_TRADE_CLOSE_RECONCILIATION"
    confirmation_resource = "TRADE_CLOSE_RECONCILIATION"
    confirmation_quantity = f"{days}D"
    try:
        admin_action_confirmation_service.verify_token(
            getattr(confirmation, "confirmation_token", None),
            action=confirmation_action,
            resource_id=confirmation_resource,
            quantity=confirmation_quantity,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "ADMIN_ACTION_CONFIRMATION_REQUIRED",
                "message": str(exc),
                "action": confirmation_action,
                "resource_id": confirmation_resource,
            },
        ) from exc
    result = await trade_close_reconciliation_service.apply_reconciliation(db, days=days)
    await db.commit()
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        "🧾 SELL→BUY 청산 대사 보정 적용",
        detail={
            "mode": result["mode"],
            "summary": result["summary"],
        },
    )
    message = (
        f"청산 대사 적용 완료 · SELL {result['summary'].get('applied_sell_count', 0)}건 / "
        f"BUY lot {result['summary'].get('updated_buy_lot_count', 0)}건 / "
        f"손익 {result['summary'].get('applied_pnl', 0):,.0f}원"
    )
    return SuccessResponse(data=result, message=message)


@router.post("/trades/reconciliation/cleanup")
async def cleanup_stale_pending_trades(
    apply: bool = Query(False, description="true일 때만 DB PENDING_CONFIRM을 CONFIRM_FAILED로 변경"),
    confirmation: AdminActionConfirmationVerifyRequest | None = None,
    db: AsyncSession = Depends(get_async_db),
):
    """브로커 pending에 없는 오래된 DB-only BUY PENDING_CONFIRM을 수동 정리"""
    if apply:
        _require_admin_action_confirmation(
            confirmation,
            action="CLEANUP_STALE_PENDING",
            resource_id="TRADE_RECONCILIATION",
            quantity="ALL",
            always=True,
        )
    broker_pending_orders = await get_broker_adapter().get_pending_orders()
    db_pending_confirms = await TradeResultRepository(db).get_pending_confirms()
    result = await stale_pending_cleanup_service.cleanup(
        db,
        broker_pending_orders=broker_pending_orders,
        db_pending_confirms=db_pending_confirms,
        dry_run=not apply,
    )
    if apply:
        await db.commit()
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        "🧹 stale PENDING_CONFIRM 수동 정리 실행",
        detail={
            "mode": result["mode"],
            "summary": result["summary"],
        },
    )
    message = (
        f"stale pending 정리 {'적용' if apply else 'DRY_RUN'} · "
        f"대상 {result['summary'].get('eligible_count', 0)}건 / "
        f"변경 {result['summary'].get('updated_count', 0)}건"
    )
    return SuccessResponse(data=result, message=message)


@router.post("/trades/reconcile-holdings")
async def reconcile_holdings_trades(
    apply_backfill: bool = Query(False, description="true일 때 브로커 보유 기반 누락 open BUY 백필을 적용"),
    apply_zero_price_repair: bool = Query(False, description="true일 때 0원 진입가 복구를 적용"),
    apply_missing_closes: bool = Query(False, description="true일 때 브로커 미보유 DB open BUY를 중립 종료"),
    confirmation: AdminActionConfirmationVerifyRequest | None = None,
):
    """계좌 보유수량 기준으로 누락 BUY lot/0원 체결가 복구 및 stale open BUY 정리"""
    apply_any = apply_backfill or apply_zero_price_repair or apply_missing_closes
    if apply_any:
        quantity = ",".join(
            label
            for label, enabled in (
                ("BACKFILL", apply_backfill),
                ("ZERO_PRICE_REPAIR", apply_zero_price_repair),
                ("MISSING_CLOSES", apply_missing_closes),
            )
            if enabled
        )
        _require_admin_action_confirmation(
            confirmation,
            action="RECONCILE_HOLDINGS_TRADES",
            resource_id="TRADE_RECONCILIATION",
            quantity=quantity or "ALL",
            always=True,
        )
    backfill = await portfolio_sync_job._backfill_missing_open_buys_from_holdings(
        dry_run=not apply_backfill,
    )
    repaired = await portfolio_sync_job._repair_confirmed_zero_entry_prices(
        dry_run=not apply_zero_price_repair,
    )
    missing_closes = await portfolio_sync_job._close_open_buys_missing_from_holdings(
        dry_run=not apply_missing_closes,
    )
    quantity_closes = await portfolio_sync_job._close_open_buy_quantity_excess_from_holdings(
        dry_run=not apply_missing_closes,
    )
    summary = {
        "backfill": backfill,
        "repair": repaired,
        "missing_closes": missing_closes,
        "quantity_closes": quantity_closes,
    }
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        "🧩 보유수량 기반 TradeResult 정합성 점검/복구 실행",
        detail=summary,
    )
    message = (
        f"정합성 {'복구' if apply_any else '점검'} 완료 · 백필 {backfill.get('backfilled', 0)}건 / "
        f"체결가 복구 {repaired.get('repaired', 0)}건 / "
        f"미보유 정리 {missing_closes['summary'].get('closed_count', 0)}건 / "
        f"수량초과 정리 {quantity_closes['summary'].get('closed_count', 0)}건"
    )
    return SuccessResponse(data=summary, message=message)


@router.post("/system/reset-operational-baseline")
async def reset_operational_baseline(confirmation: AdminActionConfirmationVerifyRequest | None = None):
    """설정은 유지하고 운영 이력 DB를 초기화한 뒤 현재 보유 기준선으로 재구성"""
    _require_admin_action_confirmation(
        confirmation,
        action="RESET_OPERATIONAL_BASELINE",
        resource_id="OPERATIONAL_BASELINE",
        quantity="ALL",
        always=True,
    )
    backup = runtime_backup_service.create_database_backup(reason="before-reset")
    deleted: dict[str, int] = {}
    models_to_clear = [
        ("recommendations", Recommendation),
        ("analysis_results", AnalysisResult),
        ("orders", Order),
        ("trade_results", TradeResult),
        ("daily_reports", DailyReport),
        ("account_day_baselines", AccountDayBaseline),
        ("account_equity_snapshots", AccountEquitySnapshot),
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
    broker_snapshot: dict[str, object] = {
        "synced": False,
        "holdings_count": 0,
        "pending_order_count": 0,
        "total_asset": 0.0,
        "cash": 0.0,
        "stock_value": 0.0,
        "total_pnl": 0.0,
        "baseline_seeded": False,
        "warning": "",
    }
    try:
        adapter = get_broker_adapter()
        balance, holdings, pending_orders = await asyncio.gather(
            adapter.get_balance(),
            adapter.get_holdings(),
            adapter.get_pending_orders(),
        )
        broker_snapshot = {
            "synced": True,
            "holdings_count": len(holdings or []),
            "pending_order_count": len(pending_orders or []),
            "total_asset": float(getattr(balance, "total_asset", 0.0) or 0.0),
            "cash": float(getattr(balance, "cash", 0.0) or 0.0),
            "stock_value": float(getattr(balance, "stock_value", 0.0) or 0.0),
            "total_pnl": float(getattr(balance, "total_pnl", 0.0) or 0.0),
            "baseline_seeded": False,
            "warning": "",
        }
        try:
            state = account_equity_service.build_state(
                balance,
                holdings=holdings,
                pending_orders=pending_orders,
            )
            await account_equity_service.record_snapshot(
                state,
                session_phase="RESET_BASELINE",
                baseline_source="RESET_BASELINE",
            )
            broker_snapshot["baseline_seeded"] = True
        except Exception as metrics_exc:
            logger.warning("기준선 리셋 후 계좌 기준선 기록 실패: {}", str(metrics_exc))
            broker_snapshot["warning"] = str(metrics_exc)[:160]
    except Exception as exc:
        logger.warning("기준선 리셋 후 브로커 스냅샷 재동기화 실패: {}", str(exc))
        broker_snapshot["warning"] = str(exc)[:160]

    summary = {
        "backup": backup,
        "deleted": deleted,
        "backfill": backfill,
        "repair": repair,
        "baseline_mode": "broker_snapshot",
        "limitations": {
            "historical_realized_pnl_restored": False,
            "historical_reports_restored": False,
            "historical_news_ingestion_restored": False,
        },
        "broker_snapshot": broker_snapshot,
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
        f"운영 DB 초기화 완료 · 백업 {backup.get('filename')} / 거래 {deleted.get('trade_results', 0)}건 / "
        f"뉴스 {deleted.get('news_items', 0)}건 삭제, "
        f"보유 백필 {backfill.get('backfilled', 0)}건 / "
        f"현재 보유 {broker_snapshot.get('holdings_count', 0)}종목 기준선 재구성"
    )
    return SuccessResponse(data=summary, message=message)


@router.post("/system/backup-operational-db")
async def backup_operational_db():
    """운영 DB 스냅샷을 runtime/backups 아래에 저장"""
    backup = runtime_backup_service.create_database_backup(reason="manual")
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.COMPLETE,
        "💾 운영 DB 수동 백업 생성",
        detail=backup,
    )
    return SuccessResponse(
        data=backup,
        message=f"운영 DB 백업 완료 · {backup.get('filename')}",
    )


# ── 계좌 정보 ──
@router.get("/account/balance")
async def get_account_balance():
    """계좌 잔고 조회"""
    try:
        balance = await get_broker_adapter().get_balance()
        try:
            payload = await account_equity_service.build_balance_payload(balance)
        except Exception as metrics_exc:
            logger.warning("계좌 세션 메트릭 조회 실패: {}", str(metrics_exc))
            payload = _build_balance_payload_fallback(balance)
        return SuccessResponse(data=payload)
    except Exception as e:
        logger.error("계좌 잔고 조회 실패: {}", str(e))
        await _capture_admin_api_error(
            "account_balance",
            e,
            detail={"route": "/admin/account/balance"},
        )
        return SuccessResponse(data=None, message=f"잔고 조회 실패: {str(e)[:100]}")


@router.post("/account/snapshot/refresh")
async def refresh_account_snapshot():
    """현재 브로커 계좌 상태를 계좌 자산 스냅샷으로 즉시 기록"""
    try:
        snapshot = await account_equity_service.capture_and_record_current(
            session_phase="MANUAL_REFRESH",
            detail={"reason": "admin_manual_refresh"},
            baseline_source="MANUAL_REFRESH",
        )
        data = {
            "captured_at": ensure_kst(snapshot.captured_at).isoformat(),
            "trading_date": snapshot.trading_date.isoformat(),
            "total_asset": float(snapshot.total_asset or 0.0),
            "cash": float(snapshot.cash or 0.0),
            "stock_value": float(snapshot.stock_value or 0.0),
            "total_unrealized_pnl": float(snapshot.total_unrealized_pnl or 0.0),
            "total_unrealized_pnl_rate": float(snapshot.total_unrealized_pnl_rate or 0.0),
            "holding_count": int(snapshot.holding_count or 0),
            "pending_order_count": int(snapshot.pending_order_count or 0),
            "session_phase": snapshot.session_phase,
        }
        await activity_logger.log(
            ActivityType.EVENT,
            ActivityPhase.COMPLETE,
            "📸 계좌 스냅샷 수동 갱신",
            detail=data,
        )
        return SuccessResponse(data=data, message="계좌 스냅샷 갱신 완료")
    except Exception as e:
        logger.error("계좌 스냅샷 수동 갱신 실패: {}", str(e))
        await _capture_admin_api_error(
            "account_snapshot_refresh",
            e,
            detail={"route": "/admin/account/snapshot/refresh"},
        )
        return SuccessResponse(data=None, message=f"계좌 스냅샷 갱신 실패: {str(e)[:100]}")


@router.get("/account/holdings")
async def get_account_holdings():
    """보유 종목 조회"""
    try:
        holdings = await get_broker_adapter().get_holdings()
        horizon_by_symbol: dict[str, str] = {}
        async with AsyncSessionLocal() as session:
            repo = TradeResultRepository(session)
            for h in holdings:
                symbol = normalize_krx_symbol(getattr(h, "symbol", ""))
                open_buys = await repo.get_all_open_buys(symbol)
                horizon_by_symbol[symbol] = _representative_trade_horizon(open_buys)

        items = []
        for h in holdings:
            symbol = normalize_krx_symbol(getattr(h, "symbol", ""))
            horizon = horizon_by_symbol.get(symbol, "MID")
            items.append({
                "symbol": symbol,
                "name": h.name,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
                "current_price": h.current_price,
                "pnl": h.pnl,
                "pnl_rate": h.pnl_rate,
                "trade_horizon": horizon,
                "trade_horizon_label": _trade_horizon_label(horizon),
            })
        return SuccessResponse(data=items)
    except Exception as e:
        logger.error("보유 종목 조회 실패: {}", str(e))
        await _capture_admin_api_error(
            "account_holdings",
            e,
            detail={"route": "/admin/account/holdings"},
        )
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
        await _capture_admin_api_error(
            "account_pending_orders",
            e,
            detail={"route": "/admin/account/pending-orders"},
        )
        return SuccessResponse(data=[], message=f"미체결 주문 조회 실패: {str(e)[:100]}")


@router.post("/account/holdings/{symbol}/sell")
async def sell_account_holding(symbol: str, confirmation: AdminActionConfirmationVerifyRequest | None = None):
    normalized_symbol = normalize_krx_symbol(symbol)
    _require_admin_action_confirmation(
        confirmation,
        action="SELL_HOLDING",
        resource_id=normalized_symbol,
        quantity="ALL",
        always=True,
    )
    result = await manual_trade_service.sell_position(symbol)
    return SuccessResponse(data=result, message=f"{result['symbol']} 즉시 매도 주문 접수")


@router.post("/account/pending-orders/{order_id}/cancel-buy")
async def cancel_pending_buy_order(order_id: str, confirmation: AdminActionConfirmationVerifyRequest | None = None):
    _require_admin_action_confirmation(
        confirmation,
        action="CANCEL_PENDING_BUY",
        resource_id=order_id,
        quantity="ALL",
        always=True,
    )
    result = await manual_trade_service.cancel_pending_buy(order_id)
    return SuccessResponse(data=result, message="미체결 매수 주문 취소 완료")


@router.post("/account/pending-orders/{order_id}/cancel-and-sell")
async def cancel_pending_sell_and_resubmit(order_id: str, confirmation: AdminActionConfirmationVerifyRequest | None = None):
    _require_admin_action_confirmation(
        confirmation,
        action="CANCEL_AND_SELL_PENDING",
        resource_id=order_id,
        quantity="ALL",
        always=True,
    )
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
            "translate_foreign_enabled": bool(settings.NEWS_TRANSLATE_FOREIGN_ENABLED),
        },
        "sources": news_ingest_service.get_source_catalog(
            include_foreign=bool(settings.NEWS_INCLUDE_FOREIGN)
        ),
    })


@router.get("/news/items")
async def get_news_items(
    symbol: str | None = Query(None),
    source_code: str | None = Query(None),
    published_from: date | None = Query(None),
    published_to: date | None = Query(None),
    sentiment_label: str | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
):
    """저장된 뉴스 아이템 조회"""
    published_from_dt = (
        datetime.combine(published_from, time.min)
        if published_from
        else None
    )
    published_to_dt = (
        datetime.combine(published_to, time.max)
        if published_to
        else None
    )
    items = await news_ingest_service.list_items(
        db,
        limit=limit,
        offset=offset,
        symbol=symbol,
        source_code=source_code,
        published_from=published_from_dt,
        published_to=published_to_dt,
        sentiment_label=sentiment_label,
        query=query,
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


@router.post("/news/backfill-enrichment")
async def backfill_news_enrichment(
    limit: int = Query(200, ge=1, le=1000),
    source_code: str | None = Query(None),
    missing_only: bool = Query(True),
    apply: bool = Query(False),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """기존 news_items에 rule 기반 리스크/섹터 enrichment를 재적용."""
    summary = await news_enrichment_backfill_service.process(
        db,
        limit=limit,
        source_code=source_code,
        missing_only=missing_only,
        apply=apply,
    )
    mode = "적용" if apply else "DRY_RUN"
    return SuccessResponse(data=summary, message=f"뉴스 enrichment backfill {mode} 완료")


@router.post("/stocks/bootstrap-universe")
async def bootstrap_stock_universe(
    rank_limit: int = Query(50, ge=0, le=200),
    apply: bool = Query(False),
    db: AsyncSession = Depends(get_async_db_with_transaction),
):
    """브로커 관측 종목으로 비어 있는 stocks universe를 복구."""
    summary = await stock_universe_bootstrap_service.process(
        db,
        rank_limit=rank_limit,
        apply=apply,
    )
    mode = "적용" if apply else "DRY_RUN"
    return SuccessResponse(data=summary, message=f"종목 universe bootstrap {mode} 완료")


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
    updates, confirmation_token = _split_confirmation_token(updates)
    _require_runtime_settings_confirmation(updates, confirmation_token)
    changed = await runtime_settings_service.update_settings(updates)

    if changed:
        await activity_logger.log(
            ActivityType.EVENT, ActivityPhase.PROGRESS,
            f"\u2699\ufe0f 설정 변경: {', '.join(changed.keys())}",
            detail=changed,
        )

    return SuccessResponse(data=changed, message=f"{len(changed)}개 설정 변경됨")


@router.post("/settings/apply")
async def apply_settings(updates: dict):
    """런타임 설정 배치 적용 — 신규 작업을 멈추고 현재 작업이 끝난 뒤 반영"""
    updates, confirmation_token = _split_confirmation_token(updates)
    _require_runtime_settings_confirmation(updates, confirmation_token)
    result = await runtime_reconfiguration_service.apply_settings(updates)
    changed = result.get("changed", {})
    return SuccessResponse(
        data=result,
        message=f"{len(changed)}개 설정 적용 완료",
    )


@router.get("/llm/api-keys")
async def get_llm_api_key_status():
    """LLM 인증용 API 키 등록 상태 조회 — 실제 키 값은 반환하지 않는다."""
    try:
        usage_snapshot = await llm_usage_service.get_snapshot()
    except Exception:
        usage_snapshot = {}
    detected_cli_slots = sum(
        1
        for key in ("claude_code", "codex")
        if (usage_snapshot.get(key) or {}).get("available")
    )
    cli_env = {
        provider: {
            "env_key": setting_key,
            "configured": bool(getattr(settings, setting_key, "")),
            "masked": _mask_secret(getattr(settings, setting_key, "")),
        }
        for provider, setting_key in _LLM_API_KEY_SETTINGS.items()
    }
    api_items = [_redact_llm_api_key_item(item) for item in _load_llm_api_key_registry()]
    api_workers = [item for item in api_items if item["configured"] and item["enabled"]]
    return SuccessResponse(data={
        **cli_env,
        "providers": _LLM_API_PROVIDERS,
        "items": api_items,
        "worker_summary": {
            "cli_slots": detected_cli_slots,
            "cli_key_slots": sum(1 for item in cli_env.values() if item["configured"]),
            "api_slots": len(api_workers),
            "total_slots": len(api_workers) + detected_cli_slots,
        },
    })


@router.post("/llm/api-keys")
async def update_llm_api_key(payload: LLMApiKeyUpdateRequest):
    """LLM 인증용 API 키를 저장한다."""
    requested_provider = str(payload.provider or "").upper().strip()
    api_key = str(payload.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키를 입력하세요")
    _require_admin_action_confirmation(
        AdminActionConfirmationVerifyRequest(confirmation_token=payload.confirmation_token),
        action="UPDATE_LLM_API_KEY",
        resource_id=requested_provider,
        quantity="SECRET",
        always=True,
    )

    if requested_provider in _LLM_API_PROVIDERS:
        items = _load_llm_api_key_registry()
        provider_meta = _LLM_API_PROVIDERS[requested_provider]
        label = str(payload.label or "").strip() or f"{provider_meta['label']} {len(items) + 1}"
        new_item = {
            "id": str(uuid4()),
            "provider": requested_provider,
            "label": label[:80],
            "api_key": api_key,
            "enabled": bool(payload.enabled),
            "created_at": datetime.now().isoformat(),
        }
        items.append(new_item)
        await _persist_llm_api_key_registry(items)
        await _persist_runtime_secret(provider_meta["env_key"], api_key)
        redacted = _redact_llm_api_key_item(new_item)
        await activity_logger.log(
            ActivityType.EVENT,
            ActivityPhase.PROGRESS,
            f"LLM API worker 키 추가: {requested_provider}",
            detail={
                "provider": requested_provider,
                "key_id": redacted["id"],
                "label": redacted["label"],
                "configured": True,
            },
        )
        logger.info("LLM API worker 키 추가: {} ({})", requested_provider, redacted["id"])
        return SuccessResponse(data=redacted, message="LLM API 키가 추가되었습니다")

    provider, setting_key = _resolve_llm_api_key_setting(requested_provider)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            repository = RuntimeSettingRepository(session)
            await repository.upsert_value(setting_key, _json.dumps(api_key))

    setattr(settings, setting_key, api_key)
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        f"LLM API 키 등록: {provider}",
        detail={"provider": provider, "env_key": setting_key, "configured": True},
    )
    logger.info("LLM API 키 등록: {} ({})", provider, setting_key)
    return SuccessResponse(
        data={
            provider: {
                "env_key": setting_key,
                "configured": True,
                "masked": _mask_secret(api_key),
            }
        },
        message="LLM API 키가 등록되었습니다",
    )


@router.delete("/llm/api-keys/{provider}")
async def clear_llm_api_key(
    provider: str,
    payload: AdminActionConfirmationVerifyRequest | None = Body(default=None),
):
    """LLM API 키를 비활성화한다."""
    requested = str(provider or "").strip()
    normalized_requested = requested.upper()
    _require_admin_action_confirmation(
        payload,
        action="DELETE_LLM_API_KEY",
        resource_id=requested,
        quantity="SECRET",
        always=True,
    )

    if normalized_requested not in _LLM_API_KEY_SETTINGS:
        items = _load_llm_api_key_registry()
        removed_items = [item for item in items if str(item.get("id")) == requested]
        next_items = [item for item in items if str(item.get("id")) != requested]
        if len(next_items) == len(items):
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")
        await _persist_llm_api_key_registry(next_items)
        if removed_items:
            removed_provider = str(removed_items[0].get("provider") or "").upper()
            provider_meta = _LLM_API_PROVIDERS.get(removed_provider)
            if provider_meta and getattr(settings, provider_meta["env_key"], "") == removed_items[0].get("api_key"):
                replacement = next(
                    (
                        item.get("api_key")
                        for item in reversed(next_items)
                        if item.get("provider") == removed_provider and item.get("enabled", True)
                    ),
                    "",
                )
                await _persist_runtime_secret(provider_meta["env_key"], str(replacement or ""))
        await activity_logger.log(
            ActivityType.EVENT,
            ActivityPhase.PROGRESS,
            "LLM API worker 키 삭제",
            detail={"key_id": requested},
        )
        logger.info("LLM API worker 키 삭제: {}", requested)
        return SuccessResponse(data={"id": requested, "deleted": True}, message="LLM API 키가 삭제되었습니다")

    normalized_provider, setting_key = _resolve_llm_api_key_setting(normalized_requested)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            repository = RuntimeSettingRepository(session)
            await repository.upsert_value(setting_key, _json.dumps(""))

    setattr(settings, setting_key, "")
    await activity_logger.log(
        ActivityType.EVENT,
        ActivityPhase.PROGRESS,
        f"LLM API 키 해제: {normalized_provider}",
        detail={"provider": normalized_provider, "env_key": setting_key, "configured": False},
    )
    logger.info("LLM API 키 해제: {} ({})", normalized_provider, setting_key)
    return SuccessResponse(
        data={
            normalized_provider: {
                "env_key": setting_key,
                "configured": False,
                "masked": "",
            }
        },
        message="LLM API 키가 해제되었습니다",
    )


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
        payload = await model_catalog_service.get_catalog(force_refresh=force_refresh)
        message = None
        if payload.get("stale"):
            message = "LLM catalog refresh returned a stale cache after upstream sync failed"
        elif any(provider.get("warnings") for provider in payload.get("providers", [])):
            message = "LLM catalog refreshed with partial upstream warnings"
        return SuccessResponse(data=payload, message=message)
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
    from util.time_util import now_kst

    broker_provider = settings.normalized_broker_provider
    broker_adapter = get_broker_adapter()
    broker_capabilities = broker_adapter.capabilities
    supported_sessions = [session.value for session in broker_capabilities.supported_order_sessions]
    mcp_required = broker_runtime_service.mcp_required
    mcp_connected = broker_runtime_service.mcp_connected
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

    capability_message = (
        "정규장 주문만 지원합니다."
        if not broker_capabilities.supports_after_hours_orders
        else "시간외 주문 지원 범위를 확인할 수 있습니다."
    )

    if not mcp_required:
        broker_ops = {
            "status": "OK",
            "label": "브로커 정상",
            "message": f"{broker_provider} 브로커는 직접 연동합니다. {capability_message}",
            "supported_sessions": supported_sessions,
        }
    elif mcp_connected:
        broker_ops = {
            "status": "OK",
            "label": "브로커 정상",
            "message": f"{broker_provider} 브로커 런타임 연결이 준비되어 있습니다. {capability_message}",
            "supported_sessions": supported_sessions,
        }
    else:
        broker_ops = {
            "status": "ERROR",
            "label": "브로커 확인 필요",
            "message": f"{broker_provider} 브로커 런타임 연결이 끊겨 있어 호출이 실패할 수 있습니다. {capability_message}",
            "supported_sessions": supported_sessions,
        }

    news_last_status = str(news_overall.get("last_status") or "IDLE").upper()
    news_source_successes = [
        code for code, state in news_sources.items()
        if str((state or {}).get("status") or "").upper() in {"SUCCESS", "EMPTY"}
    ]
    news_source_last_run_at = max(
        (
            str((state or {}).get("updated_at") or (state or {}).get("last_success_at") or "")
            for state in news_sources.values()
            if (state or {}).get("updated_at") or (state or {}).get("last_success_at")
        ),
        default=None,
    )
    news_sources_limited = not settings.NEWS_INCLUDE_FOREIGN and not settings.NEWS_DOMESTIC_MEDIA_ENABLED
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
    elif news_sources_limited:
        news_ops = {
            "status": "WARN",
            "label": "뉴스 소스 제한됨",
            "message": "해외 뉴스와 국내 언론 소스가 모두 꺼져 있어 공시 위주로만 동작합니다.",
            "last_run_at": news_overall.get("last_run_at"),
        }
    elif news_last_status == "SKIPPED":
        news_ops = {
            "status": "WARN",
            "label": "뉴스 폴링 스킵",
            "message": str(news_overall.get("last_message") or "최근 뉴스 폴링이 스킵되었습니다."),
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
    elif news_source_successes and news_source_last_run_at:
        news_ops = {
            "status": "OK",
            "label": "뉴스 폴링 정상",
            "message": f"최근 성공 소스 {len(news_source_successes)}개: {', '.join(news_source_successes[:3])}",
            "last_run_at": news_source_last_run_at,
        }
    else:
        news_ops = {
            "status": "WARN",
            "label": "뉴스 폴링 대기",
            "message": "아직 자동 뉴스 수집 이력이 없습니다.",
            "last_run_at": None,
        }

    latest_order_error_at = getattr(latest_order_error, "created_at", None) if latest_order_error is not None else None
    latest_order_error_recent = latest_order_error is not None
    if latest_order_error_at is not None:
        latest_order_error_recent = (
            now_kst() - ensure_kst(latest_order_error_at)
        ).total_seconds() <= ORDER_ERROR_RECENT_WINDOW_HOURS * 3600

    if latest_order_error is not None and latest_order_error_recent:
        order_ops = {
            "status": "WARN",
            "label": "최근 주문 오류",
            "message": latest_order_error.error_message or latest_order_error.summary,
            "symbol": latest_order_error.symbol,
            "created_at": latest_order_error.created_at.isoformat() if latest_order_error.created_at else None,
        }
    elif latest_order_error is not None:
        order_ops = {
            "status": "OK",
            "label": "주문 오류 없음",
            "message": f"최근 {ORDER_ERROR_RECENT_WINDOW_HOURS}시간 주문 오류 로그가 없습니다.",
            "symbol": None,
            "created_at": None,
            "last_error_at": latest_order_error_at.isoformat() if latest_order_error_at else None,
        }
    else:
        order_ops = {
            "status": "OK",
            "label": "주문 오류 없음",
            "message": "최근 주문 오류 로그가 없습니다.",
            "symbol": None,
            "created_at": None,
        }

    ollama_candidates = [
        settings.LLM_PROVIDER_TIER1,
        settings.LLM_PROVIDER_TIER2,
        settings.LLM_FALLBACK_PROVIDER_TIER1,
        settings.LLM_FALLBACK_PROVIDER_TIER2,
        settings.MANUAL_LLM_PROVIDER,
        settings.MANUAL_LLM_FALLBACK_PROVIDER,
        settings.NEWS_LLM_PROVIDER,
        settings.NEWS_LLM_FALLBACK_PROVIDER,
    ]
    ollama_required = any(str(value or "").upper() == "OLLAMA" for value in ollama_candidates)
    if not ollama_required:
        ollama_ops = {
            "status": "OK",
            "label": "Ollama 미사용",
            "message": "현재 활성 AI 설정에 Ollama가 포함되어 있지 않습니다.",
            "base_url": settings.OLLAMA_BASE_URL,
        }
    else:
        ollama_available = await OllamaProvider(LLMTier.TIER1).is_available()
        ollama_ops = {
            "status": "OK" if ollama_available else "WARN",
            "label": "Ollama 연결 정상" if ollama_available else "Ollama 연결 필요",
            "message": (
                f"{settings.OLLAMA_BASE_URL} 연결 확인"
                if ollama_available
                else f"{settings.OLLAMA_BASE_URL} 에 연결할 수 없습니다."
            ),
            "base_url": settings.OLLAMA_BASE_URL,
        }

    market_session = market_calendar.get_market_session_info()
    latest_snapshot = (
        await db.execute(
            select(AccountEquitySnapshot).order_by(AccountEquitySnapshot.captured_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    latest_snapshot_at = getattr(latest_snapshot, "captured_at", None) if latest_snapshot else None
    snapshot_freshness = classify_account_snapshot_freshness(
        latest_captured_at=latest_snapshot_at,
        observed_at=now_kst(),
    )
    snapshot_status = str(snapshot_freshness.get("snapshot_freshness_status") or "MISSING")
    if snapshot_status == "FRESH":
        account_snapshot_ops = {
            "status": "OK",
            "label": "계좌 스냅샷 최신",
            "message": "계좌 스냅샷이 최신입니다.",
        }
    elif snapshot_status == "OFF_SESSION_STALE":
        account_snapshot_ops = {
            "status": "OK",
            "label": "비자동매매 세션 스냅샷 대기",
            "message": snapshot_freshness.get("snapshot_stale_message"),
        }
    else:
        account_snapshot_ops = {
            "status": "WARN",
            "label": "계좌 스냅샷 갱신 필요",
            "message": snapshot_freshness.get("snapshot_stale_message"),
        }
    account_snapshot_ops.update({
        "latest_snapshot_at": latest_snapshot_at.isoformat() if latest_snapshot_at else None,
        "snapshot_age_sec": snapshot_freshness.get("snapshot_age_sec"),
        "snapshot_freshness_status": snapshot_status,
        "snapshot_stale_blocks_buy": bool(snapshot_freshness.get("snapshot_stale_blocks_buy")),
    })

    return SuccessResponse(data={
        "broker_provider": broker_provider,
        "mcp_required": mcp_required,
        "trading_enabled": settings.TRADING_ENABLED,
        "autonomy_mode": settings.AUTONOMY_MODE,
        "order_submission_mode": settings.ORDER_SUBMISSION_MODE,
        "effective_order_submission_mode": effective_order_submission_mode(),
        "runtime_override_active": runtime_order_override_active(),
        "mcp_connected": mcp_connected,
        "scheduler_running": trading_scheduler.is_running,
        "agent_running": trading_agent._running,
        "last_cycle_time": trading_agent.last_cycle_time.isoformat() if trading_agent.last_cycle_time else None,
        "sse_clients": sse_manager.client_count,
        "environment": settings.ENVIRONMENT,
        "market_open": bool(market_session["is_regular_open"]),
        "domestic_market_open": bool(market_session["is_domestic_open"]),
        "market_session": market_session["code"],
        "market_session_label": market_session["label"],
        "market_session_note": market_session["note"],
        "market_session_auto_trading": bool(market_session["supports_automated_trading"]),
        "market_holiday": market_session["holiday_name"],
        "next_market_open": market_calendar.next_krx_open().strftime("%m/%d %H:%M"),
        "next_market_session": market_session["next_session_at"].strftime("%m/%d %H:%M"),
        "broker_capabilities": {
            "supports_nxt_quotes": bool(broker_capabilities.supports_nxt_quotes),
            "supports_after_hours_orders": bool(broker_capabilities.supports_after_hours_orders),
            "supports_after_hours_automation": bool(broker_capabilities.supports_after_hours_automation),
            "supported_order_sessions": supported_sessions,
        },
        "operations": {
            "broker": broker_ops,
            "news_polling": news_ops,
            "ollama": ollama_ops,
            "orders": order_ops,
            "account_snapshot": account_snapshot_ops,
        },
    })


@router.get("/system/preflight")
async def get_system_preflight(db: AsyncSession = Depends(get_async_db)):
    """장 시작 전 read-only 운영 점검"""
    snapshot = await system_preflight_service.build_snapshot(db)
    return SuccessResponse(data=snapshot)


@router.post("/mcp/reconnect")
async def reconnect_mcp():
    """런타임 MCP 연결 재시도"""
    if not broker_runtime_service.mcp_required:
        detail = {
            "connected": True,
            "mcp_connected": False,
            "message": f"{settings.normalized_broker_provider}는 MCP 재연결이 필요하지 않습니다.",
        }
        await activity_logger.log(
            ActivityType.EVENT, ActivityPhase.PROGRESS,
            "🔌 MCP 재연결 요청 (불필요)",
            detail=detail,
        )
        return SuccessResponse(
            data=detail,
            message="현재 브로커는 MCP를 사용하지 않습니다",
        )

    from trading.mcp_client import mcp_client
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
async def start_scheduler(
    payload: AdminActionConfirmationVerifyRequest | None = Body(default=None),
):
    """런타임 스케줄러 시작"""
    _require_admin_action_confirmation(
        payload,
        action="START_SCHEDULER",
        resource_id="SCHEDULER",
        quantity="ALL",
        always=True,
    )
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
async def stop_scheduler(
    payload: AdminActionConfirmationVerifyRequest | None = Body(default=None),
):
    """런타임 스케줄러 중지"""
    _require_admin_action_confirmation(
        payload,
        action="STOP_SCHEDULER",
        resource_id="SCHEDULER",
        quantity="ALL",
        always=True,
    )
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
async def trigger_agent_cycle(
    payload: AdminActionConfirmationVerifyRequest | None = Body(default=None),
):
    """수동으로 에이전트 사이클 실행"""
    from agent.trading_agent import trading_agent

    _require_admin_action_confirmation(
        payload,
        action="TRIGGER_AGENT_CYCLE",
        resource_id="TRADING_AGENT",
        quantity="ALL",
        always=True,
    )

    await activity_logger.log(
        ActivityType.EVENT, ActivityPhase.PROGRESS,
        "\U0001f3ae 수동 사이클 트리거 (관리자)",
    )

    # 비동기로 실행 (즉시 응답)
    # 장중 종목 분석은 tier 설정을 사용해야 하므로 manual override를 주입하지 않는다.
    asyncio.create_task(trading_agent.run_cycle())
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
        manual_model_override=settings.MANUAL_LLM_MODEL,
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
            manual_model_override=settings.MANUAL_LLM_MODEL,
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
