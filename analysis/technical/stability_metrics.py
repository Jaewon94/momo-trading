"""안정성 지표 — Ulcer Index, R² (선형성).

Why:
    현재 Pre-LLM fast gate 는 momentum + chart pattern 위주라 변동성/안정성
    차원이 빠져 있다. 업계 multifactor 모델은 Low-Volatility 팩터를 별도로
    측정한다 (Ulcer Index, R², Std Dev of Log Return 등).

How to apply:
    fast_gate 가 daily_df 를 그대로 받아 계산만 한다. 게이트 점수에는
    당장 반영하지 않고, notes JSON 에 기록만 해서 weekly IC 검증으로
    예측력을 측정한 뒤 효력 검증되면 게이트에 통합한다.

References:
    - https://en.wikipedia.org/wiki/Ulcer_index  — Peter Martin (1987)
    - https://chartschool.stockcharts.com/.../ulcer-index  — 14d 권장
    - https://python.stockindicators.dev/indicators/UlcerIndex/  — Python impl
"""
from __future__ import annotations

import math
from typing import Sequence

import pandas as pd


def ulcer_index(closes: Sequence[float], lookback: int = 14) -> float:
    """Ulcer Index — 최근 N봉 동안의 drawdown 깊이·지속 (값 클수록 risk 큼).

    UI = sqrt( mean( drawdown_pct² ) ) over the lookback window.
    drawdown_pct = (close - rolling_max) / rolling_max * 100

    Returns NaN if not enough data.
    """
    if lookback <= 0:
        return float("nan")
    series = [float(v) for v in closes if v is not None and math.isfinite(float(v)) and float(v) > 0]
    if len(series) < lookback:
        return float("nan")

    window = series[-lookback:]
    peak = window[0]
    squared_drawdowns: list[float] = []
    for price in window:
        if price > peak:
            peak = price
        if peak <= 0:
            continue
        drawdown_pct = (price - peak) / peak * 100.0
        squared_drawdowns.append(drawdown_pct * drawdown_pct)
    if not squared_drawdowns:
        return float("nan")
    return math.sqrt(sum(squared_drawdowns) / len(squared_drawdowns))


def r_squared_of_log_trend(closes: Sequence[float], lookback: int = 60) -> float:
    """선형성 R² — log-close 에 대한 OLS 회귀의 결정계수.

    추세가 깨끗한 직선이면 1.0, 노이즈가 많으면 0에 가깝다.
    Returns NaN if not enough data or zero variance.
    """
    if lookback <= 1:
        return float("nan")
    series = [float(v) for v in closes if v is not None and math.isfinite(float(v)) and float(v) > 0]
    if len(series) < lookback:
        return float("nan")
    window = series[-lookback:]
    xs = list(range(len(window)))
    ys = [math.log(price) for price in window]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return max(0.0, min(1.0, 1.0 - ss_res / syy))


def compute_stability_metrics(
    daily_df: pd.DataFrame | None,
    *,
    ulcer_lookback: int = 14,
    r2_lookback: int = 60,
) -> dict[str, float | None]:
    """daily_df 로부터 Ulcer Index 14d + R² 60d 계산.

    데이터 부족·결측 시 None 반환. 호출자는 None 을 그대로 notes 에 기록할 수
    있도록 dict 형태로 돌려준다 (NaN 대신 None — JSON 친화).
    """
    if daily_df is None or daily_df.empty or "close" not in daily_df.columns:
        return {"ulcer_index_14d": None, "r_squared_60d": None}
    closes = pd.to_numeric(daily_df["close"], errors="coerce").dropna().tolist()
    ulcer = ulcer_index(closes, lookback=ulcer_lookback)
    r2 = r_squared_of_log_trend(closes, lookback=r2_lookback)
    return {
        "ulcer_index_14d": round(ulcer, 4) if math.isfinite(ulcer) else None,
        "r_squared_60d": round(r2, 4) if math.isfinite(r2) else None,
    }
