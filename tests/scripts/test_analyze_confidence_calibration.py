"""캘리브레이션 분석 헬퍼 단위 테스트."""
from __future__ import annotations

import pytest

from scripts.analyze_confidence_calibration import (
    TradeSample,
    bin_samples,
    brier_score,
    expected_calibration_error,
)


def test_brier_score_perfect_predictions():
    samples = [
        TradeSample(confidence=1.0, is_win=True),
        TradeSample(confidence=0.0, is_win=False),
    ]
    assert brier_score(samples) == pytest.approx(0.0)


def test_brier_score_worst_predictions():
    samples = [
        TradeSample(confidence=1.0, is_win=False),
        TradeSample(confidence=0.0, is_win=True),
    ]
    assert brier_score(samples) == pytest.approx(1.0)


def test_brier_score_overconfident_random_outcomes():
    # 신뢰도 0.7로 모두 예측했지만 win rate 0.5인 경우
    samples = [TradeSample(confidence=0.7, is_win=(i % 2 == 0)) for i in range(10)]
    # MSE = mean[(0.7-1)^2 = 0.09, (0.7-0)^2 = 0.49] = 0.29
    assert brier_score(samples) == pytest.approx(0.29)


def test_brier_score_empty_returns_nan():
    import math
    assert math.isnan(brier_score([]))


def test_bin_samples_distributes_into_correct_buckets():
    samples = [
        TradeSample(confidence=0.1, is_win=False),  # bin 0
        TradeSample(confidence=0.25, is_win=True),  # bin 1
        TradeSample(confidence=0.55, is_win=True),  # bin 2
        TradeSample(confidence=0.65, is_win=False),  # bin 3
        TradeSample(confidence=0.85, is_win=True),  # bin 4
    ]
    bins = bin_samples(samples, n_bins=5)
    assert [b.n for b in bins] == [1, 1, 1, 1, 1]
    assert bins[0].samples[0].confidence == pytest.approx(0.1)
    assert bins[4].samples[0].is_win is True


def test_bin_samples_handles_edge_value_one():
    """confidence == 1.0이 마지막 구간으로 들어가야 한다 (idx 클램핑)."""
    samples = [TradeSample(confidence=1.0, is_win=True)]
    bins = bin_samples(samples, n_bins=5)
    assert bins[4].n == 1


def test_bin_samples_requires_at_least_two_bins():
    with pytest.raises(ValueError):
        bin_samples([], n_bins=1)


def test_expected_calibration_error_perfect_calibration_returns_zero():
    samples = [
        TradeSample(confidence=0.3, is_win=False),
        TradeSample(confidence=0.3, is_win=False),
        TradeSample(confidence=0.3, is_win=True),  # bin 1 [0.2-0.4]: mean conf 0.3, win rate 1/3 = 0.333
        TradeSample(confidence=0.7, is_win=True),
        TradeSample(confidence=0.7, is_win=True),
        TradeSample(confidence=0.7, is_win=False),  # bin 3 [0.6-0.8]: mean conf 0.7, win rate 2/3 = 0.667
    ]
    bins = bin_samples(samples, n_bins=5)
    # 두 빈 모두 mean conf와 win rate 차이 ~0.033 정도 — 거의 잘 캘리브레이션
    ece = expected_calibration_error(bins)
    assert ece < 0.05


def test_expected_calibration_error_overconfident_model_high():
    samples = [TradeSample(confidence=0.9, is_win=False) for _ in range(10)]
    bins = bin_samples(samples, n_bins=5)
    ece = expected_calibration_error(bins)
    # 모두 0.9 신뢰도였지만 0건 승 → 빈 mean 0.9, win rate 0.0 → diff 0.9
    assert ece == pytest.approx(0.9)


def test_expected_calibration_error_empty_returns_nan():
    import math
    assert math.isnan(expected_calibration_error([]))
