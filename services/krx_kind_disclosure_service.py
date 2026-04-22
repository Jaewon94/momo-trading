"""KIND 오늘의공시 수집 서비스 (RSS 우선, HTML 폴백)."""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse
from xml.etree import ElementTree

import httpx

from services.news_ingest_service import news_ingest_service
from util.time_util import KST, now_kst


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SYMBOL_RE = re.compile(r"\b(\d{6})\b")
_EXTERNAL_ID_RE = re.compile(r"(\d{8,})")


class _KrxTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._in_tbody = False
        self._in_td = False
        self._current_row: list[dict[str, Any]] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._current_href: str | None = None
        self._current_onclick: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tbody":
            self._in_tbody = True
            return
        if not self._in_tbody:
            return
        if tag == "tr":
            self._current_row = []
            return
        if tag == "td" and self._current_row is not None:
            self._in_td = True
            self._current_cell = {
                "text_parts": [],
                "href": None,
                "onclick": None,
                "colspan": attrs_dict.get("colspan"),
            }
            return
        if tag == "a" and self._current_cell is not None:
            self._current_href = attrs_dict.get("href")
            self._current_onclick = attrs_dict.get("onclick")
            self._current_cell["href"] = self._current_href
            self._current_cell["onclick"] = self._current_onclick

    def handle_endtag(self, tag: str) -> None:
        if tag == "tbody":
            self._in_tbody = False
            return
        if not self._in_tbody:
            return
        if tag == "a":
            self._current_href = None
            self._current_onclick = None
            return
        if tag == "td" and self._current_cell is not None and self._current_row is not None:
            text = _WS_RE.sub(" ", "".join(self._current_cell["text_parts"])).strip()
            self._current_row.append({
                "text": text,
                "href": self._current_cell.get("href"),
                "onclick": self._current_cell.get("onclick"),
                "colspan": self._current_cell.get("colspan"),
            })
            self._current_cell = None
            self._in_td = False
            return
        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append({"cells": self._current_row})
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell["text_parts"].append(unescape(data))

    def handle_entityref(self, name: str) -> None:
        if self._current_cell is not None:
            self._current_cell["text_parts"].append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self._current_cell is not None:
            self._current_cell["text_parts"].append(unescape(f"&#{name};"))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def unknown_decl(self, data: str) -> None:  # pragma: no cover - defensive
        return

    def feed(self, data: str) -> None:
        super().feed(data)
        if self._current_cell is not None and self._current_row is not None:
            self.handle_endtag("td")
        if self._current_row is not None:
            self.handle_endtag("tr")


