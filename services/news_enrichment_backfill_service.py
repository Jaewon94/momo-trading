"""Backfill deterministic news enrichment for already stored items."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news_item import NewsItem
from repositories.news_item_repository import NewsItemRepository
from services.news_ingest_service import news_ingest_service


class NewsEnrichmentBackfillService:
    async def process(
        self,
        session: AsyncSession,
        *,
        limit: int = 200,
        source_code: str | None = None,
        missing_only: bool = True,
        apply: bool = False,
    ) -> dict[str, Any]:
        candidates = await self._load_candidates(
            session,
            limit=limit,
            source_code=source_code,
            missing_only=missing_only,
        )
        repo = NewsItemRepository(session)
        changed_count = 0
        symbols_attached = 0
        risk_classified = 0
        topic_mapped = 0
        updated_items: list[dict[str, Any]] = []

        for item in candidates:
            proposed = await news_ingest_service.enrich_existing_item(session, item)
            if not proposed:
                continue
            changes = self._diff_item(item, proposed)
            if not changes:
                continue

            changed_count += 1
            metadata = self._load_metadata(proposed.get("metadata_json"))
            if proposed.get("symbols_csv"):
                symbols_attached += 1
            if metadata.get("risk_classifier"):
                risk_classified += 1
            if metadata.get("topic_mapper"):
                topic_mapped += 1
            updated_items.append({
                "id": item.id,
                "source_code": item.source_code,
                "title": item.title,
                "changed_fields": sorted(changes.keys()),
                "symbols": news_ingest_service._symbols_from_csv(proposed.get("symbols_csv")),
                "risk_reason_codes": (metadata.get("risk_classifier") or {}).get("reason_codes", []),
                "topic_categories": (metadata.get("topic_mapper") or {}).get("matched_categories", []),
            })

            if not apply:
                continue
            for field, value in changes.items():
                setattr(item, field, value)
            await repo.update(item)

        logger.debug(
            "뉴스 enrichment backfill {}: 후보 {}건 / 변경 {}건 / 종목 {}건 / 리스크 {}건 / 토픽 {}건",
            "적용" if apply else "DRY_RUN",
            len(candidates),
            changed_count,
            symbols_attached,
            risk_classified,
            topic_mapped,
        )
        return {
            "status": "SUCCESS" if changed_count else "IDLE",
            "apply": apply,
            "candidate_count": len(candidates),
            "changed_count": changed_count,
            "symbols_attached": symbols_attached,
            "risk_classified": risk_classified,
            "topic_mapped": topic_mapped,
            "items": updated_items[:50],
        }

    async def _load_candidates(
        self,
        session: AsyncSession,
        *,
        limit: int,
        source_code: str | None,
        missing_only: bool,
    ) -> list[NewsItem]:
        stmt = select(NewsItem)
        if source_code:
            stmt = stmt.where(NewsItem.source_code == str(source_code).upper().strip())
        if missing_only:
            stmt = stmt.where(
                or_(
                    NewsItem.metadata_json.is_(None),
                    NewsItem.metadata_json.not_like('%"risk_classifier"%'),
                    NewsItem.metadata_json.not_like('%"topic_mapper"%'),
                )
            )
        stmt = stmt.order_by(desc(NewsItem.created_at), desc(NewsItem.published_at)).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _diff_item(item: NewsItem, proposed: dict[str, Any]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field in ("sentiment_label", "sentiment_score", "impact_score", "symbols_csv", "metadata_json"):
            proposed_value = proposed.get(field)
            if getattr(item, field) == proposed_value:
                continue
            changes[field] = proposed_value
        return changes

    @staticmethod
    def _load_metadata(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}


news_enrichment_backfill_service = NewsEnrichmentBackfillService()
