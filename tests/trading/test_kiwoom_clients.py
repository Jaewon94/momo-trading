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

        if request.headers.get("api-id") == "ka10023":
            return httpx.Response(
                200,
                json={
                    "trde_qty_sdnin": [
                        {
                            "stk_cd": "005930",
                            "stk_nm": "삼성전자",
                            "cur_prc": "+71500",
                            "pred_pre": "+1200",
                            "flu_rt": "+1.71",
                            "now_trde_qty": "1234567",
                            "sdnin_rt": "+45.20",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10027":
            return httpx.Response(
                200,
                json={
                    "pred_pre_flu_rt_upper": [
                        {
                            "stk_cd": "035720",
                            "stk_nm": "카카오",
                            "cur_prc": "-52000",
                            "pred_pre": "-1500",
                            "flu_rt": "-2.80",
                            "now_trde_qty": "765432",
                        }
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00017":
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
async def test_kiwoom_market_data_client_normalizes_rankings() -> None:
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

    volume = await market_client.get_volume_rank(market="KRX")
    top = await market_client.get_fluctuation_rank(sort="top", market="KRX")
    bottom = await market_client.get_fluctuation_rank(sort="bottom", market="KRX")

    assert volume.success is True
    assert volume.data["stocks"][0]["symbol"] == "005930"
    assert volume.data["stocks"][0]["price"] == 71500.0
    assert volume.data["stocks"][0]["volume"] == 1234567

    assert top.success is True
    assert top.data["stocks"][0]["symbol"] == "035720"
    assert top.data["stocks"][0]["change_rate"] == -2.8

    assert bottom.success is True
    assert bottom.data["stocks"][0]["symbol"] == "035720"
    ranking_requests = [request for request in requests if request[0] == "/api/dostk/rkinfo"]
    assert ranking_requests[0][1] == "ka10023"
    assert ranking_requests[1][1] == "ka10027"
    assert ranking_requests[1][2]["sort_tp"] == "1"
    assert ranking_requests[2][2]["sort_tp"] == "3"


@pytest.mark.asyncio
async def test_kiwoom_account_client_normalizes_balance_holdings_and_pending_orders() -> None:
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

    account_eval_requests = [
        request for request in requests if request[1] == "kt00017"
    ]
    pending_order_requests = [
        request for request in requests if request[1] == "ka10075"
    ]

    assert len(account_eval_requests) == 1
    assert len(pending_order_requests) == 1


@pytest.mark.asyncio
async def test_kiwoom_account_client_clamps_total_asset_when_snapshot_is_lower_than_holdings() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00017":
            return httpx.Response(
                200,
                json={
                    "tot_pur_amt": "613321891",
                    "tot_evlt_amt": "640319785",
                    "tot_evlt_pl": "26997894",
                    "tot_prft_rt": "4.44",
                    "prsm_dpst_aset_amt": "534168819",
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "001250",
                            "stk_nm": "GS글로벌",
                            "evltv_prft": "-841451",
                            "prft_rt": "-0.70",
                            "pur_pric": "3678",
                            "rmnd_qty": "32756",
                            "cur_prc": "3685",
                        },
                    ],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="REAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )
    account_client = KiwoomAccountClient(client)

    balance = await account_client.get_balance()

    assert balance.total_asset == 640319785.0
    assert balance.stock_value == 640319785.0
    assert balance.cash == 0.0
    assert balance.total_pnl == 26997894.0
    assert balance.total_pnl_rate == 4.44


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
    assert requests[-1][2]["ord_qty"] == "3"
    assert requests[-1][2]["ord_uv"] == "71000"
    assert requests[-1][2]["trde_tp"] == "0"


@pytest.mark.asyncio
async def test_kiwoom_order_executor_submits_market_order_with_string_fields() -> None:
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
        symbol="065440",
        market=Market.KRX,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=900,
        price=None,
    )

    result = await executor.execute(request)

    assert result.success is True
    assert result.order_id == "0539055"
    assert requests[-1][2]["stk_cd"] == "065440"
    assert requests[-1][2]["ord_qty"] == "900"
    assert requests[-1][2]["ord_uv"] == ""
    assert requests[-1][2]["trde_tp"] == "3"


@pytest.mark.asyncio
async def test_kiwoom_rest_client_reissues_token_when_account_api_reports_invalid_token(
    tmp_path,
) -> None:
    issued_tokens: list[str] = []
    account_authorizations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            token = f"token-{len(issued_tokens) + 1}"
            issued_tokens.append(token)
            return httpx.Response(
                200,
                json={
                    "token": token,
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00017":
            account_authorizations.append(request.headers.get("authorization", ""))
            if len(account_authorizations) == 1:
                return httpx.Response(
                    200,
                    json={
                        "return_code": 3,
                        "return_msg": "인증에 실패했습니다[8005:Token이 유효하지 않습니다]",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "tot_evlt_amt": "215000",
                    "tot_evlt_pl": "5000",
                    "tot_prft_rt": "2.38",
                    "prsm_dpst_aset_amt": "715000",
                    "acnt_evlt_remn_indv_tot": [],
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=tmp_path / "kiwoom_token.json",
    )

    response = await client.request(
        api_id="kt00017",
        endpoint="/api/dostk/acnt",
        body={"qry_tp": "1", "dmst_stex_tp": "KRX"},
    )

    assert response.body["return_code"] == 0
    assert issued_tokens == ["token-1", "token-2"]
    assert account_authorizations == ["Bearer token-1", "Bearer token-2"]


@pytest.mark.asyncio
async def test_kiwoom_rest_client_retries_on_rate_limit() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "kiwoom-token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10075":
            call_count += 1
            if call_count < 3:
                return httpx.Response(429, json={"return_code": -1, "return_msg": "too many"})
            return httpx.Response(
                200,
                json={
                    "oso": [],
                    "return_code": 0,
                    "return_msg": "조회가 완료되었습니다.",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )

    response = await client.request(
        api_id="ka10075",
        endpoint="/api/dostk/acnt",
        body={"all_stk_tp": "0", "trde_tp": "0", "stk_cd": "", "stex_tp": "0"},
    )

    assert response.body["return_code"] == 0
    assert call_count == 3


@pytest.mark.asyncio
async def test_kiwoom_rest_client_waits_when_request_rate_limit_is_full(monkeypatch) -> None:
    sleep_calls: list[float] = []
    monotonic_values = [10.0, 10.0, 10.1, 10.2, 11.21]
    last_value = monotonic_values[-1]

    def fake_monotonic() -> float:
        nonlocal monotonic_values
        if monotonic_values:
            return monotonic_values.pop(0)
        return last_value

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "kiwoom-token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        return httpx.Response(
            200,
            json={"return_code": 0, "return_msg": "ok"},
        )

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("trading.kiwoom_rest_client.time.monotonic", fake_monotonic)
    monkeypatch.setattr("trading.kiwoom_rest_client.asyncio.sleep", fake_sleep)

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )
    client._request_timestamps = [10.0, 10.1, 10.2]

    response = await client.request(
        api_id="ka10075",
        endpoint="/api/dostk/acnt",
        body={"all_stk_tp": "0"},
    )

    assert response.body["return_code"] == 0
    assert sleep_calls


@pytest.mark.asyncio
async def test_kiwoom_market_data_client_reuses_recent_quote_cache() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "kiwoom-token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "ka10001":
            request_count += 1
            return httpx.Response(
                200,
                json={
                    "cur_prc": "73000",
                    "pred_pre": "1000",
                    "flu_rt": "1.39",
                    "trde_qty": "654321",
                    "return_code": 0,
                    "return_msg": "조회가 완료되었습니다.",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )
    market_client = KiwoomMarketDataClient(client)

    first = await market_client.get_current_price("005930", market="KRX")
    second = await market_client.get_current_price("005930", market="KRX")

    assert first.success is True
    assert second.success is True
    assert request_count == 1


@pytest.mark.asyncio
async def test_kiwoom_account_client_raises_when_account_api_returns_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "token": "kiwoom-token",
                    "expires_dt": "20991231235959",
                    "token_type": "Bearer",
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00017":
            return httpx.Response(
                200,
                json={
                    "return_code": 3,
                    "return_msg": "인증에 실패했습니다[8005:Token이 유효하지 않습니다]",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )
    account_client = KiwoomAccountClient(client)

    with pytest.raises(RuntimeError, match="인증에 실패"):
        await account_client.get_balance()


@pytest.mark.asyncio
async def test_kiwoom_account_client_uses_mock_cash_fallback_when_stock_balance_tr_is_unsupported() -> None:
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
                    "return_code": 0,
                    "return_msg": "정상적으로 처리되었습니다",
                },
            )

        if request.headers.get("api-id") == "kt00017":
            return httpx.Response(
                200,
                json={
                    "return_code": 20,
                    "return_msg": "[2000](RC9000:모의투자에서는 해당업무가 제공되지 않습니다.)",
                },
            )

        if request.headers.get("api-id") == "kt00018":
            return httpx.Response(
                200,
                json={
                    "tot_pur_amt": "000000000000000",
                    "tot_evlt_amt": "000000000000000",
                    "tot_evlt_pl": "000000000000000",
                    "tot_prft_rt": "000000000.00",
                    "prsm_dpst_aset_amt": "000000500000000",
                    "acnt_evlt_remn_indv_tot": [],
                    "return_code": 0,
                    "return_msg": "모의투자 해당조회내역이 없습니다.",
                },
            )

        return httpx.Response(404, json={"return_code": -1, "return_msg": "not found"})

    client = KiwoomRESTClient(
        app_key="real-key",
        secret_key="real-secret",
        paper_app_key="paper-key",
        paper_secret_key="paper-secret",
        account_type="VIRTUAL",
        transport=httpx.MockTransport(handler),
        token_cache_path=None,
    )
    account_client = KiwoomAccountClient(client)

    balance = await account_client.get_balance()
    holdings = await account_client.get_holdings()

    assert balance.total_asset == 500000000.0
    assert balance.cash == 500000000.0
    assert holdings == []
    assert [req[1] for req in requests if req[0] == "/api/dostk/acnt"] == [
        "kt00017",
        "kt00018",
    ]
