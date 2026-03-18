from datetime import datetime

import httpx
import pytest

from trading.kiwoom_clients import (
    KiwoomAccountClient,
    KiwoomMarketDataClient,
    KiwoomOrderExecutor,
)
from trading.kiwoom_rest_client import KiwoomRESTClient
from trading.models import OrderRequest
from trading.enums import Market, OrderSide, OrderType


def build_transport() -> tuple[httpx.MockTransport, list[tuple[str, str, dict]]]:
    requests: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = {}
        if request.content:
            payload = __import__("json").loads(request.content.decode())

        requests.append((request.url.path, request.headers.get("api-id", ""), payload))

        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "kiwoom-token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                },
            )

        if request.headers.get("api-id") == "ka10001":
            return httpx.Response(
                200,
                json={
                    "stk_cd": "005930",
                    "stk_nm": "삼성전자",
                    "cur_prc": "-68900",
                    "pred_pre": "-1000",
                    "flu_rt": "-1.43",
                    "trde_qty": "1196647",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10081":
            return httpx.Response(
                200,
                json={
                    "stk_cd": "005930",
                    "stk_dt_pole_chart_qry": [
                        {
                            "dt": "20260318",
                            "open_pric": "71000",
                            "high_pric": "72000",
                            "low_pric": "70500",
                            "cur_prc": "71500",
                            "trde_qty": "120",
                        },
                        {
                            "dt": "20260317",
                            "open_pric": "70000",
                            "high_pric": "71500",
                            "low_pric": "69800",
                            "cur_prc": "71000",
                            "trde_qty": "100",
                        },
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10080":
            return httpx.Response(
                200,
                json={
                    "stk_cd": "005930",
                    "stk_min_pole_chart_qry": [
                        {
                            "tm": "0900",
                            "open_pric": "71000",
                            "high_pric": "71100",
                            "low_pric": "70900",
                            "cur_prc": "71050",
                            "trde_qty": "10",
                        },
                        {
                            "tm": "0905",
                            "open_pric": "71050",
                            "high_pric": "71200",
                            "low_pric": "71000",
                            "cur_prc": "71150",
                            "trde_qty": "12",
                        },
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00018":
            return httpx.Response(
                200,
                json={
                    "tot_pur_amt": "210000",
                    "tot_evlt_amt": "215000",
                    "tot_evlt_pl": "5000",
                    "tot_prft_rt": "2.38",
                    "prsm_dpst_aset_amt": "715000",
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "005930",
                            "stk_nm": "삼성전자",
                            "evltv_prft": "5000",
                            "prft_rt": "2.38",
                            "pur_pric": "70000",
                            "rmnd_qty": "3",
                            "cur_prc": "71500",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10075":
            return httpx.Response(
                200,
                json={
                    "oso": [
                        {
                            "ord_no": "0000069",
                            "stk_cd": "005930",
                            "stk_nm": "삼성전자",
                            "ord_qty": "3",
                            "ord_pric": "71000",
                            "oso_qty": "2",
                            "cntr_qty": "1",
                            "io_tp_nm": "+매수",
                            "tm": "091500",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "조회가 완료되었습니다.",
                },
            )

        if request.headers.get("api-id") == "kt10000":
            return httpx.Response(
                200,
                json={
                    "ord_no": "0539055",
                    "dmst_stex_tp": "KRX",
                    "return_code": 0,
                    "return_msg": "KRX 매수주문이 완료되었습니다.",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    return httpx.MockTransport(handler), requests


@pytest.mark.asyncio
async def test_kiwoom_market_data_client_normalizes_quote_and_charts() -> None:
    transport, requests = build_transport()
    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=transport,
        token_cache_path=None,
    )
    market_client = KiwoomMarketDataClient(client)

    quote = await market_client.get_current_price("005930", market="KRX")
    daily = await market_client.get_daily_price("005930", count=2, market="KRX")
    minute = await market_client.get_minute_price("005930", period="5", market="KRX")

    assert quote.success is True
    assert quote.data["price"] == 68900.0
    assert quote.data["change"] == -1000.0
    assert daily.data["prices"][0]["date"] == "20260318"
    assert daily.data["prices"][0]["close"] == 71500.0
    assert minute.data["prices"][0]["time"] == "0900"
    assert minute.data["prices"][0]["close"] == 71050.0
    assert requests[0][0] == "/oauth2/token"
    assert requests[1][0] == "/api/dostk/stkinfo"
    assert requests[2][0] == "/api/dostk/chart"


@pytest.mark.asyncio
async def test_kiwoom_account_client_normalizes_balance_holdings_and_pending_orders() -> None:
    transport, _ = build_transport()
    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=transport,
        token_cache_path=None,
    )
    account_client = KiwoomAccountClient(client)

    balance = await account_client.get_balance()
    holdings = await account_client.get_holdings()
    pending_orders = await account_client.get_pending_orders()

    assert balance.total_asset == 715000.0
    assert balance.cash == 500000.0
    assert holdings[0].symbol == "005930"
    assert holdings[0].quantity == 3
    assert pending_orders[0].remaining_qty == 2
    assert pending_orders[0].filled_qty == 1


@pytest.mark.asyncio
async def test_kiwoom_order_executor_submits_order() -> None:
    transport, requests = build_transport()
    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=transport,
        token_cache_path=None,
    )
    executor = KiwoomOrderExecutor(client)
    request = OrderRequest(
        symbol="005930",
        market=Market.KRX,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=3,
        price=71000,
    )

    result = await executor.execute(request)

    assert result.success is True
    assert result.order_id == "0539055"
    assert requests[-1][0] == "/api/dostk/ordr"
    assert requests[-1][1] == "kt10000"
    assert requests[-1][2]["stk_cd"] == "005930"
    assert requests[-1][2]["ord_qty"] == 3
    assert requests[-1][2]["ord_uv"] == 71000
    assert requests[-1][2]["trde_tp"] == "0"
