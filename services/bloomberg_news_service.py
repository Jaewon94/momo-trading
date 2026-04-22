"""Bloomberg 뉴스 sitemap 수집 서비스."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


class BloombergNewsService:
    SITEMAP_URL = "https://www.bloomberg.com/feeds/bbiz/sitemap_news.xml"
    _NS = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_recent_news(self, *, limit: int = 30) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": "momo-trading/1.0 (+https://localhost:9000/admin)"},
        ) as client:
            response = await client.get(self.SITEMAP_URL)
            response.raise_for_status()

        items = self._parse_sitemap(response.text)
        return items[: max(int(limit), 1)]

    async def fetch_and_ingest(self, db, *, limit: int = 30) -> dict[str, int]:
        items = await self.fetch_recent_news(limit=limit)
        return await news_ingest_service.ingest_items(db, items)

    def _parse_sitemap(self, xml_text: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        items: list[dict[str, Any]] = []

        for node in root.findall("sm:url", self._NS):
            url = self._clean_text(node.findtext("sm:loc", default="", namespaces=self._NS))
            title = self._clean_text(node.findtext("news:news/news:title", default="", namespaces=self._NS))
            if not url or not title:
                continue
            language = self._clean_text(
                node.findtext("news:news/news:publication/news:language", default="en", namespaces=self._NS)
            ) or "en"
            published_at = self._parse_published_at(
                node.findtext("news:news/news:publication_date", default="", namespaces=self._NS)
            )
            keywords = self._split_csv(
                node.findtext("news:news/news:keywords", default="", namespaces=self._NS)
            )
            stock_tickers = self._split_csv(
                node.findtext("news:news/news:stock_tickers", default="", namespaces=self._NS)
            )
            items.append({
                "source_code": "BLOOMBERG",
                "language": language,
                "title": title,
                "summary": self._build_summary(keywords, stock_tickers),
                "url": url,
                "published_at": published_at.isoformat(),
                "symbols": [],
                "external_id": self._extract_external_id(url),
                "metadata": {
                    "publisher": self._clean_text(
                        node.findtext("news:news/news:publication/news:name", default="", namespaces=self._NS)
                    ) or "Bloomberg",
                    "keywords": keywords,
                    "stock_tickers": stock_tickers,
                },
            })
        return items

    @staticmethod
    def _build_summary(keywords: list[str], stock_tickers: list[str]) -> str | None:
        bits: list[str] = []
        if keywords:
            bits.append(f"Keywords: {', '.join(keywords)}")
        if stock_tickers:
            bits.append(f"Tickers: {', '.join(stock_tickers)}")
        return " | ".join(bits) if bits else None

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime:
        text = str(value or "").strip()
        if not text:
            return now_kst()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    @staticmethod
    def _split_csv(value: str | None) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]

    @staticmethod
    def _extract_external_id(url: str | None) -> str | None:
        if not url:
            return None
        path = urlparse(url).path.strip("/")
        if not path:
            return None
        return path.split("/")[-1] or None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


bloomberg_news_service = BloombergNewsService()
