import pytest

from core.events import Event, EventType
from agent.trading_agent import TradingAgent


@pytest.mark.asyncio
async def test_trading_agent_on_news_item_reanalyzes_relevant_holding(monkeypatch):
    agent = TradingAgent()
    agent._running = True

    observed = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_snapshot():
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 1,
            "today_trade_count": 0,
            "holding_symbols": ["005930"],
        }

    async def fake_trading_context():
        return "ctx"

    async def fake_analyze_and_trade(stock_info, cycle_id, **kwargs):
        observed["stock_info"] = dict(stock_info)
        observed["snapshot"] = kwargs["portfolio_snapshot"]
        return {"executed": False}

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "news-cycle")
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr(agent, "_build_trading_context", fake_trading_context)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)

    await agent._on_news_item(Event(
        type=EventType.NEW_NEWS_ITEM,
        data={"symbols": ["005930"], "title": "삼성전자 공시"},
        source="test",
    ))

    assert observed["stock_info"]["symbol"] == "005930"
    assert observed["stock_info"]["trigger"] == "NEW_NEWS_ITEM"
    assert observed["snapshot"]["holding_symbols"] == ["005930"]


@pytest.mark.asyncio
async def test_trading_agent_on_news_item_skips_irrelevant_symbol(monkeypatch):
    agent = TradingAgent()
    agent._running = True
    called = False

    async def fake_snapshot():
        return {
            "cash": 1_000_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_analyze_and_trade(*args, **kwargs):
        nonlocal called
        called = True
        return {"executed": False}

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr("agent.trading_agent.market_calendar.is_krx_trading_hours", lambda: True)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr(agent, "_analyze_and_trade", fake_analyze_and_trade)
    monkeypatch.setattr("agent.trading_agent.event_detector._thresholds", {"000660": object()})

    await agent._on_news_item(Event(
        type=EventType.NEW_NEWS_ITEM,
        data={"symbols": ["005930"], "title": "삼성전자 공시"},
        source="test",
    ))

    assert called is False
