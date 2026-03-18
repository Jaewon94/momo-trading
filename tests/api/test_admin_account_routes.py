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
