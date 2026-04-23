import pytest

from services.news_gate_rollout_service import NewsGateRolloutService


@pytest.mark.asyncio
async def test_news_gate_rollout_service_preserves_legacy_buy_block(monkeypatch) -> None:
    service = NewsGateRolloutService()
    monkeypatch.setattr("services.news_gate_rollout_service.settings.NEWS_GATE_ROLLOUT_MODE", "", raising=False)
    monkeypatch.setattr("services.news_gate_rollout_service.settings.NEWS_GATE_ENABLED", True)
    monkeypatch.setattr("services.news_gate_rollout_service.settings.NEWS_SHADOW_ENABLED", True)

    decision = await service.resolve()

    assert decision.requested_mode == "LEGACY"
    assert decision.effective_mode == "BUY_BLOCK_GATE"
    assert decision.evaluate_gate is True
    assert decision.block_buy is True
    assert decision.record_shadow is True


@pytest.mark.asyncio
async def test_news_gate_rollout_service_shadow_only_evaluates_without_blocking(monkeypatch) -> None:
    service = NewsGateRolloutService()
    monkeypatch.setattr("services.news_gate_rollout_service.settings.NEWS_GATE_ROLLOUT_MODE", "SHADOW_ONLY", raising=False)

    decision = await service.resolve()

    assert decision.effective_mode == "SHADOW_ONLY"
    assert decision.evaluate_gate is True
    assert decision.block_buy is False
    assert decision.record_shadow is True


@pytest.mark.asyncio
async def test_news_gate_rollout_service_downgrades_buy_block_when_rollout_not_promoted(monkeypatch) -> None:
    service = NewsGateRolloutService()
    monkeypatch.setattr("services.news_gate_rollout_service.settings.NEWS_GATE_ROLLOUT_MODE", "BUY_BLOCK_GATE", raising=False)

    async def fake_rollout_status() -> dict:
        return {"status": "HOLDOUT", "reason": "표본 부족"}

    monkeypatch.setattr(service, "_get_rollout_status", fake_rollout_status)

    decision = await service.resolve()

    assert decision.requested_mode == "BUY_BLOCK_GATE"
    assert decision.effective_mode == "SHADOW_ONLY"
    assert decision.evaluate_gate is True
    assert decision.block_buy is False
    assert decision.record_shadow is True
    assert decision.detail["rollout_status"]["status"] == "HOLDOUT"
