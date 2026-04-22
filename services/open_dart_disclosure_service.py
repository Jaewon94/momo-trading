"""OpenDART 공시 수집 서비스."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from core.config import settings
from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


class OpenDartDisclosureService:
    BASE_URL = "https://opendart.fss.or.kr"
    NO_DATA_STATUS = {"013"}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.OPEN_DART_API_KEY
        self._transport = transport

    async def fetch_recent_disclosures(
        self,
        *,
        days: int = 1,
        page_count: int = 50,
        corp_code: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._api_key:
            raise RuntimeError("OPEN_DART_API_KEY가 필요합니다")

        end_date = now_kst().date()
        start_date = end_date - timedelta(days=max(int(days), 1) - 1)
        params = {
            "crtfc_key": self._api_key,
            "bgn_de": start_date.strftime("%Y%m%d"),
            "end_de": end_date.strftime("%Y%m%d"),
            "last_reprt_at": "Y",
            "page_count": max(int(page_count), 1),
        }
        if corp_code:
            params["corp_code"] = corp_code

        async with httpx.AsyncClient(
            base_url=self.BASE_URL,
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
        ) as client:
            response = await client.get("/api/list.json", params=params)
            response.raise_for_status()
            payload = response.json()

        status = str(payload.get("status") or "")
        if status in self.NO_DATA_STATUS:
            return []

        if status != "000":
            raise RuntimeError(f"OpenDART 조회 실패: {payload.get('message', 'unknown')}")

        return [self._to_news_item(item) for item in payload.get("list", [])]

    async def fetch_and_ingest(
        self,
        session,
        *,
        days: int = 1,
        page_count: int = 50,
        corp_code: str | None = None,
    ) -> dict[str, int]:
        items = await self.fetch_recent_disclosures(
            days=days,
            page_count=page_count,
            corp_code=corp_code,
        )
        return await news_ingest_service.ingest_items(session, items)

    @staticmethod
    def _to_news_item(item: dict[str, Any]) -> dict[str, Any]:
        rcept_no = str(item.get("rcept_no") or "").strip()
        stock_code = str(item.get("stock_code") or "").strip()
        corp_name = str(item.get("corp_name") or "").strip()
        report_nm = str(item.get("report_nm") or "").strip()
        receipt_date = datetime.strptime(str(item.get("rcept_dt") or ""), "%Y%m%d").replace(tzinfo=KST)
        title = " · ".join(part for part in [corp_name, report_nm] if part)
        return {
            "source_code": "DART",
            "title": title or report_nm or corp_name or "공시",
            "published_at": receipt_date.isoformat(),
            "symbols": [stock_code] if stock_code else [],
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else None,
            "external_id": rcept_no or None,
            "summary": report_nm or None,
            "metadata": {
                "corp_name": corp_name,
                "corp_cls": item.get("corp_cls"),
                "report_nm": report_nm,
                "rcept_no": rcept_no,
                "rm": item.get("rm"),
            },
        }


open_dart_disclosure_service = OpenDartDisclosureService()
