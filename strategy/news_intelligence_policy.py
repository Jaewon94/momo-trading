"""Canonical news intelligence policy rails."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from strategy.horizon_scan_policy import horizon_scan_profile, normalize_scan_horizon
from strategy.trade_horizon import TradeHorizon


NewsEventCategory = Literal[
    "earnings",
    "guidance",
    "contract",
    "capital_action",
    "ownership",
    "regulatory",
    "litigation",
    "supply_demand",
    "sector_theme",
    "market_noise",
]


@dataclass(frozen=True)
class NewsHorizonPolicy:
    horizon: str
    threshold_multiplier: float
    freshness_multiplier: float
    lookback_hours: int
    prompt_items: int
    pressure_candidates: int


@dataclass(frozen=True)
class NewsEventPolicy:
    category: NewsEventCategory
    label: str
    default_materiality: float
    horizon_bias: tuple[str, ...]
    treat_as_noise_when_unlinked: bool = False


@dataclass(frozen=True)
class AfterHoursNewsResearchPolicy:
    """Policy for future after-hours research generation.

    This does not enable a scheduled LLM call by itself. It defines the contract
    any implementation must follow before producing reusable next-session
    context.
    """

    max_source_items: int = 80
    max_symbols: int = 40
    max_llm_batches: int = 1
    llm_default_enabled: bool = False
    require_citations: bool = True
    require_no_trade_orders: bool = True
    require_shadow_metrics: bool = True


_HORIZON_PROFILE = {
    TradeHorizon.SHORT: {"threshold_multiplier": 0.9, "freshness_multiplier": 0.7},
    TradeHorizon.MID: {"threshold_multiplier": 1.0, "freshness_multiplier": 1.0},
    TradeHorizon.LONG: {"threshold_multiplier": 1.12, "freshness_multiplier": 1.35},
}


_SEVERITY_KEYWORDS: tuple[tuple[str, float], ...] = (
    ("회계 조사", 1.35),
    ("investigation", 1.35),
    ("fraud", 1.35),
    ("분식", 1.35),
    ("부도", 1.3),
    ("default", 1.3),
    ("거래정지", 1.25),
    ("suspension", 1.25),
    ("실적 경고", 1.18),
    ("profit warning", 1.18),
    ("guidance cut", 1.18),
    ("리콜", 1.15),
    ("recall", 1.15),
    ("공급 차질", 1.15),
    ("supply disruption", 1.15),
    ("demand warning", 1.12),
    ("정정 공시", 1.08),
)


NEWS_EVENT_POLICIES: tuple[NewsEventPolicy, ...] = (
    NewsEventPolicy("earnings", "실적/잠정실적", 0.9, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("guidance", "가이던스/전망 변경", 0.95, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("contract", "공급계약/수주", 0.82, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("capital_action", "증자/자사주/배당/소각", 0.78, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("ownership", "최대주주/임원 지분 변동", 0.58, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("regulatory", "규제/거래정지/제재", 0.96, (TradeHorizon.SHORT, TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("litigation", "소송/조사/회계 이슈", 0.95, (TradeHorizon.MID, TradeHorizon.LONG)),
    NewsEventPolicy("supply_demand", "공급망/수요 변화", 0.8, (TradeHorizon.SHORT, TradeHorizon.MID)),
    NewsEventPolicy("sector_theme", "섹터/테마 뉴스", 0.68, (TradeHorizon.SHORT, TradeHorizon.MID)),
    NewsEventPolicy("market_noise", "가격제한폭/단순 시장공지/소음", 0.25, (), True),
)


def news_horizon_policy(value: str | None) -> NewsHorizonPolicy:
    horizon = normalize_scan_horizon(value)
    scan_profile = horizon_scan_profile(horizon)
    profile = _HORIZON_PROFILE.get(horizon, _HORIZON_PROFILE[TradeHorizon.MID])
    return NewsHorizonPolicy(
        horizon=horizon,
        threshold_multiplier=float(profile["threshold_multiplier"]),
        freshness_multiplier=float(profile["freshness_multiplier"]),
        lookback_hours=scan_profile.news_lookback_hours,
        prompt_items=scan_profile.news_prompt_items,
        pressure_candidates=scan_profile.news_pressure_candidates,
    )


def news_severity_keywords() -> tuple[tuple[str, float], ...]:
    return _SEVERITY_KEYWORDS


def after_hours_news_research_policy() -> AfterHoursNewsResearchPolicy:
    return AfterHoursNewsResearchPolicy()


def news_event_policies() -> tuple[NewsEventPolicy, ...]:
    return NEWS_EVENT_POLICIES
