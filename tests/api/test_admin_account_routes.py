from types import SimpleNamespace

from trading.models import AccountBalance, HoldingInfo, PendingOrderInfo
from util.time_util import KST


def _dt(hour: int, minute: int = 0):
    return __import__("datetime").datetime(2026, 4, 9, hour, minute, tzinfo=KST)


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


async def test_admin_balance_route_includes_session_metrics(client, monkeypatch):
    from models.trade_result import TradeResult
    from services.account_equity_service import AccountEquityService
    from tests.conftest import TestAsyncSessionLocal

    service = AccountEquityService(
        session_factory=TestAsyncSessionLocal,
        now_func=lambda: _dt(13, 30),
    )

    await service.ensure_day_baseline(
        service.build_state(
            AccountBalance(
                total_asset=980_000,
                cash=280_000,
                stock_value=700_000,
                total_pnl=95_000,
                total_pnl_rate=10.74,
            ),
            captured_at=_dt(9, 0),
        ),
        baseline_source="MARKET_OPEN",
    )
    await service.record_snapshot(
        service.build_state(
            AccountBalance(
                total_asset=1_015_000,
                cash=230_000,
                stock_value=785_000,
                total_pnl=130_000,
                total_pnl_rate=14.69,
            ),
            captured_at=_dt(10, 0),
        ),
        session_phase="INTRADAY",
    )

    async with TestAsyncSessionLocal() as session:
        session.add(TradeResult(
            stock_symbol="005930",
            stock_name="삼성전자",
            side="BUY",
            strategy_type="STABLE_SHORT",
            entry_price=70_000,
            exit_price=73_000,
            quantity=10,
            pnl=25_000,
            return_pct=3.57,
            is_win=True,
            status="CONFIRMED",
            entry_at=_dt(9, 5),
            exit_at=_dt(12, 10),
        ))
        await session.commit()

    monkeypatch.setattr("api.routes.admin.account_equity_service", service)
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: FakeBrokerAdapter(),
    )

    response = await client.get("/api/v1/admin/account/balance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["session_metrics"]["available"] is True
    assert payload["data"]["session_metrics"]["baseline_total_asset"] == 980000
    assert payload["data"]["session_metrics"]["asset_delta"] == 20000
    assert payload["data"]["session_metrics"]["daily_unrealized_delta"] == -5000


async def test_admin_balance_route_preserves_balance_when_session_metrics_fail(client, monkeypatch):
    class FailingMetricsService:
        async def build_balance_payload(self, balance, *, captured_at=None):
            raise RuntimeError("metrics unavailable")

    monkeypatch.setattr("api.routes.admin.account_equity_service", FailingMetricsService())
    monkeypatch.setattr(
        "api.routes.admin.get_broker_adapter",
        lambda: FakeBrokerAdapter(),
    )

    response = await client.get("/api/v1/admin/account/balance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total_asset"] == 1000000
    assert payload["data"]["session_metrics"]["available"] is False


async def test_admin_refresh_account_snapshot_records_current_broker_state(client, monkeypatch):
    captured = {}

    class FakeAccountEquityService:
        async def capture_and_record_current(self, *, session_phase, detail, baseline_source):
            captured["session_phase"] = session_phase
            captured["detail"] = detail
            captured["baseline_source"] = baseline_source
            return SimpleNamespace(
                captured_at=_dt(10, 55),
                trading_date=_dt(10, 55).date(),
                total_asset=1_000_000,
                cash=500_000,
                stock_value=500_000,
                total_unrealized_pnl=25_000,
                total_unrealized_pnl_rate=2.5,
                holding_count=1,
                pending_order_count=1,
                session_phase=session_phase,
            )

    class FakeActivityLogger:
        async def log(self, activity_type, phase, summary, *, detail=None, **kwargs):
            captured["activity_summary"] = summary
            captured["activity_detail"] = detail

    monkeypatch.setattr("api.routes.admin.account_equity_service", FakeAccountEquityService())
    monkeypatch.setattr("api.routes.admin.activity_logger", FakeActivityLogger())

    response = await client.post("/api/v1/admin/account/snapshot/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["cash"] == 500000
    assert payload["data"]["holding_count"] == 1
    assert payload["data"]["pending_order_count"] == 1
    assert payload["data"]["session_phase"] == "MANUAL_REFRESH"
    assert captured["session_phase"] == "MANUAL_REFRESH"
    assert captured["baseline_source"] == "MANUAL_REFRESH"
    assert captured["detail"]["reason"] == "admin_manual_refresh"
    assert captured["activity_detail"]["cash"] == 500000


async def test_admin_refresh_account_snapshot_captures_errors(client, monkeypatch):
    captured = {}

    class FailingAccountEquityService:
        async def capture_and_record_current(self, **kwargs):
            raise RuntimeError("snapshot unavailable")

    async def fake_capture_admin_api_error(operation, exc, *, symbol=None, detail=None):
        captured["operation"] = operation
        captured["message"] = str(exc)
        captured["detail"] = detail

    monkeypatch.setattr("api.routes.admin.account_equity_service", FailingAccountEquityService())
    monkeypatch.setattr("api.routes.admin._capture_admin_api_error", fake_capture_admin_api_error)

    response = await client.post("/api/v1/admin/account/snapshot/refresh")

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert captured["operation"] == "account_snapshot_refresh"
    assert captured["detail"]["route"] == "/admin/account/snapshot/refresh"


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


async def test_admin_balance_route_captures_broker_errors(client, monkeypatch):
    captured = {}

    class FailingBrokerAdapter:
        async def get_balance(self):
            raise RuntimeError("broker unavailable")

    async def fake_capture_admin_api_error(operation, exc, *, symbol=None, detail=None):
        captured["operation"] = operation
        captured["message"] = str(exc)
        captured["detail"] = detail

    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FailingBrokerAdapter())
    monkeypatch.setattr("api.routes.admin._capture_admin_api_error", fake_capture_admin_api_error)

    response = await client.get("/api/v1/admin/account/balance")

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert captured["operation"] == "account_balance"
    assert captured["detail"]["route"] == "/admin/account/balance"


async def test_admin_holdings_route_captures_broker_errors(client, monkeypatch):
    captured = {}

    class FailingBrokerAdapter:
        async def get_holdings(self):
            raise RuntimeError("holdings unavailable")

    async def fake_capture_admin_api_error(operation, exc, *, symbol=None, detail=None):
        captured["operation"] = operation
        captured["message"] = str(exc)
        captured["detail"] = detail

    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FailingBrokerAdapter())
    monkeypatch.setattr("api.routes.admin._capture_admin_api_error", fake_capture_admin_api_error)

    response = await client.get("/api/v1/admin/account/holdings")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert captured["operation"] == "account_holdings"
    assert captured["detail"]["route"] == "/admin/account/holdings"


