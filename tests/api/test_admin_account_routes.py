from trading.models import AccountBalance, HoldingInfo, PendingOrderInfo


class FakeBrokerAdapter:
    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_asset=1_000_000,
            cash=500_000,
            stock_value=500_000,
            total_pnl=25_000,
            total_pnl_rate=2.5,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        return [
            HoldingInfo(
                symbol="005930",
                name="삼성전자",
                quantity=7,
                avg_buy_price=70_000,
                current_price=72_000,
                pnl=14_000,
                pnl_rate=2.86,
            )
        ]

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        return [
            PendingOrderInfo(
                order_id="1001",
                symbol="005930",
                name="삼성전자",
                side="매수",
                order_qty=7,
                filled_qty=2,
                remaining_qty=5,
                order_price=71_000,
                order_time="091500",
            )
        ]


async def test_admin_balance_route_uses_broker_adapter(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: FakeBrokerAdapter(),
    )

    response = await client.get("/api/v1/admin/account/balance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["cash"] == 500000
    assert payload["data"]["total_asset"] == 1000000


async def test_admin_holdings_route_uses_broker_adapter(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: FakeBrokerAdapter(),
    )

    response = await client.get("/api/v1/admin/account/holdings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["symbol"] == "005930"
    assert payload["data"][0]["quantity"] == 7


async def test_admin_pending_orders_route_uses_broker_adapter(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: FakeBrokerAdapter(),
    )

    response = await client.get("/api/v1/admin/account/pending-orders")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["order_id"] == "1001"
    assert payload["data"][0]["remaining_qty"] == 5


async def test_admin_manual_sell_route_delegates_to_service(client, monkeypatch):
    observed = {}

    async def fake_sell_position(symbol: str):
        observed["symbol"] = symbol
        return {
            "symbol": symbol,
            "quantity": 7,
            "order_id": "SELL-1",
            "message": "즉시 매도 주문 접수",
        }

    monkeypatch.setattr(
        "api.routes.admin.manual_trade_service.sell_position",
        fake_sell_position,
    )

    response = await client.post("/api/v1/admin/account/holdings/005930/sell")

    assert response.status_code == 200
    assert observed == {"symbol": "005930"}
    payload = response.json()
    assert payload["data"]["order_id"] == "SELL-1"
    assert "즉시 매도" in payload["message"]


async def test_admin_pending_buy_cancel_route_delegates_to_service(client, monkeypatch):
    observed = {}

    async def fake_cancel_pending_buy(order_id: str):
        observed["order_id"] = order_id
        return {
            "order_id": order_id,
            "symbol": "005930",
            "message": "미체결 매수 주문 취소 완료",
        }

    monkeypatch.setattr(
        "api.routes.admin.manual_trade_service.cancel_pending_buy",
        fake_cancel_pending_buy,
    )

    response = await client.post("/api/v1/admin/account/pending-orders/1001/cancel-buy")

    assert response.status_code == 200
    assert observed == {"order_id": "1001"}
    payload = response.json()
    assert payload["data"]["order_id"] == "1001"
    assert "취소" in payload["message"]


async def test_admin_pending_sell_replace_route_delegates_to_service(client, monkeypatch):
    observed = {}

    async def fake_replace_pending_sell(order_id: str):
        observed["order_id"] = order_id
        return {
            "cancelled_order_id": order_id,
            "new_order_id": "SELL-2",
            "symbol": "005930",
            "quantity": 7,
            "message": "기존 매도 주문 취소 후 시장가 매도 재접수",
        }

    monkeypatch.setattr(
        "api.routes.admin.manual_trade_service.replace_pending_sell_with_market_order",
        fake_replace_pending_sell,
    )

    response = await client.post("/api/v1/admin/account/pending-orders/2001/cancel-and-sell")

    assert response.status_code == 200
    assert observed == {"order_id": "2001"}
    payload = response.json()
    assert payload["data"]["new_order_id"] == "SELL-2"
    assert "취소 후 즉시 매도" in payload["message"]
