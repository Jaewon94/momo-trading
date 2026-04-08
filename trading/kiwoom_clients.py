"""Kiwoom REST 기반 도메인 클라이언트"""
import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from trading.enums import Market, OrderType
from trading.kiwoom_rest_client import KiwoomAPIResponse, KiwoomRESTClient
from trading.models import (
    AccountBalance,
    HoldingInfo,
    MCPResponse,
    OrderRequest,
    OrderResult,
    PendingOrderInfo,
)


class KiwoomAccountClient:
    """계좌/잔고 응답 정규화"""

    def __init__(self, rest_client: KiwoomRESTClient) -> None:
        self._rest_client = rest_client
        self._account_snapshot: dict[str, Any] | None = None
        self._account_snapshot_cached_at: datetime | None = None
        self._account_snapshot_ttl = timedelta(seconds=1)
        self._account_snapshot_lock = asyncio.Lock()

    async def get_balance(self) -> AccountBalance:
        data = await self._get_account_snapshot()
        self._ensure_success(data)
        total_asset = _abs_float(data.get("prsm_dpst_aset_amt"))
        stock_value = _abs_float(data.get("tot_evlt_amt"))
        if total_asset <= 0 and stock_value > 0:
            total_asset = stock_value
        if total_asset < stock_value:
            logger.warning(
                "키움 잔고 응답 불일치 보정: total_asset={:,.0f} < stock_value={:,.0f}",
                total_asset,
                stock_value,
            )
            total_asset = stock_value

        return AccountBalance(
            total_asset=total_asset,
            cash=max(total_asset - stock_value, 0.0),
            stock_value=stock_value,
            total_pnl=_signed_float(data.get("tot_evlt_pl")),
            total_pnl_rate=_signed_float(data.get("tot_prft_rt")),
            is_valid=_return_code(data) == 0,
        )

    async def get_holdings(self) -> list[HoldingInfo]:
        data = await self._get_account_snapshot()
        self._ensure_success(data)
        holdings = []
        for item in data.get("acnt_evlt_remn_indv_tot", []):
            holdings.append(
                HoldingInfo(
                    symbol=item.get("stk_cd", ""),
                    name=item.get("stk_nm", ""),
                    quantity=_signed_int(item.get("rmnd_qty")),
                    avg_buy_price=_abs_float(item.get("pur_pric")),
                    current_price=_abs_float(item.get("cur_prc")),
                    pnl=_signed_float(item.get("evltv_prft")),
                    pnl_rate=_signed_float(item.get("prft_rt")),
                )
            )
        return holdings

    async def get_pending_orders(self) -> list[PendingOrderInfo]:
        response = await self._rest_client.request(
            api_id="ka10075",
            endpoint="/api/dostk/acnt",
            body={
                "all_stk_tp": "0",
                "trde_tp": "0",
                "stk_cd": "",
                "stex_tp": "0",
            },
        )
        self._ensure_success(response.body)
        orders = []
        for item in response.body.get("oso", []):
            orders.append(
                PendingOrderInfo(
                    order_id=item.get("ord_no", ""),
                    symbol=item.get("stk_cd", ""),
                    name=item.get("stk_nm", ""),
                    side="매수" if "매수" in item.get("io_tp_nm", "") else "매도",
                    order_qty=_signed_int(item.get("ord_qty")),
                    filled_qty=_signed_int(item.get("cntr_qty")),
                    remaining_qty=_signed_int(item.get("oso_qty")),
                    order_price=_abs_float(item.get("ord_pric")),
                    order_time=item.get("tm", ""),
                )
            )
        return orders

    def invalidate_cache(self) -> None:
        self._account_snapshot = None
        self._account_snapshot_cached_at = None

    async def _get_account_snapshot(self) -> dict[str, Any]:
        cached = self._get_cached_account_snapshot()
        if cached is not None:
            return cached

        async with self._account_snapshot_lock:
            cached = self._get_cached_account_snapshot()
            if cached is not None:
                return cached

            response = await self._rest_client.request(
                api_id="kt00017",
                endpoint="/api/dostk/acnt",
                body={"qry_tp": "1", "dmst_stex_tp": "KRX"},
            )
            if self._should_use_mock_cash_fallback(response.body):
                # Kiwoom 모의투자에서는 계좌평가 잔고 TR이 막히는 경우가 있어
                # mock cash seed 값을 주는 응답으로 한 번만 폴백한다.
                response = await self._rest_client.request(
                    api_id="kt00018",
                    endpoint="/api/dostk/acnt",
                    body={"qry_tp": "1", "dmst_stex_tp": "KRX"},
                )
            if _return_code(response.body) == 0:
                self._account_snapshot = response.body
                self._account_snapshot_cached_at = datetime.now()
            return response.body

    def _get_cached_account_snapshot(self) -> dict[str, Any] | None:
        if self._account_snapshot is None or self._account_snapshot_cached_at is None:
            return None
        if datetime.now() - self._account_snapshot_cached_at > self._account_snapshot_ttl:
            return None
        return self._account_snapshot

    @staticmethod
    def _ensure_success(data: dict[str, Any]) -> None:
        if _return_code(data) == 0:
            return
        raise RuntimeError(data.get("return_msg", "키움 계좌 조회 실패"))

    def _should_use_mock_cash_fallback(self, data: dict[str, Any]) -> bool:
        if not self._rest_client.is_paper_trading:
            return False
        if _return_code(data) == 0:
            return False
        return "RC9000" in str(data.get("return_msg", ""))


