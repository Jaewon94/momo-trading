"""주간 캘리브레이션 권장값을 trading_rules PARAM_OVERRIDE 로 1-click 적용.

Why:
    weekly_calibration_review 가 Platt scaling 결과로 `recommended_raw_thresholds`
    를 산출하지만, 그동안 적용은 수동이었다. 측정-자동, 적용-수동 비대칭을
    없애 보정 사이클을 닫는다.

How:
    GET  → 최신 weekly_review_*.json 에서 50%-calibrated 임계값을 읽어
            현재 활성 min_confidence 규칙과 비교한 권장 페이로드를 반환한다.
    POST → 권장값을 trading_rule(rule_type=PARAM_OVERRIDE, param_name=min_confidence)
            로 활성화한다. 기존 min_confidence 규칙은 비활성화.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from loguru import logger
from sqlalchemy import select, update

from core.database import AsyncSessionLocal
from models.trading_rule import TradingRule
from util.time_util import now_kst

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "runtime" / "reports"

# trading_rules SAFETY_BOUNDS["min_confidence"] 와 일치시킨다.
MIN_CONFIDENCE_FLOOR = 0.50
MIN_CONFIDENCE_CEIL = 0.75

# 권장 적용 기본 만료 (주간 검증 주기 = 7일과 동일)
DEFAULT_EXPIRES_DAYS = 7


@dataclass(frozen=True)
class CalibrationRecommendation:
    """현재 min_confidence vs 권장값 비교 페이로드."""
    available: bool
    sample_count: int
    current_min_confidence: float | None
    current_source: str  # "ACTIVE_RULE" | "DEFAULT"
    recommended_min_confidence: float | None
    target_calibrated_win_rate: float
    source_report_path: str | None
    source_report_date: str | None
    brier_score_before: float | None
    brier_score_after: float | None
    ece_before: float | None
    ece_after: float | None
    delta: float | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class CalibrationRecommendationService:
    """주간 캘리브레이션 리포트 → 권장 min_confidence → trading_rule 적용."""

    DEFAULT_BASELINE_MIN_CONFIDENCE = 0.65  # 활성 규칙 없을 때 표시용 기본값

    def __init__(self, report_dir: Path = REPORT_DIR) -> None:
        self._report_dir = report_dir

    # ── 권장값 조회 ─────────────────────────────────────────────
    async def latest_recommendation(self) -> CalibrationRecommendation:
        current, current_source = await self._current_effective_min_confidence()
        latest_path = self._find_latest_weekly_review()
        if not latest_path:
            return CalibrationRecommendation(
                available=False,
                sample_count=0,
                current_min_confidence=current,
                current_source=current_source,
                recommended_min_confidence=None,
                target_calibrated_win_rate=0.50,
                source_report_path=None,
                source_report_date=None,
                brier_score_before=None,
                brier_score_after=None,
                ece_before=None,
                ece_after=None,
                delta=None,
                reason="weekly_review 리포트 없음 — 금요일 16:10 자동 검증 이후 다시 조회",
            )
        try:
            payload = json.loads(latest_path.read_text())
        except (OSError, ValueError) as exc:
            return CalibrationRecommendation(
                available=False,
                sample_count=0,
                current_min_confidence=current,
                current_source=current_source,
                recommended_min_confidence=None,
                target_calibrated_win_rate=0.50,
                source_report_path=str(latest_path),
                source_report_date=None,
                brier_score_before=None,
                brier_score_after=None,
                ece_before=None,
                ece_after=None,
                delta=None,
                reason=f"리포트 파싱 실패: {exc}",
            )

        cal = payload.get("calibration") or {}
        sample_count = int(cal.get("sample_count") or 0)
        thresholds = cal.get("recommended_raw_thresholds") or {}
        raw_recommended = thresholds.get("50pct_calibrated")
        brier_before = cal.get("brier_score_before")
        brier_after = cal.get("brier_score_after")
        ece_before = cal.get("ece_before")
        ece_after = cal.get("ece_after")

        if raw_recommended is None:
            return CalibrationRecommendation(
                available=False,
                sample_count=sample_count,
                current_min_confidence=current,
                current_source=current_source,
                recommended_min_confidence=None,
                target_calibrated_win_rate=0.50,
                source_report_path=str(latest_path),
                source_report_date=payload.get("generated_at"),
                brier_score_before=brier_before,
                brier_score_after=brier_after,
                ece_before=ece_before,
                ece_after=ece_after,
                delta=None,
                reason="Platt 적합 실패 또는 표본 부족 — 권장 임계값 없음",
            )

        clamped = max(MIN_CONFIDENCE_FLOOR, min(MIN_CONFIDENCE_CEIL, float(raw_recommended)))
        clamp_note = ""
        if abs(clamped - float(raw_recommended)) > 1e-6:
            clamp_note = (
                f" (안전 범위 {MIN_CONFIDENCE_FLOOR:.2f}~{MIN_CONFIDENCE_CEIL:.2f}로 클램핑)"
            )
        delta = round(clamped - current, 4) if current is not None else None
        reason_parts = [
            f"50% 보정 승률 raw 임계값 권장{clamp_note}",
            f"표본 {sample_count}건",
        ]
        if brier_before is not None and brier_after is not None:
            reason_parts.append(f"Brier {brier_before:.4f}→{brier_after:.4f}")
        if ece_before is not None and ece_after is not None:
            reason_parts.append(f"ECE {ece_before:.4f}→{ece_after:.4f}")
        reason = " · ".join(reason_parts)

        return CalibrationRecommendation(
            available=True,
            sample_count=sample_count,
            current_min_confidence=current,
            current_source=current_source,
            recommended_min_confidence=round(clamped, 4),
            target_calibrated_win_rate=0.50,
            source_report_path=str(latest_path),
            source_report_date=payload.get("generated_at"),
            brier_score_before=brier_before,
            brier_score_after=brier_after,
            ece_before=ece_before,
            ece_after=ece_after,
            delta=delta,
            reason=reason,
        )

    # ── 권장값 적용 ─────────────────────────────────────────────
    async def apply_recommendation(self, *, expires_days: int = DEFAULT_EXPIRES_DAYS) -> dict:
        """주간 권장 min_confidence를 trading_rules PARAM_OVERRIDE 로 활성화."""
        rec = await self.latest_recommendation()
        if not rec.available or rec.recommended_min_confidence is None:
            return {"applied": False, "reason": rec.reason}

        expires_days_clamped = max(1, min(14, int(expires_days)))
        now = now_kst()
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(TradingRule)
                .where(
                    TradingRule.param_name == "min_confidence",
                    TradingRule.is_active.is_(True),
                )
                .values(is_active=False)
            )
            rule = TradingRule(
                rule_type="PARAM_OVERRIDE",
                strategy_type="ALL",
                param_name="min_confidence",
                param_value=float(rec.recommended_min_confidence),
                source="CALIBRATION_REVIEW",
                reason=rec.reason[:500],
                priority="HIGH",
                is_active=True,
                expires_at=now + timedelta(days=expires_days_clamped),
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

        logger.info(
            "[Calibration] min_confidence {} → {} 적용 (rule_id={}, expires={})",
            rec.current_min_confidence,
            rec.recommended_min_confidence,
            rule.id,
            rule.expires_at.isoformat(),
        )
        return {
            "applied": True,
            "rule_id": rule.id,
            "previous_min_confidence": rec.current_min_confidence,
            "applied_min_confidence": rec.recommended_min_confidence,
            "expires_at": rule.expires_at.isoformat(),
            "reason": rec.reason,
        }

    # ── 헬퍼 ────────────────────────────────────────────────────
    async def _current_effective_min_confidence(self) -> tuple[float, str]:
        """활성 min_confidence 규칙이 있으면 그 값, 없으면 기본 베이스라인."""
        now = now_kst()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TradingRule)
                .where(
                    TradingRule.param_name == "min_confidence",
                    TradingRule.is_active.is_(True),
                    TradingRule.expires_at > now,
                )
                .order_by(TradingRule.created_at.desc())
                .limit(1)
            )
            rule = result.scalars().first()
        if rule is not None:
            return float(rule.param_value), "ACTIVE_RULE"
        return self.DEFAULT_BASELINE_MIN_CONFIDENCE, "DEFAULT"

    def _find_latest_weekly_review(self) -> Path | None:
        if not self._report_dir.exists():
            return None
        files = sorted(self._report_dir.glob("weekly_review_*.json"))
        return files[-1] if files else None


calibration_recommendation_service = CalibrationRecommendationService()
