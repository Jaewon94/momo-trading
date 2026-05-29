"""Pre-LLM 게이트 신호의 예측력 분석 도구 (Information Coefficient).

trade_results.notes JSON에 저장된 결정적(deterministic) 지표들이 실제
return_pct(수익률)과 얼마나 상관관계 있는지 검증한다. 청산된 BUY 거래의
지표값과 실제 수익률을 페어로 묶어 다음 표준 메트릭을 계산한다.

메트릭:
    - Pearson IC: 지표값과 수익률의 선형 상관계수 (-1 ~ +1)
    - Spearman IC: 순위 기반 상관계수 (이상치에 강건)
    - t-statistic: IC가 0과 통계적으로 다른지 검정 (|t| > 2면 유의)
    - Quintile 분석: 지표값 상위 20% vs 하위 20%의 평균 수익률 차이
    - Monotonicity: quintile 수익률이 단조 증가/감소하는지

업계 기준:
    |IC| > 0.10  매우 강한 신호 (드물다)
    0.05~0.10    실용적 신호
    0.02~0.05    약하지만 유효
    < 0.02       노이즈 수준, 폐기 권장

사용:
    .venv313/bin/python scripts/analyze_signal_predictive_power.py
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "runtime" / "data" / "app.db"
REPORT_DIR = REPO_ROOT / "runtime" / "reports"

EXCLUDED_EXIT_REASONS = (
    "BROKER_HOLDING_QUANTITY_MISMATCH",
    "HOLDING_RECONCILIATION_CLOSE",
    "BROKER_HOLDING_MISSING",
)

# 분석 대상 numeric 지표 (notes JSON 키)
INDICATOR_KEYS: tuple[str, ...] = (
    "estimated_edge_bps",
    "edge_to_cost_ratio",
    "chart_signal_confidence",
    "news_negative_pressure",
    "news_context_confidence_hint",
    "news_context_item_count",
    "news_negative_count",
    "news_source_count",
)


@dataclass(frozen=True)
class SignalSample:
    """단일 거래의 indicator 값들 + 실제 수익률."""
    return_pct: float
    is_win: bool
    indicators: dict[str, float]


@dataclass(frozen=True)
class IndicatorAnalysis:
    """한 지표에 대한 전체 통계."""
    key: str
    n: int
    pearson_ic: float
    spearman_ic: float
    t_statistic: float
    quintile_returns: list[float]  # 5 quintile 평균 수익률 (낮은 -> 높은 지표값 순)
    monotonic_increasing: bool
    monotonic_decreasing: bool
    long_short_spread: float  # 상위 quintile − 하위 quintile 평균 수익률
    verdict: str  # "STRONG_POSITIVE" | "WEAK_POSITIVE" | "NOISE" | "INVERTED" | etc.


# ────────────────────────────────────────────────────────────────────────
# 데이터 로드
# ────────────────────────────────────────────────────────────────────────

def _parse_notes_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        pass
    end = raw.rfind("}")
    if end > 0:
        try:
            return json.loads(raw[: end + 1])
        except (TypeError, ValueError):
            return None
    return None


def load_signal_samples(db_path: Path = DB_PATH) -> list[SignalSample]:
    """청산된 BUY 거래에서 (notes 지표, return_pct, is_win) 페어를 추출한다."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB 없음: {db_path}")

    placeholders = ", ".join("?" for _ in EXCLUDED_EXIT_REASONS)
    query = f"""
        SELECT return_pct, is_win, notes
        FROM trade_results
        WHERE side = 'BUY'
          AND status = 'CONFIRMED'
          AND exit_at IS NOT NULL
          AND notes IS NOT NULL
          AND notes != ''
          AND (exit_reason IS NULL OR exit_reason NOT IN ({placeholders}))
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, EXCLUDED_EXIT_REASONS).fetchall()
    finally:
        conn.close()

    samples = []
    for return_pct, is_win, notes in rows:
        parsed = _parse_notes_json(notes)
        if not parsed:
            continue
        indicators = {}
        for key in INDICATOR_KEYS:
            val = parsed.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                indicators[key] = float(val)
        if not indicators:
            continue
        samples.append(SignalSample(
            return_pct=float(return_pct or 0.0),
            is_win=bool(is_win),
            indicators=indicators,
        ))
    return samples


# ────────────────────────────────────────────────────────────────────────
# 통계 헬퍼
# ────────────────────────────────────────────────────────────────────────

def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _rank(values: Sequence[float]) -> list[float]:
    """평균 순위 (tied values 처리)."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson_correlation(_rank(xs), _rank(ys))


def t_statistic_of_correlation(ic: float, n: int) -> float:
    """IC의 t-statistic: t = IC * sqrt(n-2) / sqrt(1 - IC^2)."""
    if n < 3 or not math.isfinite(ic):
        return float("nan")
    denom = math.sqrt(max(1.0 - ic * ic, 1e-12))
    return ic * math.sqrt(n - 2) / denom


