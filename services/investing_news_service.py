"""Investing.com Stock Market News RSS 수집 서비스."""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


class InvestingNewsService:
    RSS_URL = "https://www.investing.com/rss/news_25.rss"
    _BARE_AMPERSAND_RE = re.compile(r"&(?!#?\w+;)")
    _INVALID_XML_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_recent_news(self, *, limit: int = 30) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": "momo-trading/1.0 (+https://localhost:9000/admin)"},
        ) as client:
            response = await client.get(self.RSS_URL)
            response.raise_for_status()

        items = self._parse_rss(response.text)
        return items[: max(int(limit), 1)]

    async def fetch_and_ingest(self, db, *, limit: int = 30) -> dict[str, int]:
        items = await self.fetch_recent_news(limit=limit)
        return await news_ingest_service.ingest_items(db, items)

    def _parse_rss(self, xml_text: str) -> list[dict[str, Any]]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            root = ElementTree.fromstring(self._sanitize_xml(xml_text))
        items: list[dict[str, Any]] = []

        for node in root.findall("./channel/item"):
            title = self._clean_text(node.findtext("title"))
            url = self._clean_text(node.findtext("link"))
            if not title or not url:
                continue
            published_at = self._parse_published_at(node.findtext("pubDate"))
            summary = self._clean_text(node.findtext("description"))
            external_id = self._clean_text(node.findtext("guid")) or url.rstrip("/").split("/")[-1]
            items.append({
                "source_code": "INVESTING",
                "language": "en",
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": published_at.isoformat(),
                "symbols": [],
                "external_id": external_id,
                "metadata": {
                    "publisher": "Investing.com",
                    "category": "Stock Market News",
                },
            })
        return items

    @classmethod
    def _sanitize_xml(cls, xml_text: str) -> str:
        text = str(xml_text or "").strip()
        if not text:
            raise ElementTree.ParseError("empty xml")
        closing_index = text.rfind("</rss>")
        if closing_index >= 0:
            text = text[: closing_index + len("</rss>")]
        text = cls._INVALID_XML_RE.sub("", text)
        text = cls._BARE_AMPERSAND_RE.sub("&amp;", text)
        return text

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime:
        text = str(value or "").strip()
        if not text:
            return now_kst()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            parsed = None
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                try:
                    parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return now_kst()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


investing_news_service = InvestingNewsService()