class KiwoomMarketDataClient:
    """시세/차트 응답 정규화"""

    def __init__(self, rest_client: KiwoomRESTClient) -> None:
        self._rest_client = rest_client
        self._quote_cache: dict[tuple[str, str], tuple[datetime, MCPResponse]] = {}
        self._quote_cache_ttl = timedelta(seconds=1)

    async def get_current_price(self, symbol: str, market: str = "KRX") -> MCPResponse:
        if not _is_domestic_market(market):
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")

        cache_key = (symbol, market)
        cached = self._quote_cache.get(cache_key)
        if cached and datetime.now() - cached[0] <= self._quote_cache_ttl:
            return cached[1]

        response = await self._rest_client.request(
            api_id="ka10001",
            endpoint="/api/dostk/stkinfo",
            body={"stk_cd": symbol},
        )
        data = response.body
        if _return_code(data) != 0:
            return MCPResponse(success=False, error=data.get("return_msg", "현재가 조회 실패"))

        normalized = MCPResponse(success=True, data={
            **data,
            "price": _abs_float(data.get("cur_prc")),
            "current_price": _abs_float(data.get("cur_prc")),
            "change": _signed_float(data.get("pred_pre")),
            "change_rate": _signed_float(data.get("flu_rt")),
            "volume": _signed_int(data.get("trde_qty")),
        })
        self._quote_cache[cache_key] = (datetime.now(), normalized)
        return normalized

    async def get_daily_price(
        self,
        symbol: str,
        period: str = "D",
        count: int = 30,
        market: str = "KRX",
    ) -> MCPResponse:
        if not _is_domestic_market(market):
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")

        response = await self._rest_client.request(
            api_id="ka10081",
            endpoint="/api/dostk/chart",
            body={
                "stk_cd": symbol,
                "base_dt": datetime.now().strftime("%Y%m%d"),
                "upd_stkpc_tp": "1",
            },
        )
        data = response.body
        if _return_code(data) != 0:
            return MCPResponse(success=False, error=data.get("return_msg", "일봉 조회 실패"))

        return MCPResponse(success=True, data={
            **data,
            "prices": _normalize_chart_rows(data, count=count, time_key="date"),
        })

    async def get_minute_price(
        self,
        symbol: str,
        period: str = "5",
        market: str = "KRX",
    ) -> MCPResponse:
        if not _is_domestic_market(market):
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")

        response = await self._rest_client.request(
            api_id="ka10080",
            endpoint="/api/dostk/chart",
            body={
                "stk_cd": symbol,
                "tic_scope": period,
                "upd_stkpc_tp": "1",
            },
        )
        data = response.body
        if _return_code(data) != 0:
            return MCPResponse(success=False, error=data.get("return_msg", "분봉 조회 실패"))

        return MCPResponse(success=True, data={
            **data,
            "prices": _normalize_chart_rows(data, count=None, time_key="time"),
        })

    async def get_volume_rank(self, market: str = "KRX") -> MCPResponse:
        if not _is_domestic_market(market):
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")

        response = await self._rest_client.request(
            api_id="ka10023",
            endpoint="/api/dostk/rkinfo",
            body={
                "mrkt_tp": _to_rank_market_code(market),
                "sort_tp": "1",
                "tm_tp": "1",
                "trde_qty_tp": "10",
                "tm": "5",
                "stk_cnd": "20",
                "pric_tp": "0",
                "stex_tp": _to_rank_exchange_code(market),
            },
        )
        data = response.body
        if _return_code(data) != 0:
            return MCPResponse(success=False, error=data.get("return_msg", "거래량 순위 조회 실패"))

        rows = data.get("trde_qty_sdnin", [])
        return MCPResponse(success=True, data={
            **data,
            "stocks": _normalize_rank_rows(rows),
        })

    async def get_fluctuation_rank(self, sort: str, market: str = "KRX") -> MCPResponse:
        if not _is_domestic_market(market):
            return MCPResponse(success=False, error="Kiwoom은 국내주식만 지원합니다")

        sort_tp = "1" if sort == "top" else "3"
        response = await self._rest_client.request(
            api_id="ka10027",
            endpoint="/api/dostk/rkinfo",
            body={
                "mrkt_tp": _to_rank_market_code(market),
                "sort_tp": sort_tp,
                "trde_qty_cnd": "0010",
                "stk_cnd": "0",
                "crd_cnd": "0",
                "updown_incls": "1",
                "pric_cnd": "0",
                "trde_prica_cnd": "0",
                "stex_tp": _to_rank_exchange_code(market),
            },
        )
        data = response.body
        if _return_code(data) != 0:
            return MCPResponse(success=False, error=data.get("return_msg", "등락률 순위 조회 실패"))

        rows = data.get("pred_pre_flu_rt_upper", [])
        return MCPResponse(success=True, data={
            **data,
            "stocks": _normalize_rank_rows(rows),
        })


