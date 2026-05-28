"""오버나이트 보유 판정 — 코드 룰 기반 (LLM 폴백용)

LLM Tier1 판정 실패 시 폴백으로 사용된다.
"확실한 위험" 종목만 청산하고 나머지는 보유 유지하는 완화된 기준.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from loguru import logger


@dataclass
class HoldDecision:
    action: str  # "HOLD" | "SELL"
    reason: str


@dataclass(frozen=True)
class HoldExtensionPlan:
    should_record: bool
    can_extend: bool
    current_horizon: str
    next_horizon: str
    current_max_hold_days: int
    extension_until_days: int
    total_hold_days_cap: int
    reason: str


@dataclass(frozen=True)
class HoldExtensionUpdate:
    updated_notes: str
    current_horizon: str
    next_horizon: str
    previous_max_hold_days: int
    extension_until_days: int
    extension_count: int
    reason: str


def evaluate_overnight_hold(
    holding,
    trade_result,
    current_price: float,
    config,
) -> HoldDecision:
    """종목별 오버나이트 HOLD/SELL 판정

    Args:
        holding: account_manager에서 가져온 보유종목 (symbol, avg_buy_price 등)
        trade_result: TradeResult 모델 (미청산 매수 기록). None이면 SELL.
        current_price: 현재가
        config: Settings 인스턴스

    Returns:
        HoldDecision(action="HOLD"|"SELL", reason="...")
    """
    symbol = holding.symbol

    # TradeResult 없음 → 시스템이 매수하지 않은 종목 (보수적 청산)
    if trade_result is None:
        return HoldDecision("SELL", "TradeResult 없음 — 보수적 청산")

    # 손익률 계산
    avg_price = holding.avg_buy_price
    if avg_price <= 0:
        return HoldDecision("SELL", "매입가 정보 없음")

    pnl_rate = (current_price - avg_price) / avg_price * 100

    # 1. 큰 손실 → SELL (소폭 손실은 스윙에서 정상 변동)
    # horizon별 임계값을 사용해 mid-long 매매가 일중 단기 변동에 일찍 청산되지 않도록 한다.
    loss_threshold = _overnight_loss_threshold_pct(trade_result, config)
    if pnl_rate < loss_threshold:
        return HoldDecision(
            "SELL",
            f"손실 과대 ({pnl_rate:+.1f}% < {loss_threshold:.1f}%) — 손절 수준 도달",
        )

    # 2. 최대 보유일 초과 → SELL
    hold_days = _calc_hold_days(trade_result)
    max_days = _get_max_hold_days_for_trade(trade_result, config)
    if hold_days >= max_days:
        return HoldDecision(
            "SELL",
            f"보유 {hold_days}일 ≥ 최대 {max_days}일 — 최대 보유일 초과",
        )

    # 3. AI 신뢰도 매우 낮음 → SELL
    confidence = trade_result.ai_confidence or 0.0
    if confidence < 0.45:
        return HoldDecision(
            "SELL",
            f"AI 신뢰도 {confidence:.2f} < 0.45 — 확신 매우 부족",
        )

    # 4. 목표가 도달 → SELL (익절)
    target_price = trade_result.ai_target_price
    if target_price and target_price > 0 and current_price >= target_price:
        return HoldDecision(
            "SELL",
            f"목표가 도달 (현재 {current_price:,.0f} ≥ 목표 {target_price:,.0f})",
        )

    # 모든 SELL 조건 통과 → HOLD
    target_text = f", 목표 {target_price:,.0f}원" if target_price else ""
    logger.debug(
        "오버나이트 HOLD: {}  수익 {:.1f}%, 신뢰도 {:.2f}, 보유 {}/{}일{}",
        symbol, pnl_rate, confidence, hold_days, max_days, target_text,
    )
    return HoldDecision(
        "HOLD",
        f"수익 {pnl_rate:+.1f}% + 신뢰도 {confidence:.2f} + "
        f"보유 {hold_days}/{max_days}일{target_text}",
    )


def _calc_hold_days(trade_result) -> int:
    """진입일부터 오늘까지 보유일수 계산"""
    from util.time_util import now_kst

    entry_at = trade_result.entry_at or trade_result.created_at
    if not entry_at:
        return 0
    today = now_kst().date()
    entry_date = entry_at.date() if isinstance(entry_at, datetime) else entry_at
    return max(0, (today - entry_date).days)


def _overnight_loss_threshold_pct(trade_result, config) -> float:
    """오버나이트 보유 심사용 손절 임계값을 horizon별로 반환한다.

    이전에는 -3.0%로 하드코딩돼 있어 MID/LONG 매매도 단기 변동에 강제 청산
    되는 문제가 있었다. DEFAULT_STOP_LOSS_PCT_{SHORT,MID,LONG}을 그대로
    사용해 horizon별로 다른 한도를 적용한다.
    """
    horizon = _extract_trade_horizon(trade_result) or _infer_trade_horizon(trade_result)
    horizon_key = str(horizon or "").upper()
    if horizon_key == "SHORT":
        return float(getattr(config, "DEFAULT_STOP_LOSS_PCT_SHORT", -3.0) or -3.0)
    if horizon_key == "LONG":
        return float(getattr(config, "DEFAULT_STOP_LOSS_PCT_LONG", -6.0) or -6.0)
    return float(getattr(config, "DEFAULT_STOP_LOSS_PCT_MID", -4.0) or -4.0)


def _get_max_hold_days_for_trade(trade_result, config) -> int:
    """TradeResult notes의 horizon을 우선해 최대 보유일을 반환한다."""
    strategy_type = getattr(trade_result, "strategy_type", "")
    horizon = _extract_trade_horizon(trade_result)
    extension_until_days = _extract_positive_int(
        _extract_trade_notes_payload(trade_result).get("hold_extension_until_days")
    )
    if horizon:
        base_days = _get_max_hold_days(strategy_type, config, horizon)
    else:
        base_days = _get_max_hold_days(strategy_type, config)

    if extension_until_days is None:
        return base_days
    return max(base_days, min(extension_until_days, _get_total_hold_days_cap(config)))


def _get_max_hold_days(strategy_type: str, config, horizon: str | None = None) -> int:
    """호라이즌 우선, legacy 전략 타입 보조 기준으로 최대 보유일 반환."""
    horizon_key = str(horizon or "").upper()
    if horizon_key == "SHORT":
        return int(getattr(config, "MAX_HOLD_DAYS_SHORT", 5) or 5)
    if horizon_key == "MID":
        return int(getattr(config, "MAX_HOLD_DAYS_MID", 15) or 15)
    if horizon_key == "LONG":
        return int(getattr(config, "MAX_HOLD_DAYS_LONG", 30) or 30)

    if "AGGRESSIVE" in (strategy_type or "").upper():
        return int(getattr(config, "MAX_HOLD_DAYS_AGGRESSIVE", 10) or 10)
    return int(getattr(config, "MAX_HOLD_DAYS_STABLE", 15) or 15)


def _extract_trade_horizon(trade_result) -> str | None:
    payload = _extract_trade_notes_payload(trade_result)
    horizon = str(payload.get("trade_horizon") or "").upper()
    return horizon if horizon in {"SHORT", "MID", "LONG"} else None


def get_hold_extension_status(trade_result, config) -> dict:
    """프롬프트/로그용 보유 연장 상태를 반환한다."""
    payload = _extract_trade_notes_payload(trade_result)
    current_horizon = _extract_trade_horizon(trade_result) or _infer_trade_horizon(trade_result)
    extension_until_days = _extract_positive_int(payload.get("hold_extension_until_days"))
    extension_count = _extract_nonnegative_int(payload.get("hold_extension_count")) or 0
    return {
        "trade_horizon": current_horizon,
        "hold_extension_count": extension_count,
        "hold_extension_until_days": extension_until_days,
        "hold_extension_total_cap_days": _get_total_hold_days_cap(config),
    }


def plan_hold_extension(trade_result, config, hold_days: int) -> HoldExtensionPlan:
    """LLM EXTEND 판정이 실제 보유 한도 연장으로 기록 가능한지 계산한다."""
    current_horizon = _extract_trade_horizon(trade_result) or _infer_trade_horizon(trade_result)
    current_max_days = _get_max_hold_days_for_trade(trade_result, config)
    total_cap_days = _get_total_hold_days_cap(config)
    normalized_hold_days = max(int(hold_days or 0), 0)

    if normalized_hold_days < current_max_days:
        return HoldExtensionPlan(
            should_record=False,
            can_extend=True,
            current_horizon=current_horizon,
            next_horizon=current_horizon,
            current_max_hold_days=current_max_days,
            extension_until_days=current_max_days,
            total_hold_days_cap=total_cap_days,
            reason="아직 최대보유일에 도달하지 않아 별도 연장 기록 없이 HOLD 처리",
        )

    if current_max_days >= total_cap_days:
        return HoldExtensionPlan(
            should_record=True,
            can_extend=False,
            current_horizon=current_horizon,
            next_horizon=current_horizon,
            current_max_hold_days=current_max_days,
            extension_until_days=current_max_days,
            total_hold_days_cap=total_cap_days,
            reason=f"총 보유 상한 {total_cap_days}일 도달",
        )

    if current_horizon == "SHORT":
        next_horizon = "MID"
        extension_until_days = _get_max_hold_days("", config, next_horizon)
    elif current_horizon == "MID":
        next_horizon = "LONG"
        extension_until_days = _get_max_hold_days("", config, next_horizon)
    else:
        next_horizon = "LONG"
        step_days = _get_extension_step_days(config)
        extension_until_days = max(current_max_days, normalized_hold_days) + step_days

    extension_until_days = min(max(extension_until_days, current_max_days), total_cap_days)
    if extension_until_days <= current_max_days:
        return HoldExtensionPlan(
            should_record=True,
            can_extend=False,
            current_horizon=current_horizon,
            next_horizon=next_horizon,
            current_max_hold_days=current_max_days,
            extension_until_days=current_max_days,
            total_hold_days_cap=total_cap_days,
            reason=f"연장 후 한도가 기존 한도 {current_max_days}일을 넘지 못함",
        )

    return HoldExtensionPlan(
        should_record=True,
        can_extend=True,
        current_horizon=current_horizon,
        next_horizon=next_horizon,
        current_max_hold_days=current_max_days,
        extension_until_days=extension_until_days,
        total_hold_days_cap=total_cap_days,
        reason=(
            f"{current_horizon} {current_max_days}일 심사 통과 → "
            f"{next_horizon} {extension_until_days}일까지 연장"
        ),
    )


def apply_hold_extension_decision(
    trade_result,
    *,
    decision: dict,
    hold_days: int,
    config,
    source: str = "LLM",
    reviewed_at: datetime | None = None,
) -> HoldExtensionUpdate | None:
    """EXTEND 판정을 TradeResult.notes 업데이트 문자열로 변환한다.

    반환값이 None이면 아직 심사 시점이 아니어서 보유는 유지하되 notes는 바꾸지 않는다.
    """
    plan = plan_hold_extension(trade_result, config, hold_days)
    if not plan.should_record:
        return None
    if not plan.can_extend:
        raise ValueError(plan.reason)

    payload, suffix = _extract_trade_notes_payload_and_suffix(trade_result)
    extension_count = (_extract_nonnegative_int(payload.get("hold_extension_count")) or 0) + 1
    reason = str(decision.get("reason") or plan.reason).strip()[:500]
    confidence = _safe_float(decision.get("confidence"), 0.0)
    reviewed = reviewed_at or datetime.now()

    history = payload.get("hold_extension_history")
    if not isinstance(history, list):
        history = []
    history.append({
        "at": reviewed.isoformat(),
        "source": str(source or "LLM").upper(),
        "from_horizon": plan.current_horizon,
        "to_horizon": plan.next_horizon,
        "hold_days": int(hold_days or 0),
        "previous_max_hold_days": plan.current_max_hold_days,
        "extension_until_days": plan.extension_until_days,
        "total_hold_days_cap": plan.total_hold_days_cap,
        "confidence": confidence,
        "reason": reason,
    })

    payload["trade_horizon"] = plan.next_horizon
    payload["hold_extension_count"] = extension_count
    payload["hold_extension_until_days"] = plan.extension_until_days
    payload["hold_extension_total_cap_days"] = plan.total_hold_days_cap
    payload["hold_extension_last_reviewed_at"] = reviewed.isoformat()
    payload["hold_extension_last_source"] = str(source or "LLM").upper()
    payload["hold_extension_last_reason"] = reason
    payload["hold_extension_last_confidence"] = confidence
    payload["hold_extension_history"] = history[-10:]

    updated_notes = _encode_trade_notes_payload(payload, suffix)
    return HoldExtensionUpdate(
        updated_notes=updated_notes,
        current_horizon=plan.current_horizon,
        next_horizon=plan.next_horizon,
        previous_max_hold_days=plan.current_max_hold_days,
        extension_until_days=plan.extension_until_days,
        extension_count=extension_count,
        reason=reason,
    )


def _extract_trade_notes_payload(trade_result) -> dict:
    payload, _suffix = _extract_trade_notes_payload_and_suffix(trade_result)
    return payload


def _extract_trade_notes_payload_and_suffix(trade_result) -> tuple[dict, str]:
    notes = str(getattr(trade_result, "notes", "") or "").strip()
    if not notes:
        return {}, ""

    try:
        payload = json.loads(notes)
    except json.JSONDecodeError:
        try:
            payload, end_index = json.JSONDecoder().raw_decode(notes)
        except json.JSONDecodeError:
            return {}, notes
        suffix = notes[end_index:].strip()
    else:
        suffix = ""

    if not isinstance(payload, dict):
        return {}, suffix
    return dict(payload), suffix


def _encode_trade_notes_payload(payload: dict, suffix: str = "") -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{encoded} {suffix}".strip() if suffix else encoded


def _infer_trade_horizon(trade_result) -> str:
    strategy_type = str(getattr(trade_result, "strategy_type", "") or "").upper()
    if "AGGRESSIVE" in strategy_type:
        return "SHORT"
    return "MID"


def _get_extension_step_days(config) -> int:
    return max(int(getattr(config, "MAX_HOLD_EXTENSION_DAYS", 15) or 15), 1)


def _get_total_hold_days_cap(config) -> int:
    configured = int(getattr(config, "MAX_HOLD_TOTAL_DAYS", 60) or 60)
    long_days = int(getattr(config, "MAX_HOLD_DAYS_LONG", 30) or 30)
    return max(configured, long_days)


def _extract_positive_int(value) -> int | None:
    parsed = _extract_nonnegative_int(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _extract_nonnegative_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
