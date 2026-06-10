from datetime import timedelta

import pytest

from agent.trading_agent import TradingAgent
from models.trade_result import TradeResult
from strategy.signal import TradeSignal
from trading.enums import Market, OrderSide, OrderType, SignalAction
from trading.models import AccountBalance, Candle, CurrentPrice, HoldingInfo, OrderRequest, OrderResult
from util.time_util import now_kst


class FakeBrokerAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | int]] = []

    async def get_current_price(self, symbol: str, market: Market) -> CurrentPrice:
        self.calls.append(("quote", symbol, market.value))
        return CurrentPrice(
            symbol=symbol,
            market=market,
            price=71_500,
            change=500,
            change_rate=0.7,
            volume=123456,
            timestamp=__import__("datetime").datetime.now(),
        )

    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KRX,
    ) -> list[Candle]:
        self.calls.append(("daily", symbol, count))
        return [
            Candle(
                time_key="20260318",
                open=71000,
                high=72000,
                low=70500,
                close=71500,
                volume=120,
            )
        ]

    async def get_intraday_candles(
        self,
        symbol: str,
        interval: str = "5",
        market: Market = Market.KRX,
    ) -> list[Candle]:
        self.calls.append(("intraday", symbol, interval))
        return [
            Candle(
                time_key="0900",
                open=71000,
                high=71100,
                low=70900,
                close=71050,
                volume=10,
            )
        ]

    async def get_volume_rank(self, market: Market = Market.KRX) -> list[dict]:
        self.calls.append(("volume", "", market.value))
        return [
            {"symbol": "005930", "name": "삼성전자", "price": 71_500, "change_rate": 0.7, "volume": 123456}
        ]

    async def get_fluctuation_rank(self, sort: str, market: Market = Market.KRX) -> list[dict]:
        self.calls.append((sort, "", market.value))
        return [
            {"symbol": "035720", "name": "카카오", "price": 52_000, "change_rate": 3.5, "volume": 654321}
        ]


@pytest.mark.asyncio
async def test_trading_agent_fetches_market_data_via_broker_adapter() -> None:
    adapter = FakeBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    price_resp, daily_resp, minute_resp = await agent._fetch_symbol_market_data("005930")

    assert price_resp.success is True
    assert price_resp.data["price"] == 71_500
    assert daily_resp.data["prices"][0]["date"] == "20260318"
    assert minute_resp.data["prices"][0]["time"] == "0900"
    assert adapter.calls == [
        ("quote", "005930", "KRX"),
        ("daily", "005930", 60),
        ("intraday", "005930", "5"),
    ]


class FakeTrendBrokerAdapter:
    async def get_daily_candles(
        self,
        symbol: str,
        count: int = 30,
        market: Market = Market.KRX,
    ) -> list[Candle]:
        return [
            Candle(time_key="20260318", open=71000, high=72000, low=70500, close=72000, volume=300),
            Candle(time_key="20260317", open=70000, high=71000, low=69500, close=71000, volume=180),
            Candle(time_key="20260316", open=69500, high=70500, low=69000, close=70000, volume=160),
            Candle(time_key="20260315", open=69000, high=70000, low=68800, close=69500, volume=140),
            Candle(time_key="20260314", open=68500, high=69500, low=68000, close=69000, volume=120),
            Candle(time_key="20260313", open=68000, high=69000, low=67500, close=68500, volume=110),
            Candle(time_key="20260312", open=67500, high=68500, low=67000, close=68000, volume=100),
            Candle(time_key="20260311", open=67000, high=68000, low=66500, close=67500, volume=95),
            Candle(time_key="20260310", open=66500, high=67500, low=66000, close=67000, volume=90),
            Candle(time_key="20260309", open=66000, high=67000, low=65500, close=66500, volume=85),
        ]


@pytest.mark.asyncio
async def test_trading_agent_collects_market_close_data_via_broker_adapter() -> None:
    adapter = FakeBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    market_close_data, volume_text, surge_text, drop_text = await agent._collect_market_close_data()

    assert market_close_data == "거래량/등락률 상위 데이터로 오늘 시장 흐름 파악"
    assert "삼성전자(005930)" in volume_text
    assert "카카오(035720)" in surge_text
    assert "카카오(035720)" in drop_text


@pytest.mark.asyncio
async def test_trading_agent_summarizes_stock_trend_via_broker_adapter() -> None:
    agent = TradingAgent(broker_adapter=FakeTrendBrokerAdapter())

    summary = await agent._get_stock_trend_summary("005930", "삼성전자")

    assert "삼성전자(005930)" in summary
    assert "상승추세" in summary


class FakePortfolioBrokerAdapter:
    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=2_000_000,
            cash=1_200_000,
            stock_value=800_000,
            total_pnl=15_000,
            total_pnl_rate=0.75,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=4,
                avg_buy_price=70_000,
                current_price=71_500,
                pnl=6_000,
                pnl_rate=2.18,
            )
        ]

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.requests.append(request)
        return OrderResult(
            success=True,
            order_id="SELL-1",
            message="ok",
            filled_quantity=0,
            filled_price=0.0,
        )


