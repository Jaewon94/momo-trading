"""Pre-LLM 게이트 IC 분석 헬퍼 단위 테스트."""
from __future__ import annotations

import math

import pytest

from scripts.analyze_signal_predictive_power import (
    SignalSample,
    analyze_indicator,
    classify_verdict,
    is_monotonic_decreasing,
    is_monotonic_increasing,
    pearson_correlation,
    quintile_returns,
    spearman_correlation,
    t_statistic_of_correlation,
    _parse_notes_json,
    _rank,
)


# ─── 통계 헬퍼 ───────────────────────────────────────────

def test_pearson_perfect_positive_correlation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    assert pearson_correlation(xs, ys) == pytest.approx(1.0)


def test_pearson_perfect_negative_correlation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    assert pearson_correlation(xs, ys) == pytest.approx(-1.0)


def test_pearson_no_correlation_returns_near_zero():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [3.0, 3.0, 3.0, 3.0, 3.0]
    # ys 변동 0 → nan
    assert math.isnan(pearson_correlation(xs, ys))


def test_pearson_insufficient_data():
    assert math.isnan(pearson_correlation([1.0], [2.0]))


def test_rank_handles_ties_with_average():
    # 1, 2, 2, 4 → 1, 2.5, 2.5, 4
    ranks = _rank([1.0, 2.0, 2.0, 4.0])
    assert ranks == [1.0, 2.5, 2.5, 4.0]


def test_spearman_monotonic_nonlinear():
    # 비선형이지만 단조 → Spearman 완벽
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [1.0, 4.0, 9.0, 16.0, 25.0]  # x^2
    assert spearman_correlation(xs, ys) == pytest.approx(1.0)


def test_t_statistic_large_correlation_with_large_sample_significant():
    # IC=0.3, n=100 → t = 0.3 * sqrt(98) / sqrt(0.91) ≈ 3.11
    t = t_statistic_of_correlation(0.3, 100)
    assert t > 2.0


def test_t_statistic_small_correlation_not_significant():
    t = t_statistic_of_correlation(0.01, 50)
    assert abs(t) < 2.0


def test_t_statistic_zero_correlation():
    t = t_statistic_of_correlation(0.0, 100)
    assert t == pytest.approx(0.0)


def test_t_statistic_insufficient_sample():
    assert math.isnan(t_statistic_of_correlation(0.5, 2))


# ─── Quintile 분석 ───────────────────────────────────────

def test_quintile_returns_with_monotonic_data():
    # x 작을수록 y도 작음 → quintile 평균 단조 증가
    xs = list(range(1, 11))
    ys = list(range(1, 11))
    q = quintile_returns(xs, ys, n_quantiles=5)
    assert q == [1.5, 3.5, 5.5, 7.5, 9.5]


def test_quintile_returns_handles_small_sample():
    q = quintile_returns([1.0, 2.0], [10.0, 20.0], n_quantiles=5)
    assert all(math.isnan(v) for v in q)


def test_monotonic_increasing_true():
    assert is_monotonic_increasing([1.0, 2.0, 2.0, 3.0])
    assert not is_monotonic_increasing([1.0, 3.0, 2.0])


def test_monotonic_decreasing_true():
    assert is_monotonic_decreasing([3.0, 2.0, 1.0])
    assert not is_monotonic_decreasing([3.0, 1.0, 2.0])


# ─── Verdict 분류 ────────────────────────────────────────

def test_classify_verdict_strong_positive():
    v = classify_verdict(spearman_ic=0.15, t_stat=3.0, monotonic_inc=True, monotonic_dec=False)
    assert "STRONG_POSITIVE" in v


def test_classify_verdict_inverted_with_monotonic_dec():
    v = classify_verdict(spearman_ic=-0.08, t_stat=-2.5, monotonic_inc=False, monotonic_dec=True)
    assert "INVERTED" in v


def test_classify_verdict_noise_low_ic():
    v = classify_verdict(spearman_ic=0.01, t_stat=0.3, monotonic_inc=False, monotonic_dec=False)
    assert "NOISE" in v


def test_classify_verdict_not_significant_despite_some_ic():
    v = classify_verdict(spearman_ic=0.08, t_stat=1.2, monotonic_inc=False, monotonic_dec=False)
    assert "NOT_SIGNIFICANT" in v


# ─── 통합 ───────────────────────────────────────────────

def test_analyze_indicator_constant_signal_returns_constant_verdict():
    samples = [
        SignalSample(return_pct=1.0, is_win=True, indicators={"x": 0.5}),
        SignalSample(return_pct=-1.0, is_win=False, indicators={"x": 0.5}),
        SignalSample(return_pct=0.5, is_win=True, indicators={"x": 0.5}),
        SignalSample(return_pct=-0.5, is_win=False, indicators={"x": 0.5}),
        SignalSample(return_pct=0.0, is_win=False, indicators={"x": 0.5}),
    ]
    result = analyze_indicator(samples, "x")
    assert result is not None
    assert "CONSTANT" in result.verdict


def test_analyze_indicator_strong_signal_detected():
    # x와 return이 완벽 선형 양의 상관
    samples = [
        SignalSample(return_pct=float(i), is_win=(i > 0), indicators={"x": float(i)})
        for i in range(-5, 6)
    ]
    result = analyze_indicator(samples, "x")
    assert result is not None
    assert result.spearman_ic > 0.9
    assert result.t_statistic > 2.0
    assert "STRONG_POSITIVE" in result.verdict


def test_analyze_indicator_too_few_samples_returns_none():
    samples = [
        SignalSample(return_pct=1.0, is_win=True, indicators={"x": 1.0})
        for _ in range(3)
    ]
    assert analyze_indicator(samples, "x") is None


def test_analyze_indicator_missing_key_returns_none():
    samples = [
        SignalSample(return_pct=1.0, is_win=True, indicators={"y": 1.0})
        for _ in range(10)
    ]
    assert analyze_indicator(samples, "x") is None


# ─── notes JSON 파싱 ──────────────────────────────────────

def test_parse_notes_json_clean():
    parsed = _parse_notes_json('{"a": 1, "b": "two"}')
    assert parsed == {"a": 1, "b": "two"}


def test_parse_notes_json_with_marker_suffix():
    parsed = _parse_notes_json('{"a": 1} | PARTIAL_TAKE_PROFIT_DONE')
    assert parsed == {"a": 1}


def test_parse_notes_json_garbage_returns_none():
    assert _parse_notes_json("not json | something") is None
    assert _parse_notes_json("") is None
    assert _parse_notes_json(None) is None
