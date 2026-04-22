"""Nasdaq Markets RSS 수집 서비스."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx
from loguru import logger

from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


@dataclass(frozen=True)
class NasdaqFeed:
    category: str
    url: str


class NasdaqNewsService:
    RSS_FEEDS = (
        NasdaqFeed("Markets", "https://www.nasdaq.com/feed/rssoutbound?category=Markets"),
    )
    REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 momo-trading/1.0"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Referer": "https://www.nasdaq.com/nasdaq-RSS-Feeds",
    }

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_count: int = 3,
        retry_backoff_sec: float = 0.25,
    ) -> None:
        self._transport = transport
        self._retry_count = max(int(retry_count), 1)
        self._retry_backoff_sec = max(float(retry_backoff_sec), 0.0)

    async def fetch_recent_news(self, *, limit: int = 30) -> list[dict[str, Any]]:
        errors: list[str] = []
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=8.0, read=12.0),
            follow_redirects=True,
            headers=self.REQUEST_HEADERS,
            http2=False,
        ) as client:
            for feed in self.RSS_FEEDS:
                try:
                    items = await self._fetch_feed_with_retries(client, feed)
                except RuntimeError as exc:
                    errors.append(str(exc))
                    logger.warning("Nasdaq RSS fetch failed: {}", exc)
                    continue
                return items[: max(int(limit), 1)]

        reason = "; ".join(errors) if errors else "configured RSS feeds unavailable"
        raise RuntimeError(f"Nasdaq 소스 응답 지연 또는 비정상 연결: {reason}")

    async def fetch_and_ingest(self, db, *, limit: int = 30) -> dict[str, int]:
        items = await self.fetch_recent_news(limit=limit)
        return await news_ingest_service.ingest_items(db, items)

    async def _fetch_feed_with_retries(
        self,
        client: httpx.AsyncClient,
        feed: NasdaqFeed,
    ) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_count + 1):
            response_text = ""
            try:
                response = await client.get(feed.url)
                response_text = response.text
                response.raise_for_status()
                return self._parse_rss(response_text, category=feed.category)
            except ElementTree.ParseError as exc:
                snippet = self._body_snippet(response_text)
                raise RuntimeError(f"{feed.category}: RSS XML 파싱 실패: {snippet}") from exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code != 429 and status_code < 500:
                    break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc

            if attempt < self._retry_count:
                await asyncio.sleep(self._retry_backoff_sec * attempt)

        if last_error is None:
            raise RuntimeError(f"{feed.category}: unknown error")

        raise RuntimeError(
            f"{feed.category}: {last_error.__class__.__name__}: {last_error}"
        ) from last_error

    def _parse_rss(self, xml_text: str, *, category: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
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
                "source_code": "NASDAQ",
                "language": "en",
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": published_at.isoformat(),
                "symbols": [],
                "external_id": external_id,
                "metadata": {
                    "publisher": "Nasdaq",
                    "category": category,
                },
            })
        return items

    @staticmethod
    def _body_snippet(value: str, *, limit: int = 120) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            return "empty response"
        return text[:limit]

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime:
        text = str(value or "").strip()
        if not text:
            return now_kst()
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


nasdaq_news_service = NasdaqNewsService()
