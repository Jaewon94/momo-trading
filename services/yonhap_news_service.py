"""연합뉴스TV 경제 RSS 수집 서비스."""
from __future__ import annotations

from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.stock import Stock
from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


class YonhapNewsService:
    FEED_URL = "https://www.yonhapnewstv.co.kr/category/news/economy/feed/"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_recent_news(
        self,
        session: AsyncSession,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
                "Referer": "https://www.yonhapnewstv.co.kr/",
            },
        ) as client:
            response = await client.get(self.FEED_URL)
            response.raise_for_status()
        items = self._parse_rss(response.text)[: max(int(limit), 1)]
        if not items:
            return []
        return await news_ingest_service._attach_symbols(session, items)

    async def fetch_and_ingest(
        self,
        session: AsyncSession,
        *,
        limit: int = 30,
    ) -> dict[str, int]:
        items = await self.fetch_recent_news(session, limit=limit)
        return await news_ingest_service.ingest_items(session, items)

    def _parse_rss(self, xml_text: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        channel = root.find("./channel")
        if channel is None:
            return []

        items: list[dict[str, Any]] = []
        for node in channel.findall("./item"):
            title = self._clean_text(node.findtext("title"))
            link = self._clean_text(node.findtext("link"))
            summary = self._clean_text(node.findtext("description"))
            if not title or not link:
                continue
            items.append({
                "source_code": "YONHAP",
                "title": title,
                "summary": summary,
                "url": link,
                "published_at": self._parse_published_at(node.findtext("pubDate")).isoformat(),
                "symbols": [],
                "external_id": self._extract_external_id(link),
                "metadata": {
                    "copyright_notice": "연합뉴스TV RSS는 영리 목적 사용 금지 문구가 있어 운영 정책 검토 필요",
                },
            })
        return items

    @staticmethod
    def _parse_published_at(value: str | None):
        text = str(value or "").strip()
        if not text:
            return now_kst()
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    @staticmethod
    def _extract_external_id(link: str | None) -> str | None:
        if not link:
            return None
        path = urlparse(link).path.strip("/")
        if not path:
            return None
        return path.split("/")[-1] or None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


yonhap_news_service = YonhapNewsService()
