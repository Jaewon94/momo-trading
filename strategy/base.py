"""TradingStrategy Protocol and profile metadata helpers."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from strategy.signal import TradeSignal


@runtime_checkable
class TradingStrategy(Protocol):
    """매매 전략 프로토콜"""

    @property
    def strategy_type(self) -> str: ...

    async def evaluate(self, analysis: dict) -> TradeSignal | None:
        """분석 결과를 바탕으로 매매 시그널 생성"""
        ...


@dataclass(frozen=True)
class StrategyProfile:
    strategy_type: str
    alpha_source: str
    execution_profile: str
    risk_profile: str

    def metadata(self) -> dict:
        return {
            "alpha_source": self.alpha_source,
            "execution_profile": self.execution_profile,
            "risk_profile": self.risk_profile,
        }


_PROFILE_BY_STRATEGY_TYPE = {
    "STABLE_SHORT": StrategyProfile(
        strategy_type="STABLE_SHORT",
        alpha_source="LLM_DECISION_PIPELINE",
        execution_profile="STABLE_SHORT",
        risk_profile="STABLE",
    ),
    "AGGRESSIVE_SHORT": StrategyProfile(
        strategy_type="AGGRESSIVE_SHORT",
        alpha_source="LLM_DECISION_PIPELINE",
        execution_profile="AGGRESSIVE_SHORT",
        risk_profile="AGGRESSIVE",
    ),
}


def strategy_profile_for(strategy_type: str | None) -> StrategyProfile:
    normalized = str(strategy_type or "").upper().strip()
    return _PROFILE_BY_STRATEGY_TYPE.get(
        normalized,
        StrategyProfile(
            strategy_type=normalized or "UNKNOWN",
            alpha_source="UNKNOWN",
            execution_profile=normalized or "UNKNOWN",
            risk_profile="UNKNOWN",
        ),
    )


def strategy_profile_metadata(strategy_type: str | None) -> dict:
    return strategy_profile_for(strategy_type).metadata()
