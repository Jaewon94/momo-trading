"""캘리브레이션 권장값 서비스 단위 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.calibration_recommendation_service import (
    MIN_CONFIDENCE_CEIL,
    MIN_CONFIDENCE_FLOOR,
    CalibrationRecommendationService,
)


def _write_weekly_review(directory: Path, name: str, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


@pytest.mark.asyncio
async def test_latest_recommendation_returns_unavailable_when_no_reports(tmp_path):
    service = CalibrationRecommendationService(report_dir=tmp_path)

    async def fake_current():
        return 0.65, "DEFAULT"

    service._current_effective_min_confidence = fake_current  # type: ignore[assignment]
    rec = await service.latest_recommendation()
    assert rec.available is False
    assert rec.current_min_confidence == 0.65
    assert rec.recommended_min_confidence is None
    assert "weekly_review" in rec.reason


@pytest.mark.asyncio
async def test_latest_recommendation_returns_recommended_threshold(tmp_path):
    payload = {
        "generated_at": "2026-05-29T16:10:00",
        "calibration": {
            "sample_count": 92,
            "brier_score_before": 0.291,
            "brier_score_after": 0.246,
            "ece_before": 0.211,
            "ece_after": 0.011,
            "recommended_raw_thresholds": {
                "50pct_calibrated": 0.6234,
                "55pct_calibrated": 0.7100,
            },
        },
    }
    _write_weekly_review(tmp_path, "weekly_review_20260529.json", payload)
    service = CalibrationRecommendationService(report_dir=tmp_path)

    async def fake_current():
        return 0.55, "ACTIVE_RULE"

    service._current_effective_min_confidence = fake_current  # type: ignore[assignment]
    rec = await service.latest_recommendation()
    assert rec.available is True
    assert rec.sample_count == 92
    assert rec.current_min_confidence == 0.55
    assert rec.current_source == "ACTIVE_RULE"
    assert rec.recommended_min_confidence == pytest.approx(0.6234, rel=1e-4)
    assert rec.delta == pytest.approx(0.0734, rel=1e-3)
    assert "Brier" in rec.reason
    assert "표본 92건" in rec.reason


@pytest.mark.asyncio
async def test_latest_recommendation_clamps_to_safety_bounds(tmp_path):
    payload = {
        "generated_at": "2026-05-29T16:10:00",
        "calibration": {
            "sample_count": 50,
            "recommended_raw_thresholds": {"50pct_calibrated": 0.999},
        },
    }
    _write_weekly_review(tmp_path, "weekly_review_20260529.json", payload)
    service = CalibrationRecommendationService(report_dir=tmp_path)

    async def fake_current():
        return 0.65, "DEFAULT"

    service._current_effective_min_confidence = fake_current  # type: ignore[assignment]
    rec = await service.latest_recommendation()
    assert rec.available is True
    assert rec.recommended_min_confidence == MIN_CONFIDENCE_CEIL
    assert "클램핑" in rec.reason


@pytest.mark.asyncio
async def test_latest_recommendation_picks_most_recent_file(tmp_path):
    older = {
        "generated_at": "2026-05-22T16:10:00",
        "calibration": {
            "sample_count": 20,
            "recommended_raw_thresholds": {"50pct_calibrated": 0.55},
        },
    }
    newer = {
        "generated_at": "2026-05-29T16:10:00",
        "calibration": {
            "sample_count": 92,
            "recommended_raw_thresholds": {"50pct_calibrated": 0.62},
        },
    }
    _write_weekly_review(tmp_path, "weekly_review_20260522.json", older)
    _write_weekly_review(tmp_path, "weekly_review_20260529.json", newer)
    service = CalibrationRecommendationService(report_dir=tmp_path)

    async def fake_current():
        return 0.65, "DEFAULT"

    service._current_effective_min_confidence = fake_current  # type: ignore[assignment]
    rec = await service.latest_recommendation()
    assert rec.sample_count == 92
    assert rec.recommended_min_confidence == pytest.approx(0.62, rel=1e-4)


@pytest.mark.asyncio
async def test_latest_recommendation_handles_platt_failure(tmp_path):
    payload = {
        "generated_at": "2026-05-29T16:10:00",
        "calibration": {
            "sample_count": 5,
            "brier_score_before": 0.30,
            "ece_before": 0.20,
            "calibration_skipped_reason": "class missing",
        },
    }
    _write_weekly_review(tmp_path, "weekly_review_20260529.json", payload)
    service = CalibrationRecommendationService(report_dir=tmp_path)

    async def fake_current():
        return 0.65, "DEFAULT"

    service._current_effective_min_confidence = fake_current  # type: ignore[assignment]
    rec = await service.latest_recommendation()
    assert rec.available is False
    assert rec.recommended_min_confidence is None
    assert "Platt" in rec.reason or "임계값" in rec.reason


def test_safety_bounds_match_trading_rules_module():
    """SAFETY_BOUNDS와 일치하지 않으면 적용 시 클램핑 충돌."""
    from analysis.feedback.trading_rules import SAFETY_BOUNDS

    lo, hi = SAFETY_BOUNDS["min_confidence"]
    assert lo == pytest.approx(MIN_CONFIDENCE_FLOOR)
    assert hi == pytest.approx(MIN_CONFIDENCE_CEIL)
