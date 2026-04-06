import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_admin_position_detail_route_returns_summary_and_timeline(client, monkeypatch):
    trade = SimpleNamespace(
        id="t1",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=71000.0,
        exit_price=0.0,
        quantity=2,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        ai_recommendation="BUY",
        ai_confidence=0.82,
        ai_target_price=76000.0,
        ai_stop_loss_price=69000.0,
        entry_rsi=None,
        entry_pattern=None,
        market_regime="BULL",
        notes=json.dumps({
            "trade_horizon": "MID",
            "estimated_edge_bps": 182.4,
            "estimated_cost_bps": 61,
            "edge_to_cost_ratio": 2.99,
            "cost_gate_ratio": 1.3,
            "news_negative_pressure": 0.22,
            "news_negative_count": 2,
            "news_source_count": 2,
            "news_threshold": 0.75,
            "news_top_contributors": [
                {"headline": "한글 번역 제목", "pressure": 0.11},
                {"headline": "공급 차질 우려", "pressure": 0.07},
            ],
            "chart_signal_direction": "BULLISH",
            "chart_signal_confidence": 0.74,
            "entry_pattern": "상승 추세 지속",
        }, ensure_ascii=False),
        status="CONFIRMED",
        entry_at=datetime(2026, 4, 3, 9, 5),
        exit_at=None,
        created_at=datetime(2026, 4, 3, 9, 5),
    )
    activity = SimpleNamespace(
        id="a1",
        cycle_id="cycle-1",
        activity_type="TIER1_ANALYSIS",
        phase="COMPLETE",
        stock_id=None,
        symbol="005930",
        summary="삼성전자 분석 완료",
        detail='{"recommendation":"BUY","reason":"추세 유지","target_price":76000,"stop_loss_price":69000}',
        llm_provider="CODEX",
        llm_tier="TIER1",
        execution_time_ms=1200,
        confidence=0.82,
        error_message=None,
        created_at=datetime(2026, 4, 3, 9, 4),
    )
    news_item = SimpleNamespace(
        id="n1",
        source_code="DART",
        source_name="금융감독원 전자공시",
        source_tier="A",
        region="KR",
        official=True,
        language="ko",
        title="삼성전자 시설투자 공시",
        summary="대규모 설비투자 계획 공시",
        url="https://dart.fss.or.kr/example/005930",
        published_at=datetime(2026, 4, 3, 9, 3),
        sentiment_label="POSITIVE",
        sentiment_score=0.76,
        impact_score=0.88,
        trust_score=1.0,
        symbols_csv=",005930,",
        created_at=datetime(2026, 4, 3, 9, 3),
    )

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            assert symbol == "005930"
            assert limit == 21
            return [trade]

        async def get_all_open_buys(self, symbol):
            assert symbol == "005930"
            return [trade]

    class FakeActivityRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            assert symbol == "005930"
            assert limit == 21
            return [activity]

    class FakeBrokerAdapter:
        async def get_holdings(self):
            return [
                SimpleNamespace(
                    symbol="005930",
                    name="삼성전자",
                    quantity=2,
                    avg_buy_price=71000.0,
                    current_price=73500.0,
                    pnl=5000.0,
                    pnl_rate=3.52,
                ),
            ]

    class FakeNewsRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_recent(self, *, limit=50, offset=0, symbol=None, source_code=None):
            assert symbol == "005930"
            assert limit == 21
            assert offset == 0
            assert source_code is None
            return [news_item]

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.AgentActivityRepository", FakeActivityRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.NewsItemRepository", FakeNewsRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FakeBrokerAdapter(), raising=False)

    response = await client.get("/api/v1/admin/positions/005930")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["symbol"] == "005930"
    assert payload["summary"]["holding"]["current_price"] == 73500.0
    assert payload["summary"]["latest_signal"]["recommendation"] == "BUY"
    assert payload["summary"]["decision_insight"]["horizon"] == "MID"
    assert payload["summary"]["decision_insight"]["cost"]["ratio"] == 2.99
    assert payload["summary"]["decision_insight"]["news"]["contributors"][0]["headline"] == "한글 번역 제목"
    assert payload["summary"]["decision_insight"]["chart"]["direction"] == "BULLISH"
    assert payload["summary"]["trade_stats"]["open_buy_count"] == 1
    assert payload["summary"]["holding_status"] == "ok"
    assert [item["type"] for item in payload["timeline"]] == ["trade", "activity", "news"]
    assert payload["timeline"][2]["title"] == "삼성전자 시설투자 공시"
    assert payload["timeline"][2]["detail"]["source_code"] == "DART"
    assert payload["timeline"][2]["detail"]["impact_score"] == 0.88
    assert payload["timeline"][0]["detail"]["trade_state_detail_label"] == ""
    assert payload["timeline_page"]["limit"] == 20
    assert payload["timeline_page"]["offset"] == 0
    assert payload["timeline_page"]["has_more"] is False