async def test_admin_pending_orders_route_captures_broker_errors(client, monkeypatch):
    captured = {}

    class FailingBrokerAdapter:
        async def get_pending_orders(self):
            raise RuntimeError("pending unavailable")

    async def fake_capture_admin_api_error(operation, exc, *, symbol=None, detail=None):
        captured["operation"] = operation
        captured["message"] = str(exc)
        captured["detail"] = detail

    monkeypatch.setattr("api.routes.admin.get_broker_adapter", lambda: FailingBrokerAdapter())
    monkeypatch.setattr("api.routes.admin._capture_admin_api_error", fake_capture_admin_api_error)

    response = await client.get("/api/v1/admin/account/pending-orders")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert captured["operation"] == "account_pending_orders"
    assert captured["detail"]["route"] == "/admin/account/pending-orders"


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


async def test_admin_manual_sell_route_requires_confirmation_when_enabled(client, monkeypatch):
    called = False

    async def fake_sell_position(_symbol: str):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr("api.routes.admin.manual_trade_service.sell_position", fake_sell_position)

    response = await client.post("/api/v1/admin/account/holdings/005930/sell")

    assert response.status_code == 428
    assert called is False


async def test_admin_manual_sell_route_accepts_confirmation_token_when_enabled(client, monkeypatch):
    observed = {}

    async def fake_sell_position(symbol: str):
        observed["symbol"] = symbol
        return {
            "symbol": symbol,
            "quantity": 7,
            "order_id": "SELL-1",
            "message": "즉시 매도 주문 접수",
        }

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr("api.routes.admin.manual_trade_service.sell_position", fake_sell_position)

    challenge_response = await client.post(
        "/api/v1/admin/actions/confirmations",
        json={"action": "SELL_HOLDING", "resource_id": "005930", "quantity": "ALL"},
    )
    token = challenge_response.json()["data"]["confirmation_token"]

    response = await client.post(
        "/api/v1/admin/account/holdings/005930/sell",
        json={"confirmation_token": token},
    )

    assert response.status_code == 200
    assert observed == {"symbol": "005930"}


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


async def test_admin_pending_sell_replace_route_requires_confirmation_when_enabled(client, monkeypatch):
    called = False

    async def fake_replace_pending_sell(_order_id: str):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("api.routes.admin.settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED", True, raising=False)
    monkeypatch.setattr(
        "api.routes.admin.manual_trade_service.replace_pending_sell_with_market_order",
        fake_replace_pending_sell,
    )

    response = await client.post("/api/v1/admin/account/pending-orders/2001/cancel-and-sell")

    assert response.status_code == 428
    assert called is False
