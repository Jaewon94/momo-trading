"""적재된 해외 뉴스 번역 백로그 처리."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.llm.selection_policy import resolve_news_selection
from core.config import settings
from repositories.news_item_repository import NewsItemRepository
from services.news_translation_service import news_translation_service


class NewsTranslationBackfillService:
    TRADING_HOURS_BATCH_SIZE = 2
    OFF_HOURS_BATCH_SIZE = 8

    async def process_pending(self, session: AsyncSession, *, market_hours: bool) -> dict[str, Any]:
        if not settings.NEWS_LLM_ENABLED:
            return {
                "status": "SKIPPED",
                "reason": "NEWS_LLM_ENABLED disabled",
                "candidate_count": 0,
                "translated": 0,
                "failed": 0,
            }
        if not settings.NEWS_TRANSLATE_FOREIGN_ENABLED:
            return {
                "status": "SKIPPED",
                "reason": "NEWS_TRANSLATE_FOREIGN_ENABLED disabled",
                "candidate_count": 0,
                "translated": 0,
                "failed": 0,
            }

        repo = NewsItemRepository(session)
        batch_size = self.TRADING_HOURS_BATCH_SIZE if market_hours else self.OFF_HOURS_BATCH_SIZE
        candidates = await repo.get_translation_backlog(limit=max(batch_size * 3, 12))
        if not candidates:
            return {
                "status": "IDLE",
                "reason": "translation backlog empty",
                "candidate_count": 0,
                "translated": 0,
                "failed": 0,
            }

        selection = resolve_news_selection()
        translated_count = 0
        failed_count = 0

        for item in candidates[:batch_size]:
            raw = self._serialize_item_for_translation(item)
            result = await news_translation_service.translate_item(raw, news_selection=selection)
            metadata = dict(result.get("metadata") or {})
            metadata["translation_attempts"] = int(metadata.get("translation_attempts") or 0) + 1
            if metadata.get("translation_status") == "SUCCESS":
                translated_count += 1
            else:
                failed_count += 1
            item.metadata_json = json.dumps(metadata, ensure_ascii=False)
            if result.get("sentiment_label") is not None:
                item.sentiment_label = result.get("sentiment_label")
            if result.get("sentiment_score") is not None:
                item.sentiment_score = float(result.get("sentiment_score") or 0.0)
            await repo.update(item)

        logger.debug(
            "뉴스 번역 백로그 처리: 후보 {}건 / 성공 {}건 / 실패 {}건 / 장중={}",
            len(candidates),
            translated_count,
            failed_count,
            market_hours,
        )
        return {
            "status": "SUCCESS" if translated_count and not failed_count else ("PARTIAL_ERROR" if failed_count else "IDLE"),
            "candidate_count": len(candidates),
            "translated": translated_count,
            "failed": failed_count,
            "batch_size": batch_size,
            "market_hours": market_hours,
            "provider": str(selection.provider or settings.NEWS_LLM_PROVIDER or "CLAUDE_CODE").upper(),
        }

    @staticmethod
    def _serialize_item_for_translation(item) -> dict[str, Any]:
        try:
            metadata = json.loads(item.metadata_json) if item.metadata_json else {}
        except (TypeError, ValueError):
            metadata = {}
        return {
            "source_code": getattr(item, "source_code", ""),
            "language": getattr(item, "language", ""),
            "title": getattr(item, "title", ""),
            "summary": getattr(item, "summary", ""),
            "metadata": metadata,
            "sentiment_label": getattr(item, "sentiment_label", None),
            "sentiment_score": float(getattr(item, "sentiment_score", 0.0) or 0.0),
        }


news_translation_backfill_service = NewsTranslationBackfillService()
