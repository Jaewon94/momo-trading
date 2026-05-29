"""LLM 신뢰도(ai_confidence) 캘리브레이션 분석 도구.

청산된 BUY 거래의 신뢰도와 실제 win rate를 비교해, 시스템이 보고하는
신뢰도가 실제 적중률과 얼마나 일치하는지 진단한다.

사용:
    .venv313/bin/python scripts/analyze_confidence_calibration.py

산출물:
    - 콘솔: 표본 수, 평균 신뢰도, 평균 win rate, Brier score, 빈별 분포
    - PNG (선택): runtime/reports/calibration_<YYYYMMDD>.png
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "runtime" / "data" / "app.db"
REPORT_DIR = REPO_ROOT / "runtime" / "reports"

# reconciliation / 보정성 청산은 LLM 판단의 결과가 아니므로 분석에서 제외.
EXCLUDED_EXIT_REASONS = (
    "BROKER_HOLDING_QUANTITY_MISMATCH",
    "HOLDING_RECONCILIATION_CLOSE",
    "BROKER_HOLDING_MISSING",
)


@dataclass(frozen=True)
class TradeSample:
    confidence: float
    is_win: bool


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    samples: list[TradeSample]

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def win_rate(self) -> float | None:
        if not self.samples:
            return None
        return sum(1 for s in self.samples if s.is_win) / self.n

    @property
    def mean_confidence(self) -> float | None:
        if not self.samples:
            return None
        return sum(s.confidence for s in self.samples) / self.n

    @property
    def label(self) -> str:
        return f"{self.lower:.2f}-{self.upper:.2f}"


def load_trade_samples(db_path: Path = DB_PATH) -> list[TradeSample]:
    """청산된 BUY 거래에서 (ai_confidence, is_win) 페어를 추출한다."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB 없음: {db_path}")

    placeholders = ", ".join("?" for _ in EXCLUDED_EXIT_REASONS)
    query = f"""
        SELECT ai_confidence, is_win
        FROM trade_results
        WHERE side = 'BUY'
          AND status = 'CONFIRMED'
          AND exit_at IS NOT NULL
          AND ai_confidence > 0
          AND (exit_reason IS NULL OR exit_reason NOT IN ({placeholders}))
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(query, EXCLUDED_EXIT_REASONS)
        rows = cur.fetchall()
    finally:
        conn.close()
    return [TradeSample(confidence=float(c), is_win=bool(w)) for c, w in rows]


def brier_score(samples: Sequence[TradeSample]) -> float:
    """Brier = mean[(p_pred - y_actual)^2], 0=완벽, 1=최악."""
    if not samples:
        return float("nan")
    return sum((s.confidence - (1.0 if s.is_win else 0.0)) ** 2 for s in samples) / len(samples)


def bin_samples(samples: Sequence[TradeSample], n_bins: int = 5) -> list[CalibrationBin]:
    """0.0~1.0 구간을 n_bins 등분해서 표본을 묶는다."""
    if n_bins < 2:
        raise ValueError("n_bins must be >= 2")
    edges = [i / n_bins for i in range(n_bins + 1)]
    bins = [CalibrationBin(lower=edges[i], upper=edges[i + 1], samples=[]) for i in range(n_bins)]
    for sample in samples:
        idx = min(int(sample.confidence * n_bins), n_bins - 1)
        bins[idx].samples.append(sample)
    return bins


def expected_calibration_error(bins: Sequence[CalibrationBin]) -> float:
    """Expected Calibration Error = sum(n_i / N * |mean_conf_i - win_rate_i|)."""
    total = sum(b.n for b in bins)
    if total == 0:
        return float("nan")
    err = 0.0
    for b in bins:
        if b.n == 0:
            continue
        weight = b.n / total
        err += weight * abs((b.mean_confidence or 0.0) - (b.win_rate or 0.0))
    return err


def format_report(samples: Sequence[TradeSample], bins: Sequence[CalibrationBin]) -> str:
    total = len(samples)
    if not total:
        return "분석할 표본이 없습니다. (청산된 BUY + ai_confidence>0 이 없음)"
    wins = sum(1 for s in samples if s.is_win)
    avg_conf = sum(s.confidence for s in samples) / total
    actual_rate = wins / total

    lines = []
    lines.append("=" * 70)
    lines.append("LLM 신뢰도 캘리브레이션 분석")
    lines.append("=" * 70)
    lines.append(f"표본 수:           {total}")
    lines.append(f"실제 승수/패수:    {wins} / {total - wins}")
    lines.append(f"실제 win rate:     {actual_rate:.3f}")
    lines.append(f"평균 신뢰도:       {avg_conf:.3f}")
    lines.append(f"  → 차이:          {avg_conf - actual_rate:+.3f}  (양수면 over-confident)")
    lines.append(f"Brier score:       {brier_score(samples):.4f}  (0=완벽, 1=최악)")
    lines.append(f"Expected Calibration Error (ECE): {expected_calibration_error(bins):.4f}")
    lines.append("")
    lines.append("구간별 분포 (n_bins=5)")
    lines.append("-" * 70)
    lines.append(f"{'구간':>12} {'n':>5} {'wins':>5} {'평균 신뢰도':>12} {'실제 win rate':>14} {'차이':>10}")
    for b in bins:
        if b.n == 0:
            lines.append(f"{b.label:>12} {0:>5} {'-':>5} {'-':>12} {'-':>14} {'-':>10}")
            continue
        wins_b = sum(1 for s in b.samples if s.is_win)
        gap = (b.mean_confidence or 0.0) - (b.win_rate or 0.0)
        lines.append(
            f"{b.label:>12} {b.n:>5} {wins_b:>5} "
            f"{(b.mean_confidence or 0):>12.3f} {(b.win_rate or 0):>14.3f} {gap:>+10.3f}"
        )
    lines.append("")
    lines.append("해석:")
    lines.append("  - '차이' 양수 = 모델이 over-confident (예측보다 실제 승률 낮음)")
    lines.append("  - '차이' 음수 = 모델이 under-confident (예측보다 실제 승률 높음)")
    lines.append("  - 완벽 캘리브레이션: 모든 구간 차이 ≈ 0")
    return "\n".join(lines)


def save_reliability_png(bins: Sequence[CalibrationBin], output_path: Path) -> Path | None:
    """Reliability diagram을 PNG로 저장한다. matplotlib 미설치 시 None 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))

    # 대각선 (이상적 캘리브레이션)
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="완벽 캘리브레이션")

    # 실제 빈별 점
    xs, ys, sizes = [], [], []
    for b in bins:
        if b.n == 0:
            continue
        xs.append(b.mean_confidence or 0.0)
        ys.append(b.win_rate or 0.0)
        sizes.append(max(40, b.n * 8))

    if xs:
        ax.scatter(xs, ys, s=sizes, color="tab:blue", alpha=0.7, label="실제 win rate")
        for b in bins:
            if b.n == 0:
                continue
            ax.annotate(
                f"n={b.n}",
                xy=(b.mean_confidence or 0.0, b.win_rate or 0.0),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("LLM 신뢰도 (mean)")
    ax.set_ylabel("실제 win rate")
    ax.set_title("LLM Confidence vs Actual Win Rate")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-bins", type=int, default=5, help="신뢰도 구간 개수 (기본 5)")
    parser.add_argument("--no-png", action="store_true", help="PNG 저장 건너뛰기")
    args = parser.parse_args()

    samples = load_trade_samples()
    bins = bin_samples(samples, n_bins=args.n_bins)
    print(format_report(samples, bins))

    if samples and not args.no_png:
        today = datetime.now().strftime("%Y%m%d")
        png_path = REPORT_DIR / f"calibration_{today}.png"
        saved = save_reliability_png(bins, png_path)
        if saved is not None and saved.exists():
            print(f"\nReliability diagram 저장: {saved}")
        else:
            print("\nmatplotlib 미설치 — PNG 저장 건너뜀. (`uv pip install matplotlib`)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
