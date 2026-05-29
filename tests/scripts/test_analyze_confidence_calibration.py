"""캘리브레이션 분석 헬퍼 단위 테스트."""
from __future__ import annotations

import pytest

from scripts.analyze_confidence_calibration import (
    PlattParams,
    TradeSample,
    apply_calibration,
    bin_samples,
    brier_score,
    expected_calibration_error,
    fit_platt_scaling,
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


def test_platt_params_apply_is_sigmoid():
    # slope=0, intercept=0 → sigmoid(0) = 0.5
    p = PlattParams(slope=0.0, intercept=0.0)
    assert p.apply(0.0) == pytest.approx(0.5)
    assert p.apply(1.0) == pytest.approx(0.5)


def test_platt_params_apply_handles_large_negative_z():
    # 수치 안정성: 큰 음수에서도 0~1 사이
    p = PlattParams(slope=-100.0, intercept=50.0)
    out = p.apply(1.0)
    assert 0.0 <= out <= 1.0


def test_platt_inverse_recovers_target_probability():
    p = PlattParams(slope=2.0, intercept=-1.0)
    raw = p.inverse_for_target(0.6)
    assert raw is not None
    assert p.apply(raw) == pytest.approx(0.6, abs=1e-6)


def test_platt_inverse_rejects_invalid_target():
    p = PlattParams(slope=1.0, intercept=0.0)
    assert p.inverse_for_target(0.0) is None
    assert p.inverse_for_target(1.0) is None


def test_fit_platt_scaling_requires_both_classes():
    only_wins = [TradeSample(confidence=0.7, is_win=True) for _ in range(5)]
    with pytest.raises(ValueError):
        fit_platt_scaling(only_wins)


def test_fit_platt_scaling_improves_brier_on_overconfident_signal():
    """over-confident 가상 데이터에서 보정 후 Brier가 줄어드는지 확인.

    raw confidence는 모두 0.8인데 실제 win rate가 0.4 → 보정이 작동하면
    p_calibrated가 ~0.4 근처로 내려가 Brier가 줄어야 한다.
    """
    samples = []
    for i in range(20):
        samples.append(TradeSample(confidence=0.8, is_win=(i % 5 < 2)))  # 8 wins / 20 = 0.4
    params = fit_platt_scaling(samples)
    calibrated = apply_calibration(samples, params)
    assert brier_score(calibrated) < brier_score(samples)
    # 보정된 평균 신뢰도가 실제 win rate(0.4)에 가까워져야 한다.
    avg_calibrated = sum(s.confidence for s in calibrated) / len(calibrated)
    assert abs(avg_calibrated - 0.4) < 0.1


def test_fit_platt_scaling_separable_data_gives_monotonic_calibration():
    """저-신뢰도는 모두 패배, 고-신뢰도는 모두 승리인 경우 보정도 단조 증가."""
    samples = [TradeSample(confidence=0.3, is_win=False) for _ in range(10)] + [
        TradeSample(confidence=0.8, is_win=True) for _ in range(10)
    ]
    params = fit_platt_scaling(samples)
    assert params.apply(0.3) < params.apply(0.8)
    # 저신뢰도 < 0.5 < 고신뢰도가 일반적
    assert params.apply(0.3) < 0.5 < params.apply(0.8)