def quintile_returns(xs: Sequence[float], ys: Sequence[float], n_quantiles: int = 5) -> list[float]:
    """지표값으로 정렬해 N quintile 평균 수익률 반환 (낮은→높은 지표값 순)."""
    pairs = sorted(zip(xs, ys), key=lambda p: p[0])
    n = len(pairs)
    if n < n_quantiles:
        return [float("nan")] * n_quantiles
    out = []
    for i in range(n_quantiles):
        lo = int(i * n / n_quantiles)
        hi = int((i + 1) * n / n_quantiles)
        if hi <= lo:
            out.append(float("nan"))
            continue
        quintile_ys = [p[1] for p in pairs[lo:hi]]
        out.append(sum(quintile_ys) / len(quintile_ys))
    return out


def is_monotonic_increasing(values: Sequence[float]) -> bool:
    return all(
        a <= b
        for a, b in zip(values, values[1:])
        if math.isfinite(a) and math.isfinite(b)
    )


def is_monotonic_decreasing(values: Sequence[float]) -> bool:
    return all(
        a >= b
        for a, b in zip(values, values[1:])
        if math.isfinite(a) and math.isfinite(b)
    )


# ────────────────────────────────────────────────────────────────────────
# 지표별 종합 분석
# ────────────────────────────────────────────────────────────────────────

def classify_verdict(spearman_ic: float, t_stat: float, monotonic_inc: bool, monotonic_dec: bool) -> str:
    """업계 통념 + 통계적 유의성을 합쳐 평가 라벨을 매긴다."""
    if not math.isfinite(spearman_ic):
        return "INSUFFICIENT_DATA"
    abs_ic = abs(spearman_ic)
    significant = abs(t_stat) >= 2.0 if math.isfinite(t_stat) else False
    if abs_ic < 0.02:
        return "NOISE (|IC| < 0.02)"
    if not significant:
        return f"NOT_SIGNIFICANT (|t|={abs(t_stat):.2f} < 2)"
    if spearman_ic <= -0.05:
        if monotonic_dec:
            return "STRONG_INVERTED (단조 감소)"
        return "INVERTED (역방향 신호)"
    if spearman_ic >= 0.10:
        return "STRONG_POSITIVE"
    if spearman_ic >= 0.05:
        return "PRACTICAL_POSITIVE"
    if spearman_ic >= 0.02:
        return "WEAK_POSITIVE"
    return "NEGLIGIBLE"


def analyze_indicator(samples: Sequence[SignalSample], key: str) -> IndicatorAnalysis | None:
    pairs = [(s.indicators[key], s.return_pct) for s in samples if key in s.indicators]
    if len(pairs) < 5:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    # 변동성 없는 지표(전부 같은 값)는 IC 계산 불가
    if max(xs) - min(xs) <= 0:
        return IndicatorAnalysis(
            key=key, n=len(pairs),
            pearson_ic=float("nan"), spearman_ic=float("nan"),
            t_statistic=float("nan"),
            quintile_returns=[float("nan")] * 5,
            monotonic_increasing=False, monotonic_decreasing=False,
            long_short_spread=float("nan"),
            verdict="CONSTANT (전 표본 동일 값)",
        )
    pearson_ic = pearson_correlation(xs, ys)
    spearman_ic = spearman_correlation(xs, ys)
    t_stat = t_statistic_of_correlation(spearman_ic, len(pairs))
    q_returns = quintile_returns(xs, ys, n_quantiles=5)
    inc = is_monotonic_increasing(q_returns)
    dec = is_monotonic_decreasing(q_returns)
    spread = q_returns[-1] - q_returns[0] if math.isfinite(q_returns[0]) and math.isfinite(q_returns[-1]) else float("nan")
    verdict = classify_verdict(spearman_ic, t_stat, inc, dec)
    return IndicatorAnalysis(
        key=key,
        n=len(pairs),
        pearson_ic=pearson_ic,
        spearman_ic=spearman_ic,
        t_statistic=t_stat,
        quintile_returns=q_returns,
        monotonic_increasing=inc,
        monotonic_decreasing=dec,
        long_short_spread=spread,
        verdict=verdict,
    )


# ────────────────────────────────────────────────────────────────────────
# 보고서
# ────────────────────────────────────────────────────────────────────────

def _fmt(value: float, width: int = 8, places: int = 4) -> str:
    if not math.isfinite(value):
        return f"{'-':>{width}}"
    return f"{value:>{width}.{places}f}"


