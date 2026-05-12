"""Fast deterministic gate before expensive per-symbol Tier1 LLM analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from analysis.chart_analyzer import ChartAnalysisResult
from core.config import settings
from trading.symbols import normalize_krx_symbol
from util.time_util import now_kst


@dataclass(frozen=True)
class DeterministicTier1FastGateDecision:
    action: str
    code: str
    reason: str
    score: float
    detail: dict = field(default_factory=dict)

    @property
    def should_skip_tier1(self) -> bool:
        return self.action == "HOLD"


@dataclass(frozen=True)
class FastGateRiskProfile:
    risk_appetite: str
    min_continue_score: float
    overheat_change_pct: float
    bull_momentum_min_change_pct: float
    bull_momentum_min_score: float
    hard_late_overheat_change_pct: float
    hard_bearish_confidence: float
    hard_bearish_trend_score_max: float


class DeterministicTier1FastGateService:
    """Conservative LLM avoidance for clear non-buy scan candidates.

    This gate is intentionally one-way: it may skip clear HOLD/REJECT cases, but
    it never creates a BUY signal. BUY candidates still continue to Tier2/LLM.
    """

    def evaluate(
        self,
        *,
        symbol: str,
        stock_info: dict,
        current_price: float,
        daily_df: pd.DataFrame,
        minute_df: pd.DataFrame | None,
        chart_result: ChartAnalysisResult,
        portfolio_snapshot: dict | None,
        market_regime: str = "",
        now: datetime | None = None,
        ignore_enabled: bool = False,
    ) -> DeterministicTier1FastGateDecision:
        if (
            not ignore_enabled
            and not bool(getattr(settings, "DETERMINISTIC_TIER1_FAST_GATE_ENABLED", True))
        ):
            return self._continue("DISABLED", "deterministic Tier1 fast gate disabled", 100.0)

        normalized_symbol = normalize_krx_symbol(symbol)
        holding_symbols = {
            normalize_krx_symbol(item)
            for item in (portfolio_snapshot or {}).get("holding_symbols", [])
            if normalize_krx_symbol(item)
        }
        is_holding = normalized_symbol in holding_symbols
        direction = str(stock_info.get("direction", "BUY") or "BUY").upper()
        if is_holding or direction == "SELL":
            return self._continue("HOLDING_OR_SELL", "held or sell-directed candidate requires full analysis", 100.0)

        decision_time = now or now_kst()
        cutoff_hour = int(getattr(settings, "TIER1_FAST_GATE_LATE_BUY_CUTOFF_HOUR", 14) or 14)
        cutoff_minute = int(getattr(settings, "TIER1_FAST_GATE_LATE_BUY_CUTOFF_MINUTE", 45) or 45)
        after_cutoff = (decision_time.hour, decision_time.minute) >= (cutoff_hour, cutoff_minute)

        change_rate = self._float(
            stock_info.get("change_rate")
            or stock_info.get("change_pct")
            or stock_info.get("rate")
            or 0.0
        )
        if change_rate == 0.0:
            price_data = stock_info.get("price_data") or {}
            change_rate = self._float(price_data.get("change_rate") or 0.0)

        indicators = chart_result.indicators or {}
        signal_summary = chart_result.signal_summary or {}
        trend = chart_result.trend
        intraday = getattr(trend, "intraday", None) or {}
        score = 50.0
        reasons: list[str] = []

        trend_direction = str(getattr(trend, "direction", "NEUTRAL") or "NEUTRAL").upper()
        trend_score = self._float(getattr(trend, "score", 0.0) or 0.0)
        signal_direction = str(signal_summary.get("direction", "NEUTRAL") or "NEUTRAL").upper()
        signal_confidence = self._float(signal_summary.get("confidence") or 0.0)

        if trend_direction == "BULLISH":
            score += 12
            reasons.append("daily trend bullish")
        elif trend_direction == "BEARISH":
            score -= 18
            reasons.append("daily trend bearish")

        if signal_direction == "BULLISH":
            score += 10
            reasons.append("chart aggregate bullish")
        elif signal_direction == "BEARISH":
            score -= 16
            reasons.append("chart aggregate bearish")

        intraday_direction = str(intraday.get("direction", "NEUTRAL") or "NEUTRAL").upper()
        if intraday_direction == "BULLISH":
            score += 8
            reasons.append("intraday trend bullish")
        elif intraday_direction == "BEARISH":
            score -= 12
            reasons.append("intraday trend bearish")

        vwap_position = str(intraday.get("vwap_position", "") or "").upper()
        if vwap_position == "ABOVE_VWAP":
            score += 4
            reasons.append("above intraday VWAP")
        elif vwap_position == "BELOW_VWAP":
            score -= 4
            reasons.append("below intraday VWAP")

        volume_trend = str(intraday.get("vol_trend", "") or "").upper()
        if volume_trend == "INCREASING":
            score += 4
            reasons.append("intraday volume increasing")
        elif volume_trend == "DECREASING":
            score -= 4
            reasons.append("intraday volume decreasing")

        rsi = self._float(indicators.get("rsi_14"))
        if rsi >= 78:
            score -= 10
            reasons.append("RSI overheat")
        elif 45 <= rsi <= 68:
            score += 5
            reasons.append("RSI constructive")

        macd_hist = self._float(indicators.get("macd_histogram"))
        if macd_hist > 0:
            score += 5
            reasons.append("MACD positive")
        elif macd_hist < 0:
            score -= 7
            reasons.append("MACD negative")

        volume_weakening = self._volume_weakening(daily_df, minute_df)
        if volume_weakening:
            score -= 8
            reasons.append("volume weakening")
        else:
            score += 4
            reasons.append("volume acceptable")

        risk_profile = self._risk_profile()
        upper_limit_fade_risk = (
            change_rate >= risk_profile.overheat_change_pct
            and vwap_position == "BELOW_VWAP"
            and volume_trend == "DECREASING"
            and volume_weakening
        )
        if change_rate >= risk_profile.overheat_change_pct:
            score -= 18 if upper_limit_fade_risk else 8
            reasons.append("near upper-limit overheat")
            if upper_limit_fade_risk:
                reasons.append("upper-limit fade risk")
        elif 3.0 <= change_rate <= 18.0:
            score += 8
            reasons.append("moderate positive momentum")
        elif change_rate < -3.0:
            score -= 12
            reasons.append("negative price momentum")

        if after_cutoff:
            score -= 20
            reasons.append("late-day new buy cutoff")

        regime = str(market_regime or "").upper()
        if regime in {"BEAR", "BEARISH"}:
            score -= 8
            reasons.append("bearish market regime")

        hard_late_overheat = after_cutoff and change_rate >= risk_profile.hard_late_overheat_change_pct
        hard_bearish = (
            signal_direction == "BEARISH"
            and signal_confidence >= risk_profile.hard_bearish_confidence
            and trend_score < risk_profile.hard_bearish_trend_score_max
        )
        bull_momentum_allow = self._bull_momentum_allow(
            regime=regime,
            change_rate=change_rate,
            score=score,
            after_cutoff=after_cutoff,
            signal_direction=signal_direction,
            signal_confidence=signal_confidence,
            trend_score=trend_score,
            risk_profile=risk_profile,
        )
        if bull_momentum_allow:
            reasons.append("bull/theme momentum analysis allowance")

        if hard_late_overheat or (hard_bearish and not bull_momentum_allow) or (score < risk_profile.min_continue_score and not bull_momentum_allow):
            return DeterministicTier1FastGateDecision(
                action="HOLD",
                code="FAST_GATE_HOLD",
                reason=", ".join(reasons[:6]) or "deterministic score below threshold",
                score=round(score, 2),
                detail={
                    "score": round(score, 2),
                    "threshold": risk_profile.min_continue_score,
                    "change_rate": change_rate,
                    "after_cutoff": after_cutoff,
                    "risk_appetite": risk_profile.risk_appetite,
                    "overheat_threshold": risk_profile.overheat_change_pct,
                    "trend_direction": trend_direction,
                    "signal_direction": signal_direction,
                    "intraday_direction": intraday_direction,
                    "intraday_vwap_position": vwap_position,
                    "intraday_volume_trend": volume_trend,
                    "volume_weakening": volume_weakening,
                    "upper_limit_fade_risk": upper_limit_fade_risk,
                    "bull_momentum_allow": bull_momentum_allow,
                    "reasons": reasons,
                },
            )

        return DeterministicTier1FastGateDecision(
            action="CONTINUE",
            code="FAST_GATE_CONTINUE",
            reason=", ".join(reasons[:6]) or "deterministic score passed",
            score=round(score, 2),
            detail={
                "score": round(score, 2),
                "threshold": risk_profile.min_continue_score,
                "change_rate": change_rate,
                "after_cutoff": after_cutoff,
                "risk_appetite": risk_profile.risk_appetite,
                "overheat_threshold": risk_profile.overheat_change_pct,
                "trend_direction": trend_direction,
                "signal_direction": signal_direction,
                "intraday_direction": intraday_direction,
                "intraday_vwap_position": vwap_position,
                "intraday_volume_trend": volume_trend,
                "volume_weakening": volume_weakening,
                "upper_limit_fade_risk": upper_limit_fade_risk,
                "bull_momentum_allow": bull_momentum_allow,
                "reasons": reasons,
            },
        )

    @staticmethod
    def _continue(code: str, reason: str, score: float) -> DeterministicTier1FastGateDecision:
        return DeterministicTier1FastGateDecision(
            action="CONTINUE",
            code=code,
            reason=reason,
            score=score,
            detail={"score": score},
        )

    @staticmethod
    def _float(value) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _risk_profile(cls) -> FastGateRiskProfile:
        """Return effective fast-gate thresholds for the selected risk appetite.

        Runtime settings remain the conservative baseline. Moderate and aggressive
        modes relax only the deterministic pre-LLM skip gate; they do not create
        buy signals by themselves.
        """
        appetite = str(getattr(settings, "RISK_APPETITE", "CONSERVATIVE") or "CONSERVATIVE").upper()
        min_continue = float(getattr(settings, "TIER1_FAST_GATE_MIN_CONTINUE_SCORE", 55.0) or 55.0)
        overheat = float(getattr(settings, "TIER1_FAST_GATE_OVERHEAT_CHANGE_PCT", 27.0) or 27.0)
        bull_min_change = float(getattr(settings, "TIER1_FAST_GATE_BULL_MOMENTUM_MIN_CHANGE_PCT", 7.0) or 7.0)
        bull_min_score = float(getattr(settings, "TIER1_FAST_GATE_BULL_MOMENTUM_MIN_SCORE", 35.0) or 35.0)

        if appetite == "AGGRESSIVE":
            return FastGateRiskProfile(
                risk_appetite=appetite,
                min_continue_score=max(35.0, min_continue - 15.0),
                overheat_change_pct=min(31.0, overheat + 4.0),
                bull_momentum_min_change_pct=max(2.0, bull_min_change - 4.0),
                bull_momentum_min_score=max(20.0, bull_min_score - 10.0),
                hard_late_overheat_change_pct=27.0,
                hard_bearish_confidence=0.75,
                hard_bearish_trend_score_max=-15.0,
            )

        if appetite == "MODERATE":
            return FastGateRiskProfile(
                risk_appetite=appetite,
                min_continue_score=max(45.0, min_continue - 10.0),
                overheat_change_pct=min(30.0, overheat + 2.0),
                bull_momentum_min_change_pct=max(3.0, bull_min_change - 2.0),
                bull_momentum_min_score=max(25.0, bull_min_score - 5.0),
                hard_late_overheat_change_pct=24.0,
                hard_bearish_confidence=0.60,
                hard_bearish_trend_score_max=-8.0,
            )

        return FastGateRiskProfile(
            risk_appetite="CONSERVATIVE",
            min_continue_score=min_continue,
            overheat_change_pct=overheat,
            bull_momentum_min_change_pct=bull_min_change,
            bull_momentum_min_score=bull_min_score,
            hard_late_overheat_change_pct=20.0,
            hard_bearish_confidence=0.45,
            hard_bearish_trend_score_max=0.0,
        )

    @classmethod
    def _bull_momentum_allow(
        cls,
        *,
        regime: str,
        change_rate: float,
        score: float,
        after_cutoff: bool,
        signal_direction: str,
        signal_confidence: float,
        trend_score: float,
        risk_profile: FastGateRiskProfile | None = None,
    ) -> bool:
        if not bool(getattr(settings, "TIER1_FAST_GATE_BULL_MOMENTUM_ALLOW_ENABLED", True)):
            return False
        if regime not in {"BULL", "BULLISH", "THEME", "STRONG_BULL"}:
            return False
        if after_cutoff:
            return False
        profile = risk_profile or cls._risk_profile()
        min_change = profile.bull_momentum_min_change_pct
        min_score = profile.bull_momentum_min_score
        if change_rate < min_change or score < min_score:
            return False
        if (
            signal_direction == "BEARISH"
            and signal_confidence >= profile.hard_bearish_confidence
            and trend_score < profile.hard_bearish_trend_score_max
        ):
            return False
        return True

    @classmethod
    def _volume_weakening(cls, daily_df: pd.DataFrame, minute_df: pd.DataFrame | None) -> bool:
        if minute_df is not None and "volume" in minute_df.columns and len(minute_df) >= 6:
            volumes = pd.to_numeric(minute_df["volume"], errors="coerce").dropna()
            if len(volumes) >= 6:
                recent = float(volumes.tail(3).mean())
                previous = float(volumes.iloc[-6:-3].mean())
                if previous > 0 and recent < previous * 0.75:
                    return True

        if "volume" in daily_df.columns and len(daily_df) >= 6:
            volumes = pd.to_numeric(daily_df["volume"], errors="coerce").dropna()
            if len(volumes) >= 6:
                latest = float(volumes.iloc[-1])
                previous_avg = float(volumes.iloc[-6:-1].mean())
                if previous_avg > 0 and latest < previous_avg * 0.6:
                    return True
        return False


deterministic_tier1_fast_gate_service = DeterministicTier1FastGateService()