class KiwoomOrderExecutor:
    """주문 응답 정규화"""

    def __init__(self, rest_client: KiwoomRESTClient) -> None:
        self._rest_client = rest_client

    async def execute(self, request: OrderRequest) -> OrderResult:
        if not _is_domestic_market(request.market.value):
            return OrderResult(success=False, message="Kiwoom은 국내주식만 지원합니다")

        api_id = "kt10000" if request.side == request.side.BUY else "kt10001"
        response = await self._rest_client.request(
            api_id=api_id,
            endpoint="/api/dostk/ordr",
            body={
                "dmst_stex_tp": _to_exchange(request.market),
                "stk_cd": request.symbol,
                "ord_qty": str(int(request.quantity)),
                "ord_uv": str(int(request.price)) if request.price else "",
                "trde_tp": "0" if request.order_type == OrderType.LIMIT else "3",
            },
        )
        data = response.body
        success = _return_code(data) == 0 and bool(data.get("ord_no"))
        return OrderResult(
            success=success,
            order_id=data.get("ord_no"),
            message=data.get("return_msg", "주문 실행 완료" if success else "주문 실패"),
            filled_quantity=0,
            filled_price=_abs_float(data.get("ord_uv")),
        )

    async def cancel(self, order_id: str, market: str = "KRX") -> OrderResult:
        return OrderResult(
            success=False,
            order_id=order_id,
            message="키움 취소주문은 종목코드/원주문번호 매핑 정리 후 구현 예정입니다",
        )


def _normalize_chart_rows(
    data: dict[str, Any],
    *,
    count: int | None,
    time_key: str,
) -> list[dict[str, Any]]:
    rows = _find_chart_rows(data)
    if count is not None:
        rows = rows[:count]

    normalized = []
    for row in rows:
        normalized.append({
            time_key: row.get("dt") or row.get("tm") or row.get("date") or row.get("time") or "",
            "open": _abs_float(row.get("open_pric") or row.get("open")),
            "high": _abs_float(row.get("high_pric") or row.get("high")),
            "low": _abs_float(row.get("low_pric") or row.get("low")),
            "close": _abs_float(row.get("close_pric") or row.get("cur_prc") or row.get("close")),
            "volume": _signed_int(row.get("trde_qty") or row.get("volume")),
        })
    return normalized


def _normalize_rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append({
            "symbol": row.get("stk_cd", ""),
            "name": row.get("stk_nm", ""),
            "price": _abs_float(row.get("cur_prc")),
            "current_price": _abs_float(row.get("cur_prc")),
            "change": _signed_float(row.get("pred_pre")),
            "change_rate": _signed_float(row.get("flu_rt")),
            "volume": _signed_int(row.get("now_trde_qty") or row.get("trde_qty")),
            "trade_amount": _signed_int(row.get("acml_trde_prica") or row.get("trde_prica")),
        })
    return normalized


def _find_chart_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    for value in data.values():
        if not isinstance(value, list) or not value:
            continue
        first = value[0]
        if not isinstance(first, dict):
            continue
        if {"dt", "tm"} & set(first.keys()) or {"close_pric", "cur_prc"} & set(first.keys()):
            return value
    return []


def _is_domestic_market(market: str) -> bool:
    return market.upper() in {Market.KRX.value, Market.KOSPI.value, Market.KOSDAQ.value}


def _to_exchange(market: Market) -> str:
    if market in {Market.KRX, Market.KOSPI, Market.KOSDAQ}:
        return "KRX"
    return market.value


def _to_rank_market_code(market: str) -> str:
    market_upper = market.upper()
    if market_upper == Market.KOSPI.value:
        return "001"
    if market_upper == Market.KOSDAQ.value:
        return "101"
    return "000"


def _to_rank_exchange_code(market: str) -> str:
    market_upper = market.upper()
    if market_upper in {Market.KRX.value, Market.KOSPI.value, Market.KOSDAQ.value}:
        return "1"
    return "3"


def _return_code(data: dict[str, Any]) -> int:
    try:
        return int(data.get("return_code", 0))
    except (TypeError, ValueError):
        return -1


def _clean_number(value: Any) -> str:
    return str(value or "").replace(",", "").strip()


def _abs_float(value: Any) -> float:
    cleaned = _clean_number(value)
    if not cleaned:
        return 0.0
    try:
        return abs(float(cleaned))
    except ValueError:
        return 0.0


def _signed_float(value: Any) -> float:
    cleaned = _clean_number(value)
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _signed_int(value: Any) -> int:
    cleaned = _clean_number(value)
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except ValueError:
        return 0