class InvalidBalanceBrokerAdapter(FakePortfolioBrokerAdapter):
    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=0,
            cash=0,
            stock_value=0,
            total_pnl=0,
            total_pnl_rate=0,
            is_valid=False,
        )


class EmptyHoldingsBrokerAdapter(FakePortfolioBrokerAdapter):
    async def get_holdings(self) -> list[HoldingInfo]:
        return []


class PrefixedSymbolHoldingsBrokerAdapter(FakePortfolioBrokerAdapter):
    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="A010170",
                name="대한광통신",
                quantity=7,
                avg_buy_price=9_200,
                current_price=10_030,
                pnl=5_810,
                pnl_rate=9.02,
            )
        ]


@pytest.mark.asyncio
async def test_trading_agent_builds_portfolio_snapshot_from_broker_adapter(monkeypatch) -> None:
    adapter = FakePortfolioBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    async def fake_today_trade_count() -> int:
        return 2

    monkeypatch.setattr(agent, "_get_today_trade_count", fake_today_trade_count)

    snapshot = await agent._build_portfolio_snapshot()

    assert snapshot == {
        "cash": 1_200_000,
        "total_asset": 2_000_000,
        "stock_value": 800_000.0,
        "current_exposure_pct": 40.0,
        "holding_count": 1,
        "today_trade_count": 2,
        "holding_symbols": ["005930"],
        "holding_quantities": {"005930": 4},
    }
    assert agent._available_cash == 1_200_000


@pytest.mark.asyncio
async def test_trading_agent_counts_today_trade_results_for_risk_limit() -> None:
    from tests.conftest import TestAsyncSessionLocal

    now = now_kst()
    yesterday = now - timedelta(days=1)

    def trade(
        order_id: str | None,
        *,
        side: str = "BUY",
        status: str = "CONFIRMED",
        strategy_type: str = "AGGRESSIVE_SHORT",
        entry_at=None,
        notes: str | None = None,
    ) -> TradeResult:
        return TradeResult(
            order_id=order_id,
            stock_symbol="005930",
            stock_name="삼성전자",
            side=side,
            strategy_type=strategy_type,
            entry_price=70_000,
            exit_price=0.0 if side == "BUY" else 70_500,
            quantity=1,
            pnl=0.0,
            return_pct=0.0,
            is_win=False,
            hold_days=0,
            exit_reason="",
            ai_recommendation="BUY",
            ai_confidence=0.7,
            market_regime="NORMAL",
            status=status,
            entry_at=entry_at or now,
            exit_at=now if side == "SELL" else None,
            notes=notes,
        )

    async with TestAsyncSessionLocal() as session:
        session.add_all([
            trade("BUY-1", status="CONFIRMED"),
            trade("BUY-2", status="PENDING_CONFIRM"),
            trade("BUY-3", status="CONFIRM_FAILED"),
            trade(None, strategy_type="HOLDING_SYNC", notes="HOLDING_SYNC_BACKFILL"),
            trade("SELL-1", side="SELL"),
            trade("OLD-1", entry_at=yesterday),
        ])
        await session.commit()

    agent = TradingAgent(broker_adapter=FakePortfolioBrokerAdapter())

    assert await agent._get_today_trade_count() == 3


@pytest.mark.asyncio
async def test_trading_agent_normalizes_prefixed_holding_symbols_in_snapshot(monkeypatch) -> None:
    adapter = PrefixedSymbolHoldingsBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    async def fake_today_trade_count() -> int:
        return 1

    monkeypatch.setattr(agent, "_get_today_trade_count", fake_today_trade_count)

    snapshot = await agent._build_portfolio_snapshot()

    assert snapshot["holding_symbols"] == ["010170"]
    assert snapshot["holding_quantities"] == {"010170": 7}


def test_trading_agent_normalizes_sell_signal_quantity_to_full_holding() -> None:
    agent = TradingAgent(broker_adapter=FakePortfolioBrokerAdapter())
    signal = TradeSignal(
        symbol="010170",
        stock_id="010170",
        action=SignalAction.SELL,
        strength=0.7,
        suggested_price=13_780,
        suggested_quantity=2_300,
        strategy_type="AGGRESSIVE_SHORT",
        reason="AI 매도 추천",
        confidence=0.52,
    )

    normalized_qty = agent._resolve_sell_quantity_from_snapshot(
        signal=signal,
        portfolio_snapshot={"holding_quantities": {"010170": 4}},
    )

    assert normalized_qty == 4


@pytest.mark.asyncio
async def test_trading_agent_looks_up_current_price_via_broker_adapter() -> None:
    adapter = FakeBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)

    price = await agent._lookup_current_price("005930", "KRX")

    assert price == 71_500
    assert adapter.calls == [("quote", "005930", "KRX")]


