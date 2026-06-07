"""주간 캘리브레이션·IC 검증 잡.

매주 금요일 장 마감 후 자동 실행돼:
- LLM 신뢰도 Platt scaling 보정 (Brier/ECE 비교)
- Pre-LLM 결정적 지표의 Information Coefficient (Pearson/Spearman/t-stat)
를 계산하고 활동 로그에 요약을 남긴다. 전체 결과는 runtime/reports/에
weekly_review_<YYYYMMDD>.json 으로 저장한다.

스크립트 모듈(`scripts/analyze_*.py`)의 헬퍼를 그대로 import 해 동일한
계산 로직을 쓴다. 자동 잡은 화면을 띄우지 않아도 되니 PNG 저장은
생략한다.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

from scripts.analyze_confidence_calibration import (
    bin_samples as calibration_bin_samples,
    brier_score,
    expected_calibration_error,
    fit_platt_scaling,
    apply_calibration,
    load_trade_samples,
)
from scripts.analyze_signal_predictive_power import (
    INDICATOR_KEYS,
    analyze_indicator,
    load_signal_samples,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "runtime" / "reports"
INVERTED_ALERT_MIN_SAMPLE_SIZE = 30


def _format_summary_message(
    *,
    calibration_payload: dict,
    indicator_payload: list[dict],
) -> str:
    lines: list[str] = ["📊 주간 캘리브레이션·IC 검증 완료"]
    cal = calibration_payload
    if cal.get("sample_count"):
        before = cal.get("brier_score_before")
        after = cal.get("brier_score_after")
        ece_before = cal.get("ece_before")
        ece_after = cal.get("ece_after")
        lines.append(
            f"  · 신뢰도 표본 {cal['sample_count']}건 / Brier {before:.4f}→{after:.4f}"
            if before is not None and after is not None
            else f"  · 신뢰도 표본 {cal['sample_count']}건"
        )
        if ece_before is not None and ece_after is not None:
            lines.append(f"  · ECE {ece_before:.4f} → {ece_after:.4f}")
        thresholds = cal.get("recommended_raw_thresholds") or {}
        threshold_50 = thresholds.get("50pct_calibrated")
        if threshold_50 is not None:
            lines.append(f"  · 권장 raw 신뢰도(보정 후 50% 적중): {threshold_50:.3f}")
    else:
        lines.append("  · 신뢰도 표본 부족 — 분석 건너뜀")

    strong = [
        item for item in indicator_payload
        if item.get("verdict") and (
            "STRONG_POSITIVE" in item["verdict"]
            or "PRACTICAL_POSITIVE" in item["verdict"]
        )
    ]
    inverted = [item for item in indicator_payload if item.get("verdict") and "INVERTED" in item["verdict"]]
    noise = [item for item in indicator_payload if item.get("verdict") and "NOISE" in item["verdict"]]
    constant = [item for item in indicator_payload if item.get("verdict") and "CONSTANT" in item["verdict"]]

    lines.append(
        f"  · 지표 {len(indicator_payload)}종 분석 → "
        f"유효 {len(strong)} · 역방향 {len(inverted)} · 노이즈 {len(noise)} · 상수 {len(constant)}"
    )
    if strong:
        top = ", ".join(item["key"] for item in strong[:3])
        lines.append(f"  · 유효 지표: {top}")
    if inverted:
        names = ", ".join(item["key"] for item in inverted[:3])
        lines.append(f"  · 역방향 검토: {names}")
    return "\n".join(lines)


def _run_calibration_analysis() -> dict:
    samples = load_trade_samples()
    if not samples:
        return {"sample_count": 0}
    win_count = sum(1 for s in samples if s.is_win)
    raw_bins = calibration_bin_samples(samples, n_bins=5)
    raw_brier = brier_score(samples)
    raw_ece = expected_calibration_error(raw_bins)
    payload: dict = {
        "sample_count": len(samples),
        "win_count": win_count,
        "brier_score_before": raw_brier,
        "ece_before": raw_ece,
        "brier_score_after": None,
        "ece_after": None,
        "platt": None,
        "recommended_raw_thresholds": None,
    }
    try:
        params = fit_platt_scaling(samples)
    except ValueError as exc:
        payload["calibration_skipped_reason"] = str(exc)
        return payload
    calibrated = apply_calibration(samples, params)
    calibrated_bins = calibration_bin_samples(calibrated, n_bins=5)
    payload.update(
        brier_score_after=brier_score(calibrated),
        ece_after=expected_calibration_error(calibrated_bins),
        platt={"slope": params.slope, "intercept": params.intercept},
        recommended_raw_thresholds={
            f"{int(target * 100)}pct_calibrated": params.inverse_for_target(target)
            for target in (0.45, 0.50, 0.55, 0.60)
        },
    )
    return payload


def _run_signal_analysis() -> list[dict]:
    samples = load_signal_samples()
    if not samples:
        return []
    rows: list[dict] = []
    for key in INDICATOR_KEYS:
        result = analyze_indicator(samples, key)
        if result is None:
            continue
        rows.append({
            "key": result.key,
            "n": result.n,
            "pearson_ic": result.pearson_ic if math.isfinite(result.pearson_ic) else None,
            "spearman_ic": result.spearman_ic if math.isfinite(result.spearman_ic) else None,
            "t_statistic": result.t_statistic if math.isfinite(result.t_statistic) else None,
            "long_short_spread": (
                result.long_short_spread if math.isfinite(result.long_short_spread) else None
            ),
            "verdict": result.verdict,
        })
    return rows


def _save_report(payload: dict, *, report_dir: Path | None = None) -> Path:
    target_dir = report_dir if report_dir is not None else REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    path = target_dir / f"weekly_review_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _collect_inverted_indicators(
    indicator_payload: list[dict],
    *,
    min_sample_size: int = INVERTED_ALERT_MIN_SAMPLE_SIZE,
) -> list[dict]:
    """verdict 가 INVERTED 인 지표만 추출 — 별도 ALERT 로 노출하기 위함."""
    inverted: list[dict] = []
    for item in indicator_payload:
        verdict = str(item.get("verdict") or "")
        n = int(item.get("n") or 0)
        if "INVERTED" in verdict and n >= min_sample_size:
            inverted.append({
                "key": item.get("key"),
                "spearman_ic": item.get("spearman_ic"),
                "t_statistic": item.get("t_statistic"),
                "verdict": verdict,
                "n": n,
            })
    return inverted


def _collect_watchlist_inverted_indicators(
    indicator_payload: list[dict],
    *,
    min_sample_size: int = INVERTED_ALERT_MIN_SAMPLE_SIZE,
) -> list[dict]:
    """소표본 역방향 후보를 별도 관찰 대상으로 남긴다."""
    watchlist: list[dict] = []
    for item in indicator_payload:
        verdict = str(item.get("verdict") or "")
        n = int(item.get("n") or 0)
        if "INVERTED" in verdict and 0 < n < min_sample_size:
            watchlist.append({
                "key": item.get("key"),
                "spearman_ic": item.get("spearman_ic"),
                "t_statistic": item.get("t_statistic"),
                "verdict": verdict,
                "n": n,
                "min_sample_size": min_sample_size,
            })
    return watchlist


async def calibration_review_job() -> dict:
    """매주 금요일 장 마감 후 한 번 호출되는 진입점."""
    from trading.enums import ActivityPhase, ActivityType
    from services.activity_logger import activity_logger

    logger.debug("주간 캘리브레이션 검증 시작")
    try:
        calibration_payload = _run_calibration_analysis()
        indicator_payload = _run_signal_analysis()
        payload = {
            "generated_at": datetime.now().isoformat(),
            "calibration": calibration_payload,
            "indicators": indicator_payload,
        }
        report_path = _save_report(payload)
        summary = _format_summary_message(
            calibration_payload=calibration_payload,
            indicator_payload=indicator_payload,
        )
        await activity_logger.log(
            ActivityType.SCHEDULE,
            ActivityPhase.PROGRESS,
            summary,
            detail={"weekly_review_path": str(report_path)},
        )

        inverted = _collect_inverted_indicators(indicator_payload)
        watchlist_inverted = _collect_watchlist_inverted_indicators(indicator_payload)
        if watchlist_inverted:
            try:
                await activity_logger.log(
                    ActivityType.SCHEDULE,
                    ActivityPhase.PROGRESS,
                    "Pre-LLM 게이트 소표본 역방향 후보 관찰",
                    detail={
                        "watchlist_inverted_indicators": watchlist_inverted,
                        "min_sample_size": INVERTED_ALERT_MIN_SAMPLE_SIZE,
                        "weekly_review_path": str(report_path),
                    },
                )
            except Exception as inner_exc:  # noqa: BLE001
                logger.warning("소표본 역방향 후보 로깅 실패: {}", str(inner_exc))
        if inverted:
            names = ", ".join(item.get("key") or "?" for item in inverted)
            alert_message = (
                f"⚠️ Pre-LLM 게이트 역방향 지표 {len(inverted)}건 감지 — {names}. "
                "부호 뒤집어 사용하거나 게이트에서 제외 검토 필요."
            )
            try:
                await activity_logger.log(
                    ActivityType.SCHEDULE,
                    ActivityPhase.ERROR,
                    alert_message,
                    detail={
                        "inverted_indicators": inverted,
                        "weekly_review_path": str(report_path),
                    },
                )
            except Exception as inner_exc:  # noqa: BLE001
                logger.warning("역방향 지표 ALERT 로깅 실패: {}", str(inner_exc))

        logger.info("주간 캘리브레이션 검증 완료 — {}", report_path)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.error("주간 캘리브레이션 검증 실패: {}", str(exc))
        try:
            await activity_logger.log(
                ActivityType.SCHEDULE,
                ActivityPhase.ERROR,
                f"❌ 주간 캘리브레이션 검증 실패: {str(exc)[:120]}",
            )
        except Exception:  # noqa: BLE001
            pass
        return {"error": str(exc)}
