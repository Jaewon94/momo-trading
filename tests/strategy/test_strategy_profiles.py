import pytest

from strategy.aggressive_short import AggressiveShortStrategy
from strategy.base import strategy_profile_for
from strategy.stable_short import StableShortStrategy


def test_strategy_profile_separates_alpha_source_and_execution_profile() -> None:
    stable = strategy_profile_for("STABLE_SHORT")
    aggressive = strategy_profile_for("AGGRESSIVE_SHORT")

    assert stable.alpha_source == "LLM_DECISION_PIPELINE"
    assert stable.execution_profile == "STABLE_SHORT"
    assert stable.risk_profile == "STABLE"

    assert aggressive.alpha_source == "LLM_DECISION_PIPELINE"
    assert aggressive.execution_profile == "AGGRESSIVE_SHORT"
    assert aggressive.risk_profile == "AGGRESSIVE"


@pytest.mark.asyncio
async def test_stable_short_signal_carries_profile_metadata() -> None:
    signal = await StableShortStrategy().evaluate({
        "recommendation": "BUY",
        "confidence": 0.8,
        "symbol": "005930",
        "current_price": 70_000,
    })

    assert signal is not None
    assert signal.strategy_type == "STABLE_SHORT"
    assert signal.metadata["alpha_source"] == "LLM_DECISION_PIPELINE"
    assert signal.metadata["execution_profile"] == "STABLE_SHORT"
    assert signal.metadata["risk_profile"] == "STABLE"


@pytest.mark.asyncio
async def test_aggressive_short_signal_carries_profile_metadata() -> None:
    signal = await AggressiveShortStrategy().evaluate({
        "recommendation": "BUY",
        "confidence": 0.8,
        "symbol": "005930",
        "current_price": 70_000,
    })

    assert signal is not None
    assert signal.strategy_type == "AGGRESSIVE_SHORT"
    assert signal.metadata["alpha_source"] == "LLM_DECISION_PIPELINE"
    assert signal.metadata["execution_profile"] == "AGGRESSIVE_SHORT"
    assert signal.metadata["risk_profile"] == "AGGRESSIVE"
