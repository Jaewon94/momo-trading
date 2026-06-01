"""Ulcer Index + R² 60d 단위 테스트."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from analysis.technical.stability_metrics import (
    compute_stability_metrics,
    r_squared_of_log_trend,
    ulcer_index,
)


# ── Ulcer Index ──────────────────────────────────────────────────


def test_ulcer_index_zero_when_monotonically_rising():
    closes = [100.0 + i for i in range(20)]
    result = ulcer_index(closes, lookback=14)
    assert result == pytest.approx(0.0, abs=1e-6)


def test_ulcer_index_returns_nan_when_not_enough_data():
    assert math.isnan(ulcer_index([100.0, 101.0, 102.0], lookback=14))


def test_ulcer_index_increases_with_deeper_drawdown():
    mild = [100.0, 100.0, 99.0, 100.0, 99.5, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    severe = [100.0, 100.0, 80.0, 70.0, 60.0, 60.0, 60.0, 70.0, 80.0, 90.0, 100.0, 100.0, 100.0, 100.0]
    mild_ui = ulcer_index(mild, lookback=14)
    severe_ui = ulcer_index(severe, lookback=14)
    assert severe_ui > mild_ui
    assert severe_ui > 10.0  # 업계 통념상 위험 영역


def test_ulcer_index_ignores_invalid_values():
    closes = [None, 0.0, -1.0] + [100.0] * 14
    result = ulcer_index(closes, lookback=14)
    assert result == pytest.approx(0.0, abs=1e-6)


# ── R² 60d ───────────────────────────────────────────────────────


def test_r_squared_close_to_one_for_geometric_growth():
    closes = [100.0 * (1.01 ** i) for i in range(60)]
    r2 = r_squared_of_log_trend(closes, lookback=60)
    assert r2 == pytest.approx(1.0, abs=1e-6)


def test_r_squared_close_to_zero_for_random_walk():
    import random

    rng = random.Random(42)
    closes = [100.0]
    for _ in range(80):
        closes.append(closes[-1] * (1 + rng.uniform(-0.05, 0.05)))
    r2 = r_squared_of_log_trend(closes, lookback=60)
    # 정확히 0이 아니더라도 0.95 이상 깨끗한 추세는 아님
    assert 0.0 <= r2 < 0.95


def test_r_squared_returns_nan_when_not_enough_data():
    assert math.isnan(r_squared_of_log_trend([100.0, 101.0], lookback=60))


def test_r_squared_constant_series_returns_nan():
    assert math.isnan(r_squared_of_log_trend([100.0] * 60, lookback=60))


# ── compute_stability_metrics 통합 ───────────────────────────────


def test_compute_stability_metrics_returns_none_for_empty_df():
    out = compute_stability_metrics(pd.DataFrame())
    assert out == {"ulcer_index_14d": None, "r_squared_60d": None}


def test_compute_stability_metrics_returns_none_when_close_missing():
    df = pd.DataFrame({"open": [100, 101], "volume": [1, 2]})
    out = compute_stability_metrics(df)
    assert out["ulcer_index_14d"] is None
    assert out["r_squared_60d"] is None


def test_compute_stability_metrics_returns_floats_with_sufficient_data():
    closes = [100.0 * (1.005 ** i) for i in range(70)]
    df = pd.DataFrame({"close": closes})
    out = compute_stability_metrics(df)
    assert out["ulcer_index_14d"] is not None
    assert out["r_squared_60d"] is not None
    assert out["r_squared_60d"] > 0.99
    assert out["ulcer_index_14d"] == pytest.approx(0.0, abs=1e-3)


def test_compute_stability_metrics_returns_none_when_short_window():
    df = pd.DataFrame({"close": [100, 101, 102]})
    out = compute_stability_metrics(df)
    assert out["ulcer_index_14d"] is None
    assert out["r_squared_60d"] is None
