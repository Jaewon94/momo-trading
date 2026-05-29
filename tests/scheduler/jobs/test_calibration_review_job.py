"""주간 캘리브레이션 검증 잡 단위 테스트."""
from __future__ import annotations

import json

import pytest

from scheduler.jobs import calibration_review_job as job_module
from scripts.analyze_confidence_calibration import TradeSample as CalibTradeSample
from scripts.analyze_signal_predictive_power import SignalSample


def test_format_summary_includes_calibration_and_indicator_breakdown():
    calibration = {
        "sample_count": 100,
        "brier_score_before": 0.30,
        "brier_score_after": 0.20,
        "ece_before": 0.21,
        "ece_after": 0.01,
        "recommended_raw_thresholds": {"50pct_calibrated": 0.755},
    }
    indicators = [
        {"key": "edge_to_cost_ratio", "verdict": "STRONG_POSITIVE"},
        {"key": "estimated_edge_bps", "verdict": "INVERTED"},
        {"key": "chart_signal_confidence", "verdict": "NOISE (|IC| < 0.02)"},
        {"key": "news_negative_pressure", "verdict": "CONSTANT (전 표본 동일 값)"},
    ]
    msg = job_module._format_summary_message(
        calibration_payload=calibration,
        indicator_payload=indicators,
    )
    assert "주간 캘리브레이션·IC 검증 완료" in msg
    assert "100건" in msg
    assert "0.3000→0.2000" in msg or "0.30" in msg or "Brier" in msg
    assert "0.755" in msg
    # 라벨별 카운트가 본문에 표시되는지
    assert "유효 1" in msg
    assert "역방향 1" in msg
    assert "노이즈 1" in msg
    assert "상수 1" in msg
    assert "edge_to_cost_ratio" in msg
    assert "estimated_edge_bps" in msg


def test_format_summary_handles_empty_calibration():
    msg = job_module._format_summary_message(
        calibration_payload={"sample_count": 0},
        indicator_payload=[],
    )
    assert "신뢰도 표본 부족" in msg
    assert "지표 0종 분석" in msg


def test_save_report_writes_json_with_payload(tmp_path):
    payload = {"calibration": {"sample_count": 5}, "indicators": []}
    saved = job_module._save_report(payload, report_dir=tmp_path)
    assert saved.exists()
    parsed = json.loads(saved.read_text())
    assert parsed == payload
    # 파일 이름이 weekly_review_YYYYMMDD.json 형태
    assert saved.name.startswith("weekly_review_")
    assert saved.suffix == ".json"


def test_run_calibration_analysis_returns_zero_payload_when_no_samples(monkeypatch):
    monkeypatch.setattr(job_module, "load_trade_samples", lambda: [])
    payload = job_module._run_calibration_analysis()
    assert payload == {"sample_count": 0}


def test_run_calibration_analysis_includes_platt_params_for_mixed_outcomes(monkeypatch):
    # 20건 표본 (10승 10패) → Platt 적합 가능
    samples = []
    for i in range(20):
        samples.append(CalibTradeSample(confidence=0.7, is_win=(i % 2 == 0)))
    monkeypatch.setattr(job_module, "load_trade_samples", lambda: samples)
    payload = job_module._run_calibration_analysis()
    assert payload["sample_count"] == 20
    assert payload["brier_score_before"] is not None
    assert payload["brier_score_after"] is not None
    assert payload["platt"] is not None
    assert "slope" in payload["platt"]
    assert payload["recommended_raw_thresholds"]["50pct_calibrated"] is not None


def test_run_calibration_analysis_skips_platt_when_class_missing(monkeypatch):
    samples = [CalibTradeSample(confidence=0.6, is_win=True) for _ in range(10)]
    monkeypatch.setattr(job_module, "load_trade_samples", lambda: samples)
    payload = job_module._run_calibration_analysis()
    assert payload["sample_count"] == 10
    assert payload["platt"] is None
    assert payload["recommended_raw_thresholds"] is None
    assert "calibration_skipped_reason" in payload


def test_run_signal_analysis_filters_constants_and_returns_indicator_rows(monkeypatch):
    # 20건 표본: x_strong은 return과 강한 양의 상관, x_const는 변동 없음
    samples = []
    for i in range(20):
        ret = float(i - 10)  # -10..9
        samples.append(SignalSample(
            return_pct=ret,
            is_win=ret > 0,
            indicators={"fast_gate_score": float(i), "x_const": 0.5},
        ))
    monkeypatch.setattr(job_module, "load_signal_samples", lambda: samples)
    monkeypatch.setattr(job_module, "INDICATOR_KEYS", ("fast_gate_score", "x_const"))
    rows = job_module._run_signal_analysis()
    keys = {row["key"] for row in rows}
    assert "fast_gate_score" in keys
    assert "x_const" in keys
    strong_row = next(row for row in rows if row["key"] == "fast_gate_score")
    assert strong_row["spearman_ic"] is not None
    assert strong_row["spearman_ic"] > 0.9
    const_row = next(row for row in rows if row["key"] == "x_const")
    assert "CONSTANT" in const_row["verdict"]


@pytest.mark.asyncio
async def test_calibration_review_job_logs_summary_and_returns_payload(monkeypatch, tmp_path):
    captured_logs: list[tuple[str, str, str]] = []

    class _FakeLogger:
        async def log(self, activity_type, phase, summary, **kwargs):
            captured_logs.append((str(activity_type), str(phase), summary))

    fake_logger = _FakeLogger()
    monkeypatch.setattr(
        "services.activity_logger.activity_logger", fake_logger
    )
    monkeypatch.setattr(job_module, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(job_module, "_run_calibration_analysis", lambda: {
        "sample_count": 50,
        "brier_score_before": 0.29,
        "brier_score_after": 0.24,
        "ece_before": 0.21,
        "ece_after": 0.01,
        "recommended_raw_thresholds": {"50pct_calibrated": 0.75},
    })
    monkeypatch.setattr(job_module, "_run_signal_analysis", lambda: [
        {"key": "fast_gate_score", "verdict": "STRONG_POSITIVE"},
    ])

    result = await job_module.calibration_review_job()
    assert result["calibration"]["sample_count"] == 50
    assert any("주간 캘리브레이션·IC 검증 완료" in line for _, _, line in captured_logs)
    # weekly_review 파일이 tmp_path에 저장돼야 한다.
    files = list(tmp_path.glob("weekly_review_*.json"))
    assert len(files) == 1
