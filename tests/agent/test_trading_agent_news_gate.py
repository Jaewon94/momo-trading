import pytest

from agent.trading_agent import TradingAgent


@pytest.mark.asyncio
async def test_trading_agent_news_gate_uses_service_result(monkeypatch):
    monkeypatch.setattr("agent.trading_agent.settings.NEWS_GATE_ENABLED", True)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_evaluate_gate(session, *, symbol, horizon=None):
        assert symbol == "005930"
        assert horizon == "MID"
        return {
            "approved": False,
            "reason": "부정 뉴스 압력 0.80 >= 0.55",
            "negative_pressure": 0.8,
            "negative_count": 1,
            "threshold": 0.55,
        }

    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("agent.trading_agent.news_signal_service.evaluate_gate", fake_evaluate_gate)

    agent = TradingAgent()

    result = await agent._evaluate_news_gate(symbol="005930", horizon="MID")

    assert result["approved"] is False
    assert result["negative_count"] == 1


@pytest.mark.asyncio
async def test_trading_agent_records_shadow_policy_decision(monkeypatch):
    records = []

    async def fake_log(*args, **kwargs):
        records.append((args, kwargs))

    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)

    agent = TradingAgent()
    await agent._record_news_shadow_decision(
        symbol="005930",
        name="삼성전자",
        strategy_type="STABLE_SHORT",
        horizon="MID",
        gate_eval={"edge_bps": 182.4, "cost_bps": 61.0, "edge_to_cost_ratio": 2.99},
        news_gate={
            "approved": False,
            "negative_pressure": 0.82,
            "threshold": 0.75,
            "source_count": 2,
            "contributors": [{"headline": "한글 번역 제목", "pressure": 0.11}],
        },
        cycle_id="cycle-shadow",
    )

    assert len(records) == 1
    assert "Shadow A/B" in records[0][0][2]
    assert records[0][1]["detail"]["kind"] == "NEWS_SHADOW_AB"
    assert records[0][1]["detail"]["actual_decision"] == "BLOCK"
    assert records[0][1]["detail"]["baseline_decision"] == "BUY"
