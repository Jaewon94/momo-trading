"""뉴스 아이템 저장소."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news_item import NewsItem
from repositories.async_base_repository import AsyncBaseRepository
from trading.symbols import normalize_krx_symbol


class NewsItemRepository(AsyncBaseRepository[NewsItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(NewsItem, session)

    async def get_by_dedupe_hash(self, dedupe_hash: str) -> NewsItem | None:
        stmt = select(NewsItem).where(NewsItem.dedupe_hash == dedupe_hash).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        symbol: str | None = None,
        source_code: str | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        sentiment_label: str | None = None,
        query: str | None = None,
    ) -> list[NewsItem]:
        stmt = select(NewsItem)
        normalized_symbol = normalize_krx_symbol(symbol)
        if normalized_symbol:
            stmt = stmt.where(NewsItem.symbols_csv.like(f"%,{normalized_symbol},%"))
        if source_code:
            stmt = stmt.where(NewsItem.source_code == str(source_code).upper().strip())
        if published_from:
            stmt = stmt.where(NewsItem.published_at >= published_from)
        if published_to:
            stmt = stmt.where(NewsItem.published_at <= published_to)
        if sentiment_label:
            stmt = stmt.where(NewsItem.sentiment_label == str(sentiment_label).upper().strip())
        if query:
            pattern = f"%{str(query).strip()}%"
            stmt = stmt.where(
                or_(
                    NewsItem.title.ilike(pattern),
                    NewsItem.summary.ilike(pattern),
                    NewsItem.body.ilike(pattern),
                    NewsItem.source_name.ilike(pattern),
                )
            )
        stmt = (
            stmt.order_by(NewsItem.published_at.desc(), NewsItem.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
