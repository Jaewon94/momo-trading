"""뉴스 수집 1차 인프라: 소스 카탈로그 + 정규화 저장."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news_item import NewsItem
from models.stock import Stock
from repositories.news_item_repository import NewsItemRepository
from trading.symbols import normalize_krx_symbol
from util.time_util import KST, ensure_kst, now_kst


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NewsSourceDefinition:
    code: str
    name: str
    tier: str
    region: str
    official: bool
    trust_score: float
    domains: tuple[str, ...]
    language: str = "ko"


class NewsIngestService:
    """외부 뉴스 수집기들이 공통으로 쓰는 정규화/저장 계층."""

    _CATALOG: dict[str, NewsSourceDefinition] = {
        "DART": NewsSourceDefinition(
            code="DART",
            name="금융감독원 전자공시",
            tier="A",
            region="KR",
            official=True,
            trust_score=1.0,
            domains=("dart.fss.or.kr", "englishdart.fss.or.kr"),
        ),
        "KRX": NewsSourceDefinition(
            code="KRX",
            name="한국거래소 공시/시장공지",
            tier="A",
            region="KR",
            official=True,
            trust_score=1.0,
            domains=("kind.krx.co.kr", "data.krx.co.kr"),
        ),
        "YONHAP": NewsSourceDefinition(
            code="YONHAP",
            name="연합뉴스 경제",
            tier="B",
            region="KR",
            official=False,
            trust_score=0.82,
            domains=("yna.co.kr",),
        ),
        "REUTERS": NewsSourceDefinition(
            code="REUTERS",
            name="Reuters Markets",
            tier="B",
            region="GLOBAL",
            official=False,
            trust_score=0.9,
            domains=("reuters.com",),
            language="en",
        ),
        "BLOOMBERG": NewsSourceDefinition(
            code="BLOOMBERG",
            name="Bloomberg Markets",
            tier="B",
            region="GLOBAL",
            official=False,
            trust_score=0.88,
            domains=("bloomberg.com",),
            language="en",
        ),
        "CNBC": NewsSourceDefinition(
            code="CNBC",
            name="CNBC Markets",
            tier="B",
            region="GLOBAL",
            official=False,
            trust_score=0.84,
            domains=("cnbc.com",),
            language="en",
        ),
        "NASDAQ": NewsSourceDefinition(
            code="NASDAQ",
            name="Nasdaq Markets",
            tier="B",
            region="GLOBAL",
            official=True,
            trust_score=0.86,
            domains=("nasdaq.com",),
            language="en",
        ),
        "INVESTING": NewsSourceDefinition(
            code="INVESTING",
            name="Investing.com Stock Market News",
            tier="B",
            region="GLOBAL",
            official=False,
            trust_score=0.83,
            domains=("investing.com",),
            language="en",
        ),
        "SEEKING_ALPHA": NewsSourceDefinition(
            code="SEEKING_ALPHA",
            name="Seeking Alpha All News",
            tier="B",
            region="GLOBAL",
            official=False,
            trust_score=0.81,
            domains=("seekingalpha.com",),
            language="en",
        ),
    }

    def get_source_catalog(self, *, include_foreign: bool = True) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for source in sorted(self._CATALOG.values(), key=lambda item: (item.tier, item.region, item.code)):
            if not include_foreign and source.region != "KR":
                continue
            payload = asdict(source)
            payload["domains"] = list(source.domains)
            items.append(payload)
        return items

    async def ingest_items(self, session: AsyncSession, items: list[dict[str, Any]]) -> dict[str, int]:
        detailed = await self.ingest_items_detailed(session, items)
        return detailed["summary"]

    async def ingest_items_detailed(self, session: AsyncSession, items: list[dict[str, Any]]) -> dict[str, Any]:
        repo = NewsItemRepository(session)
        created = 0
        duplicates = 0
        skipped = 0
        created_items: list[dict[str, Any]] = []
        if not items:
            return {
                "summary": {
                    "received": 0,
                    "created": 0,
                    "duplicates": 0,
                    "skipped": 0,
                },
                "created_items": [],
            }
        items = await self._attach_symbols(session, items)

        for raw in items:
            normalized = self._normalize_item(raw)
            if not normalized:
                skipped += 1
                continue

            existing = await repo.get_by_dedupe_hash(normalized["dedupe_hash"])
            if existing:
                duplicates += 1
                continue

            saved = await repo.create(NewsItem(**normalized))
            created += 1
            created_items.append(self.serialize_item(saved))

        return {
            "summary": {
                "received": len(items),
                "created": created,
                "duplicates": duplicates,
                "skipped": skipped,
            },
            "created_items": created_items,
        }

    async def list_items(
        self,
        session: AsyncSession,
        *,
        limit: int = 50,
        offset: int = 0,
        symbol: str | None = None,
        source_code: str | None = None,
    ) -> list[NewsItem]:
        repo = NewsItemRepository(session)
        return await repo.get_recent(
            limit=limit,
            offset=offset,
            symbol=symbol,
            source_code=source_code,
        )

    async def _attach_symbols(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stock_rows = [
            {
                "symbol": normalize_krx_symbol(symbol),
                "name": str(name or "").strip(),
                "category": str(category or "").strip(),
            }
            for symbol, name, category in (
                await session.execute(
                    select(Stock.symbol, Stock.name, Stock.category)
                    .where(Stock.is_active == True)  # noqa: E712
                    .order_by(Stock.name.desc(), Stock.created_at.desc())
                )
            ).all()
            if str(name or "").strip()
        ]
        stock_rows.sort(key=lambda item: len(item["name"]), reverse=True)
        stock_by_symbol = {
            item["symbol"]: item
            for item in stock_rows
            if item["symbol"]
        }
        category_to_symbols: dict[str, list[str]] = {}
        for item in stock_rows:
            category = item["category"]
            symbol = item["symbol"]
            if not category or not symbol:
                continue
            category_to_symbols.setdefault(category, [])
            if symbol not in category_to_symbols[category]:
                category_to_symbols[category].append(symbol)
        category_rows = sorted(
            [category for category in category_to_symbols.keys() if category],
            key=len,
            reverse=True,
        )

        enriched: list[dict[str, Any]] = []
        for item in items:
            copied = dict(item)
            existing_symbols = self._normalize_symbols(copied.get("symbols"))
            metadata = dict(copied.get("metadata") or {})
            if existing_symbols:
                copied["symbols"] = existing_symbols
                metadata = self._enrich_symbol_metadata(
                    metadata,
                    symbols=existing_symbols,
                    matched_names=[],
                    stock_by_symbol=stock_by_symbol,
                    category_to_symbols=category_to_symbols,
                )
                copied["metadata"] = metadata
                enriched.append(copied)
                continue

            haystack = " ".join([
                str(copied.get("title") or ""),
                str(copied.get("summary") or ""),
                str(metadata.get("translated_title") or ""),
                str(metadata.get("translated_summary") or ""),
            ])
            matching_stocks = []
            for stock in stock_rows:
                name = stock["name"]
                if len(name) < 2:
                    continue
                position = haystack.find(name)
                if position < 0:
                    continue
                matching_stocks.append((position, -len(name), stock))
            matching_stocks.sort(key=lambda item: (item[0], item[1]))

            matched_symbols: list[str] = []
            matched_names: list[str] = []
            seen_names: set[str] = set()
            for _, _, stock in matching_stocks:
                name = stock["name"]
                if name in seen_names:
                    continue
                matched_symbols.append(stock["symbol"])
                matched_names.append(name)
                seen_names.add(name)
                if len(matched_symbols) >= 5:
                    break

            matched_categories: list[str] = []
            seen_categories: set[str] = set()
            for category in category_rows:
                if len(category) < 2:
                    continue
                if haystack.find(category) < 0:
                    continue
                if category in seen_categories:
                    continue
                matched_categories.append(category)
                seen_categories.add(category)
                if len(matched_categories) >= 3:
                    break

            inferred_symbols = matched_symbols
            if not inferred_symbols and matched_categories:
                inferred_symbols = list(category_to_symbols.get(matched_categories[0]) or [])[:8]

            copied["symbols"] = inferred_symbols
            enriched_metadata = self._enrich_symbol_metadata(
                metadata,
                symbols=inferred_symbols,
                matched_names=matched_names,
                stock_by_symbol=stock_by_symbol,
                category_to_symbols=category_to_symbols,
            )
            if matched_categories:
                enriched_metadata.setdefault("matched_sector_labels", matched_categories)
            copied["metadata"] = enriched_metadata
            enriched.append(copied)

        return enriched

    def _enrich_symbol_metadata(
        self,
        metadata: dict[str, Any],
        *,
        symbols: list[str],
        matched_names: list[str],
        stock_by_symbol: dict[str, dict[str, str]],
        category_to_symbols: dict[str, list[str]],
    ) -> dict[str, Any]:
        enriched = dict(metadata or {})
        normalized_symbols = self._normalize_symbols(symbols)
        if not normalized_symbols:
            return enriched

        if matched_names:
            enriched["matched_stock_names"] = matched_names

        enriched["related_symbols"] = normalized_symbols
        primary_symbol = normalized_symbols[0]
        enriched.setdefault("primary_symbol", primary_symbol)
        enriched.setdefault("symbol_weights", {primary_symbol: 1.0})
        if len(normalized_symbols) > 1:
            enriched.setdefault(
                "related_symbol_weights",
                {symbol: 0.72 for symbol in normalized_symbols[1:]},
            )

        primary_stock = stock_by_symbol.get(primary_symbol) or {}
        category = str(primary_stock.get("category") or "").strip()
        if not category:
            return enriched

        sector_symbols = []
        seen_sector_symbols: set[str] = set()
        for symbol in normalized_symbols:
            stock = stock_by_symbol.get(symbol) or {}
            if str(stock.get("category") or "").strip() != category:
                continue
            if symbol in seen_sector_symbols:
                continue
            sector_symbols.append(symbol)
            seen_sector_symbols.add(symbol)
        for symbol in category_to_symbols.get(category) or []:
            if symbol in seen_sector_symbols:
                continue
            sector_symbols.append(symbol)
            seen_sector_symbols.add(symbol)
        if sector_symbols:
            enriched.setdefault("sector_label", category)
            enriched.setdefault("sector_symbols", sector_symbols[:8])
            if len(sector_symbols) > 1:
                enriched.setdefault("sector_relevance", 1.08)

        return enriched

    def serialize_item(self, item: NewsItem) -> dict[str, Any]:
        metadata = self._load_metadata(getattr(item, "metadata_json", None))
        title = getattr(item, "title", None)
        summary = getattr(item, "summary", None)
        display_title = str(metadata.get("translated_title") or title or "").strip() or title
        display_summary = str(metadata.get("translated_summary") or summary or "").strip() or summary
        return {
            "id": item.id,
            "source_code": item.source_code,
            "source_name": item.source_name,
            "source_tier": item.source_tier,
            "region": item.region,
            "official": item.official,
            "language": item.language,
            "title": title,
            "summary": summary,
            "display_title": display_title,
            "display_summary": display_summary,
            "original_title": title,
            "original_summary": summary,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "sentiment_label": item.sentiment_label,
            "sentiment_score": float(item.sentiment_score or 0.0),
            "impact_score": float(item.impact_score or 0.0),
            "trust_score": float(item.trust_score or 0.0),
            "symbols": self._symbols_from_csv(item.symbols_csv),
            "translation_provider": metadata.get("translation_provider"),
            "translation_status": metadata.get("translation_status"),
            "metadata": metadata,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def _normalize_item(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        source_code = str(raw.get("source_code") or "").upper().strip()
        title = self._normalize_title(raw.get("title"))
        if not source_code or not title:
            return None

        source = self._CATALOG.get(source_code) or NewsSourceDefinition(
            code=source_code,
            name=source_code,
            tier="C",
            region="UNKNOWN",
            official=False,
            trust_score=0.5,
            domains=(),
            language=str(raw.get("language") or "ko"),
        )
        published_at = self._parse_datetime(raw.get("published_at"))
        symbols = self._normalize_symbols(raw.get("symbols"))
        metadata = raw.get("metadata") or {}
        external_id = str(raw.get("external_id") or "").strip() or None
        url = str(raw.get("url") or "").strip() or None
        dedupe_hash = self._build_dedupe_hash(
            source_code=source.code,
            external_id=external_id,
            url=url,
            title=title,
            published_at=published_at,
        )

        return {
            "source_code": source.code,
            "source_name": source.name,
            "source_tier": source.tier,
            "region": source.region,
            "official": source.official,
            "language": str(raw.get("language") or source.language or "ko"),
            "title": title,
            "summary": self._clean_text(raw.get("summary")),
            "body": self._clean_text(raw.get("body")),
            "url": url,
            "external_id": external_id,
            "published_at": published_at,
            "sentiment_label": raw.get("sentiment_label"),
            "sentiment_score": float(raw.get("sentiment_score", 0.5) or 0.5),
            "impact_score": float(raw.get("impact_score", 0.0) or 0.0),
            "trust_score": float(raw.get("trust_score", source.trust_score) or source.trust_score),
            "symbols_csv": self._symbols_to_csv(symbols),
            "metadata_json": json.dumps(metadata, ensure_ascii=False) if metadata else None,
            "dedupe_hash": dedupe_hash,
        }

    @staticmethod
    def _normalize_title(value: Any) -> str:
        text = str(value or "").strip()
        return _WHITESPACE_RE.sub(" ", text)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return _WHITESPACE_RE.sub(" ", text)

    @staticmethod
    def _load_metadata(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return ensure_kst(value)
        text = str(value or "").strip()
        if not text:
            return now_kst()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed

    @staticmethod
    def _normalize_symbols(symbols: Any) -> list[str]:
        if not symbols:
            return []
        raw_items = symbols if isinstance(symbols, list) else [symbols]
        normalized = []
        for item in raw_items:
            symbol = normalize_krx_symbol(str(item or "").strip())
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @staticmethod
    def _symbols_to_csv(symbols: list[str]) -> str:
        if not symbols:
            return ""
        return f",{','.join(symbols)},"

    @staticmethod
    def _symbols_from_csv(symbols_csv: str | None) -> list[str]:
        text = str(symbols_csv or "").strip(",")
        if not text:
            return []
        return [item for item in text.split(",") if item]

    @staticmethod
    def _build_dedupe_hash(
        *,
        source_code: str,
        external_id: str | None,
        url: str | None,
        title: str,
        published_at: datetime,
    ) -> str:
        identity = external_id or url or title.lower()
        payload = f"{source_code}|{identity}|{published_at.isoformat()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


news_ingest_service = NewsIngestService()