@pytest.mark.asyncio
async def test_admin_position_detail_route_normalizes_a_prefixed_symbol(client, monkeypatch):
    trade = SimpleNamespace(
        id="t1",
        stock_symbol="065440",
        stock_name="테스트종목",
        side="BUY",
        strategy_type="SWING",
        entry_price=12000.0,
        exit_price=0.0,
        quantity=3,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        ai_recommendation="BUY",
        ai_confidence=0.82,
        ai_target_price=13000.0,
        ai_stop_loss_price=11500.0,
        entry_rsi=None,
        entry_pattern=None,
        market_regime="BULL",
        status="CONFIRMED",
        entry_at=datetime(2026, 4, 3, 9, 5),
        exit_at=None,
        created_at=datetime(2026, 4, 3, 9, 5),
    )
    observed: dict[str, str] = {}

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            observed["trade_symbol"] = symbol
            return [trade]

        async def get_all_open_buys(self, symbol):
            observed["open_buy_symbol"] = symbol
            return [trade]

    class FakeActivityRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            observed["activity_symbol"] = symbol
            return []

    class FakeBrokerAdapter:
        async def get_holdings(self):
            return [
                SimpleNamespace(
                    symbol="A065440",
                    name="테스트종목",
                    quantity=3,
                    avg_buy_price=12000.0,
                    current_price=12500.0,
                    pnl=1500.0,
                    pnl_rate=4.17,
                ),
            ]

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.AgentActivityRepository", FakeActivityRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FakeBrokerAdapter(), raising=False)

    response = await client.get("/api/v1/admin/positions/A065440")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert observed == {
        "trade_symbol": "065440",
        "open_buy_symbol": "065440",
        "activity_symbol": "065440",
    }
    assert payload["symbol"] == "065440"
    assert payload["summary"]["holding"]["symbol"] == "065440"
    assert payload["summary"]["holding_status"] == "ok"


@pytest.mark.asyncio
async def test_admin_position_detail_route_survives_holding_timeout(client, monkeypatch):
    trade = SimpleNamespace(
        id="t1",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=71000.0,
        exit_price=0.0,
        quantity=2,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        ai_recommendation="BUY",
        ai_confidence=0.82,
        ai_target_price=76000.0,
        ai_stop_loss_price=69000.0,
        entry_rsi=None,
        entry_pattern=None,
        market_regime="BULL",
        status="CONFIRMED",
        entry_at=datetime(2026, 4, 3, 9, 5),
        exit_at=None,
        created_at=datetime(2026, 4, 3, 9, 5),
    )

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            return [trade]

        async def get_all_open_buys(self, symbol):
            return [trade]

    class FakeActivityRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            return []

    class EmptyNewsRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_recent(self, *, limit=50, offset=0, symbol=None, source_code=None):
            return []

    class SlowBrokerAdapter:
        async def get_holdings(self):
            await asyncio.sleep(0.05)
            return []

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.AgentActivityRepository", FakeActivityRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.NewsItemRepository", EmptyNewsRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: SlowBrokerAdapter(), raising=False)
    monkeypatch.setattr("api.routes.admin.POSITION_DETAIL_HOLDING_TIMEOUT_SEC", 0.001, raising=False)
    monkeypatch.setattr("api.routes.admin._position_holdings_cache", {"items": None, "fetched_at": 0.0}, raising=False)

    response = await client.get("/api/v1/admin/positions/005930")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["holding"] is None
    assert payload["summary"]["holding_status"] == "timeout"
    assert "지연" in payload["summary"]["holding_message"]
    assert payload["summary"]["trade_stats"]["total_trades"] == 1
    assert payload["timeline"][0]["type"] == "trade"