@pytest.mark.asyncio
async def test_trading_agent_executes_exit_order_via_broker_adapter(monkeypatch) -> None:
    adapter = FakePortfolioBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)
    recorded: dict = {}

    async def fake_confirm_and_record(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.decision_maker.confirm_and_record", fake_confirm_and_record)

    result = await agent._execute_exit_order(
        symbol="005930",
        expected_price=71_000,
        exit_reason="STOP_LOSS",
    )

    assert result is not None
    assert result.success is True
    assert adapter.requests[0].side == OrderSide.SELL
    assert adapter.requests[0].order_type == OrderType.MARKET
    assert adapter.requests[0].market == Market.KRX
    assert adapter.requests[0].quantity == 4
    assert recorded["order_id"] == "SELL-1"
    assert recorded["exit_reason"] == "STOP_LOSS"


@pytest.mark.asyncio
async def test_trading_agent_executes_partial_exit_order_quantity(monkeypatch) -> None:
    adapter = FakePortfolioBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)
    recorded: dict = {}

    async def fake_confirm_and_record(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.decision_maker.confirm_and_record", fake_confirm_and_record)

    result = await agent._execute_exit_order(
        symbol="005930",
        expected_price=71_000,
        exit_reason="PARTIAL_STOP_LOSS",
        quantity=2,
    )

    assert result is not None
    assert result.success is True
    assert adapter.requests[0].quantity == 2
    assert recorded["quantity"] == 2
    assert recorded["exit_reason"] == "PARTIAL_STOP_LOSS"


@pytest.mark.asyncio
async def test_trading_agent_rejects_invalid_balance_snapshot(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=InvalidBalanceBrokerAdapter())

    async def fake_today_trade_count() -> int:
        return 0

    monkeypatch.setattr(agent, "_get_today_trade_count", fake_today_trade_count)

    with pytest.raises(RuntimeError, match="계좌 조회 실패"):
        await agent._build_portfolio_snapshot()


@pytest.mark.asyncio
async def test_trading_agent_skips_exit_order_without_holding(monkeypatch) -> None:
    adapter = EmptyHoldingsBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)
    recorded = False

    async def fake_confirm_and_record(**kwargs) -> None:
        nonlocal recorded
        recorded = True

    monkeypatch.setattr("agent.trading_agent.decision_maker.confirm_and_record", fake_confirm_and_record)

    result = await agent._execute_exit_order(
        symbol="005930",
        expected_price=71_000,
        exit_reason="STOP_LOSS",
    )

    assert result is None
    assert adapter.requests == []
    assert recorded is False


@pytest.mark.asyncio
async def test_trading_agent_normalizes_a_prefixed_symbol_for_exit_orders(monkeypatch) -> None:
    adapter = PrefixedSymbolHoldingsBrokerAdapter()
    agent = TradingAgent(broker_adapter=adapter)
    recorded: dict = {}

    async def fake_confirm_and_record(**kwargs) -> None:
        recorded.update(kwargs)

    monkeypatch.setattr("agent.trading_agent.decision_maker.confirm_and_record", fake_confirm_and_record)

    result = await agent._execute_exit_order(
        symbol="A010170",
        expected_price=10_030,
        exit_reason="TAKE_PROFIT",
    )

    assert result is not None
    assert result.success is True
    assert adapter.requests[0].symbol == "010170"
    assert adapter.requests[0].quantity == 7
    assert recorded["symbol"] == "010170"
    assert recorded["exit_reason"] == "TAKE_PROFIT"


@pytest.mark.asyncio
async def test_trading_agent_updates_last_cycle_time_when_cycle_ends_without_candidates(monkeypatch) -> None:
    agent = TradingAgent(broker_adapter=FakePortfolioBrokerAdapter())

    monkeypatch.setattr("agent.trading_agent.settings.AI_RISK_TUNING_ENABLED", False)

    async def fake_publish(*args, **kwargs) -> None:
        return None

    async def fake_log(*args, **kwargs) -> None:
        return None

    async def fake_snapshot() -> dict:
        return {
            "cash": 1_200_000,
            "total_asset": 2_000_000,
            "holding_count": 0,
            "today_trade_count": 0,
            "holding_symbols": [],
        }

    async def fake_scan(*args, **kwargs) -> dict:
        return {"selected": []}

    monkeypatch.setattr("agent.trading_agent.event_bus.publish", fake_publish)
    monkeypatch.setattr("agent.trading_agent.activity_logger.log", fake_log)
    monkeypatch.setattr("agent.trading_agent.activity_logger.start_cycle", lambda: "cycle-1")
    monkeypatch.setattr("agent.trading_agent.activity_logger.timer", lambda: object())
    monkeypatch.setattr("agent.trading_agent.activity_logger.elapsed_ms", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(agent, "_build_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr("agent.trading_agent.market_scanner.scan", fake_scan)

    result = await agent._run_trading_cycle()

    assert result["scanned"] == 0
    assert agent.last_cycle_time is not None