class KrxKindDisclosureService:
    BASE_URL = "https://kind.krx.co.kr"
    RSS_PATH = "/disclosure/rsstodaydistribute.do"
    HTML_PATH = "/disclosure/todaydisclosure.do"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch_recent_disclosures(
        self,
        *,
        page_count: int = 50,
        market_type: str = "0",
        rep_issuance_code: str | None = None,
        search_corp_name: str | None = None,
    ) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.BASE_URL,
            transport=self._transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
        ) as client:
            rss_response = await client.get(
                self.RSS_PATH,
                params={
                    "method": "searchRssTodayDistribute",
                    "repIsuSrtCd": rep_issuance_code or "",
                    "mktTpCd": market_type,
                    "searchCorpName": search_corp_name or "",
                    "currentPageSize": max(int(page_count), 1),
                },
            )
            rss_response.raise_for_status()
            try:
                content_type = str(rss_response.headers.get("Content-Type") or "").lower()
                if "html" in content_type:
                    raise ElementTree.ParseError("html response")
                items = self._parse_rss(rss_response.text)
                if not rss_response.text.lstrip().startswith("<?xml") and not rss_response.text.lstrip().startswith("<rss"):
                    raise ElementTree.ParseError("non-rss response")
            except ElementTree.ParseError:
                html_response = await client.post(
                    self.HTML_PATH,
                    data={
                        "method": "searchTodayDisclosureSub",
                        "forward": "todaydisclosure_sub",
                        "marketType": market_type,
                        "currentPageSize": max(int(page_count), 1),
                        "pageIndex": 1,
                        "todayFlag": "Y",
                        "repIsuSrtCd": rep_issuance_code or "",
                        "searchCorpName": search_corp_name or "",
                    },
                )
                html_response.raise_for_status()
                return self._parse_html(html_response.text)
            return items

    async def fetch_and_ingest(
        self,
        session,
        *,
        page_count: int = 50,
        market_type: str = "0",
        rep_issuance_code: str | None = None,
        search_corp_name: str | None = None,
    ) -> dict[str, int]:
        items = await self.fetch_recent_disclosures(
            page_count=page_count,
            market_type=market_type,
            rep_issuance_code=rep_issuance_code,
            search_corp_name=search_corp_name,
        )
        return await news_ingest_service.ingest_items(session, items)

    def _parse_rss(self, xml_text: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        if root.tag.lower() != "rss":
            raise ElementTree.ParseError("unexpected root tag")
        items: list[dict[str, Any]] = []
        for node in root.findall("./channel/item"):
            title = self._clean_text(node.findtext("title"))
            link = self._clean_text(node.findtext("link"))
            summary = self._clean_text(node.findtext("description"))
            published_at = self._parse_published_at(
                node.findtext("{http://purl.org/dc/elements/1.1/}date")
                or node.findtext("pubDate")
            )
            raw_text = " ".join(part for part in [title, summary, link] if part)
            items.append({
                "source_code": "KRX",
                "title": title or "KRX 공시",
                "summary": summary,
                "url": link,
                "published_at": published_at.isoformat(),
                "symbols": self._extract_symbols(raw_text),
                "external_id": self._extract_external_id(link),
            })
        return items

    def _parse_html(self, html_text: str) -> list[dict[str, Any]]:
        parser = _KrxTableParser()
        parser.feed(html_text)
        items: list[dict[str, Any]] = []
        for row in parser.rows:
            cells = row.get("cells") or []
            if len(cells) == 1 and "조회된 결과값이 없습니다." in str(cells[0].get("text") or ""):
                return []
            if len(cells) < 4:
                continue
            time_text = self._clean_text(cells[0].get("text"))
            company_text = self._clean_text(cells[1].get("text"))
            title_text = self._clean_text(cells[2].get("text"))
            submitter = self._clean_text(cells[3].get("text"))
            href = cells[2].get("href") or cells[1].get("href")
            onclick = cells[2].get("onclick") or cells[1].get("onclick")
            link = self._normalize_link(href, onclick)
            raw_text = " ".join(part for part in [company_text, title_text, submitter, link] if part)
            title = " · ".join(part for part in [company_text, title_text] if part)
            items.append({
                "source_code": "KRX",
                "title": title or company_text or title_text or "KRX 공시",
                "summary": submitter,
                "url": link,
                "published_at": self._parse_time_text(time_text).isoformat(),
                "symbols": self._extract_symbols(raw_text),
                "external_id": self._extract_external_id(link or onclick),
            })
        return items

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = _TAG_RE.sub(" ", str(value or ""))
        text = _WS_RE.sub(" ", unescape(text)).strip()
        return text or None

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime:
        text = str(value or "").strip()
        if not text:
            return now_kst()
        if "," in text:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=KST)
            return parsed.astimezone(KST)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)

    @staticmethod
    def _parse_time_text(value: str | None) -> datetime:
        text = str(value or "").strip()
        now = now_kst()
        match = re.match(r"(\d{1,2}):(\d{2})", text)
        if not match:
            return now
        return now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0)

    @staticmethod
    def _extract_symbols(text: str | None) -> list[str]:
        found = []
        for symbol in _SYMBOL_RE.findall(str(text or "")):
            if symbol not in found:
                found.append(symbol)
        return found

    @staticmethod
    def _extract_external_id(text: str | None) -> str | None:
        raw = str(text or "")
        parsed = urlparse(raw)
        for value in parse_qs(parsed.query).values():
            if value and value[0].isdigit():
                return value[0]
        match = _EXTERNAL_ID_RE.search(raw)
        return match.group(1) if match else None

    @classmethod
    def _normalize_link(cls, href: str | None, onclick: str | None) -> str | None:
        candidate = str(href or "").strip()
        if candidate and not candidate.lower().startswith("javascript:"):
            return urljoin(cls.BASE_URL, candidate)
        raw = " ".join(part for part in [candidate, str(onclick or "")] if part)
        match = _EXTERNAL_ID_RE.search(raw)
        if match:
            return urljoin(cls.BASE_URL, f"/common/disclsviewer.do?acptno={match.group(1)}")
        return None


krx_kind_disclosure_service = KrxKindDisclosureService()