@pytest.mark.asyncio
async def test_admin_position_detail_route_uses_recent_holding_cache_on_timeout(client, monkeypatch):
    trade = SimpleNamespace(
        id="t1",
        stock_symbol="005930",
        stock_name="삼성전자",
        side="BUY",
        strategy_type="SWING",
        entry_price=71000.0,
        exit_price=0.0,
        quantity=2,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        ai_recommendation="BUY",
        ai_confidence=0.82,
        ai_target_price=76000.0,
        ai_stop_loss_price=69000.0,
        entry_rsi=None,
        entry_pattern=None,
        market_regime="BULL",
        status="CONFIRMED",
        entry_at=datetime(2026, 4, 3, 9, 5),
        exit_at=None,
        created_at=datetime(2026, 4, 3, 9, 5),
    )

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            return [trade]

        async def get_all_open_buys(self, symbol):
            return [trade]

    class FakeActivityRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            return []

    class FlakyBrokerAdapter:
        def __init__(self):
            self.calls = 0

        async def get_holdings(self):
            self.calls += 1
            if self.calls == 1:
                return [
                    SimpleNamespace(
                        symbol="005930",
                        name="삼성전자",
                        quantity=2,
                        avg_buy_price=71000.0,
                        current_price=73500.0,
                        pnl=5000.0,
                        pnl_rate=3.52,
                    ),
                ]
            await asyncio.sleep(0.05)
            return []

    adapter = FlakyBrokerAdapter()
    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.AgentActivityRepository", FakeActivityRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: adapter, raising=False)
    monkeypatch.setattr("api.routes.admin.POSITION_DETAIL_HOLDING_TIMEOUT_SEC", 0.001, raising=False)
    monkeypatch.setattr("api.routes.admin.POSITION_DETAIL_HOLDING_CACHE_TTL_SEC", 60.0, raising=False)
    monkeypatch.setattr("api.routes.admin._position_holdings_cache", {"items": None, "fetched_at": 0.0}, raising=False)

    first_response = await client.get("/api/v1/admin/positions/005930")
    second_response = await client.get("/api/v1/admin/positions/005930")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()["data"]
    second_payload = second_response.json()["data"]
    assert first_payload["summary"]["holding_status"] == "ok"
    assert second_payload["summary"]["holding_status"] == "cached"
    assert second_payload["summary"]["holding"]["current_price"] == 73500.0


@pytest.mark.asyncio
async def test_admin_position_detail_route_supports_timeline_pagination(client, monkeypatch):
    trades = [
        SimpleNamespace(
            id=f"t{i}",
            stock_symbol="005930",
            stock_name="삼성전자",
            side="BUY",
            strategy_type="SWING",
            entry_price=70000.0 + i,
            exit_price=0.0,
            quantity=1,
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="",
            ai_recommendation="BUY",
            ai_confidence=0.82,
            ai_target_price=76000.0,
            ai_stop_loss_price=69000.0,
            entry_rsi=None,
            entry_pattern=None,
            market_regime="BULL",
            status="CONFIRMED",
            entry_at=datetime(2026, 4, 3, 9, 5 - i),
            exit_at=None,
            created_at=datetime(2026, 4, 3, 9, 5 - i),
        )
        for i in range(3)
    ]
    activities = [
        SimpleNamespace(
            id=f"a{i}",
            cycle_id="cycle-1",
            activity_type="TIER1_ANALYSIS",
            phase="COMPLETE",
            stock_id=None,
            symbol="005930",
            summary=f"삼성전자 분석 {i}",
            detail='{"recommendation":"BUY"}',
            llm_provider="CODEX",
            llm_tier="TIER1",
            execution_time_ms=1200,
            confidence=0.82,
            error_message=None,
            created_at=datetime(2026, 4, 3, 8, 59 - i),
        )
        for i in range(3)
    ]

    observed = {}

    class FakeTradeRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            observed["trade_limit"] = limit
            return trades[:limit]

        async def get_all_open_buys(self, symbol):
            return trades

    class FakeActivityRepo:
        def __init__(self, _db) -> None:
            pass

        async def get_by_symbol(self, symbol, limit=50):
            observed["activity_limit"] = limit
            return activities[:limit]

    class FakeBrokerAdapter:
        async def get_holdings(self):
            return []

    monkeypatch.setattr("api.routes.admin.TradeResultRepository", FakeTradeRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.AgentActivityRepository", FakeActivityRepo, raising=False)
    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FakeBrokerAdapter(), raising=False)

    response = await client.get("/api/v1/admin/positions/005930?timeline_limit=2&timeline_offset=2")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert observed == {"trade_limit": 5, "activity_limit": 5}
    assert len(payload["timeline"]) == 2
    assert payload["timeline_page"] == {
        "limit": 2,
        "offset": 2,
        "returned": 2,
        "has_more": True,
        "next_offset": 4,
    }