def format_report(samples: Sequence[SignalSample], results: Sequence[IndicatorAnalysis]) -> str:
    lines = []
    lines.append("=" * 90)
    lines.append("Pre-LLM 게이트 신호 예측력 분석 (Information Coefficient)")
    lines.append("=" * 90)
    lines.append(f"청산된 BUY 표본:        {len(samples)} 건")
    if samples:
        wins = sum(1 for s in samples if s.is_win)
        avg_return = sum(s.return_pct for s in samples) / len(samples)
        lines.append(f"승률 / 평균 수익률:     {wins}/{len(samples)} = {wins/len(samples):.1%}  /  {avg_return:+.2f}%")
    lines.append("")
    lines.append("지표별 IC 분석 (높은 |IC| + |t|>=2 가 유의)")
    lines.append("-" * 90)
    lines.append(
        f"{'지표':<32} {'n':>4} {'Pearson':>9} {'Spearman':>9} "
        f"{'t-stat':>8} {'평가':<32}"
    )
    sortable = [r for r in results if r is not None]
    sortable.sort(key=lambda r: abs(r.spearman_ic) if math.isfinite(r.spearman_ic) else -1, reverse=True)
    for r in sortable:
        lines.append(
            f"{r.key:<32} {r.n:>4} {_fmt(r.pearson_ic, 9)} {_fmt(r.spearman_ic, 9)} "
            f"{_fmt(r.t_statistic, 8, 2)} {r.verdict:<32}"
        )
    lines.append("")
    lines.append("Quintile 분석 (지표값 낮은→높은 순, 평균 수익률 %)")
    lines.append("-" * 90)
    lines.append(f"{'지표':<32} {'Q1':>8} {'Q2':>8} {'Q3':>8} {'Q4':>8} {'Q5':>8} {'Q5-Q1':>10}")
    for r in sortable:
        if not all(math.isfinite(q) for q in r.quintile_returns):
            continue
        q = r.quintile_returns
        spread = q[-1] - q[0]
        lines.append(
            f"{r.key:<32} "
            f"{q[0]:>+8.2f} {q[1]:>+8.2f} {q[2]:>+8.2f} {q[3]:>+8.2f} {q[4]:>+8.2f} "
            f"{spread:>+10.2f}"
        )
    lines.append("")
    lines.append("권장 액션")
    lines.append("-" * 90)
    for r in sortable:
        if "STRONG_POSITIVE" in r.verdict or "PRACTICAL_POSITIVE" in r.verdict:
            lines.append(f"  ✅ {r.key}: 유지·가중치 ↑ (Spearman IC {r.spearman_ic:+.3f}, t={r.t_statistic:+.2f})")
        elif "INVERTED" in r.verdict:
            lines.append(f"  🔁 {r.key}: 부호 뒤집어 사용 검토 (IC {r.spearman_ic:+.3f})")
        elif "WEAK_POSITIVE" in r.verdict:
            lines.append(f"  ⚠️ {r.key}: 약한 신호, 추가 데이터로 재검증 (IC {r.spearman_ic:+.3f}, t={r.t_statistic:+.2f})")
        elif "NOISE" in r.verdict or "NEGLIGIBLE" in r.verdict:
            lines.append(f"  🗑️ {r.key}: 노이즈 수준, 게이트에서 제외 검토")
        elif "CONSTANT" in r.verdict:
            lines.append(f"  ⏸️ {r.key}: 변동성 0, 현재 데이터로 검증 불가")
        elif "NOT_SIGNIFICANT" in r.verdict:
            lines.append(f"  ⏳ {r.key}: 통계적 유의성 미달, 표본 누적 후 재평가")
    lines.append("")
    lines.append("주의:")
    lines.append("  - |t| >= 2 ≈ p<0.05 (대략적 유의성). 정확한 p값은 scipy 필요")
    lines.append("  - 표본 < 50건이면 결과 신뢰성 제한")
    lines.append("  - quintile 단조성도 같이 봐야 robustness 확인 가능")
    return "\n".join(lines)


def save_report_json(samples: Sequence[SignalSample], results: Sequence[IndicatorAnalysis], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "sample_count": len(samples),
        "win_count": sum(1 for s in samples if s.is_win),
        "average_return_pct": (
            sum(s.return_pct for s in samples) / len(samples) if samples else 0.0
        ),
        "indicators": [
            {
                "key": r.key,
                "n": r.n,
                "pearson_ic": r.pearson_ic if math.isfinite(r.pearson_ic) else None,
                "spearman_ic": r.spearman_ic if math.isfinite(r.spearman_ic) else None,
                "t_statistic": r.t_statistic if math.isfinite(r.t_statistic) else None,
                "quintile_returns": [q if math.isfinite(q) else None for q in r.quintile_returns],
                "long_short_spread": r.long_short_spread if math.isfinite(r.long_short_spread) else None,
                "monotonic_increasing": r.monotonic_increasing,
                "monotonic_decreasing": r.monotonic_decreasing,
                "verdict": r.verdict,
            }
            for r in results if r is not None
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-json", action="store_true", help="JSON 저장 건너뛰기")
    args = parser.parse_args()

    samples = load_signal_samples()
    if not samples:
        print("분석할 표본이 없습니다.")
        return 0
    results = [analyze_indicator(samples, key) for key in INDICATOR_KEYS]
    print(format_report(samples, results))

    if not args.no_json:
        today = datetime.now().strftime("%Y%m%d")
        path = REPORT_DIR / f"signal_ic_{today}.json"
        saved = save_report_json(samples, results, path)
        print(f"\nIC 분석 JSON 저장: {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
