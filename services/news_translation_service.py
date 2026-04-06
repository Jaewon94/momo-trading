"""해외 뉴스 한글 번역/요약 서비스."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from analysis.llm.llm_factory import llm_factory
from analysis.llm.selection_policy import resolve_news_selection
from core.config import settings
from trading.enums import LLMTier


class NewsTranslationService:
    async def translate_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any] | None] = [None] * len(items)
        news_selection = resolve_news_selection()
        limit = self._translation_concurrency_limit(news_selection.provider)
        semaphore = asyncio.Semaphore(limit)
        tasks: list[asyncio.Task[None]] = []
        paused_session_id: str | None = None

        if self._should_disable_claude_session_sharing(news_selection.provider):
            paused_session_id = llm_factory.pause_session()

        try:
            for index, item in enumerate(items):
                language = str(item.get("language") or "").lower()
                if not settings.NEWS_LLM_ENABLED or language.startswith("ko"):
                    translated[index] = item
                    continue
                tasks.append(asyncio.create_task(
                    self._translate_with_limit(
                        item=item,
                        translated=translated,
                        index=index,
                        semaphore=semaphore,
                        news_selection=news_selection,
                    )
                ))
            if tasks:
                await asyncio.gather(*tasks)
            return [item for item in translated if item is not None]
        finally:
            if paused_session_id:
                llm_factory.resume_session(paused_session_id)

    async def _translate_with_limit(
        self,
        *,
        item: dict[str, Any],
        translated: list[dict[str, Any] | None],
        index: int,
        semaphore: asyncio.Semaphore,
        news_selection,
    ) -> None:
        async with semaphore:
            translated[index] = await self._translate_item(item, news_selection=news_selection)

    async def _translate_item(
        self,
        item: dict[str, Any],
        *,
        news_selection=None,
    ) -> dict[str, Any]:
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title:
            return item

        prompt = f"""Translate the following financial news into Korean for a Korean stock trading dashboard.

Return JSON only:
{{
  "translated_title": "...",
  "translated_summary": "...",
  "sentiment_label": "POSITIVE",
  "sentiment_score": 0.72
}}

Rules:
- Keep company/product names accurate.
- Write concise Korean suitable for UI.
- translated_summary should be 1-2 Korean sentences.
- sentiment_label must be POSITIVE, NEUTRAL, or NEGATIVE.
- sentiment_score must be a number from 0.0 to 1.0.

Title: {title}
Summary: {summary}
"""

        copied = dict(item)
        metadata = dict(item.get("metadata") or {})
        selected_news = news_selection or resolve_news_selection()
        try:
            result, provider = await llm_factory.generate(
                prompt,
                LLMTier.TIER1,
                "",
                provider_chain=list(selected_news.provider_chain),
                provider_model_overrides=selected_news.provider_model_overrides,
            )
            start = result.find("{")
            end = result.rfind("}") + 1
            payload = json.loads(result[start:end]) if start >= 0 and end > start else {}
            if not payload:
                raise ValueError("translation JSON parse failed")
            translated_title = str(payload.get("translated_title") or "").strip()
            translated_summary = str(payload.get("translated_summary") or "").strip()
            if translated_title:
                metadata["translated_title"] = translated_title
            if translated_summary:
                metadata["translated_summary"] = translated_summary
            metadata["translation_provider"] = provider
            metadata["translation_status"] = "SUCCESS"
            metadata.pop("translation_error", None)
            copied["metadata"] = metadata
            if payload.get("sentiment_label"):
                copied["sentiment_label"] = str(payload["sentiment_label"]).upper()
            if payload.get("sentiment_score") is not None:
                copied["sentiment_score"] = float(payload["sentiment_score"])
            return copied
        except Exception as exc:
            logger.debug("해외 뉴스 번역 실패: {}", str(exc))
            metadata["translation_status"] = "FAILED"
            error_text = str(exc).strip() or exc.__class__.__name__
            metadata["translation_error"] = error_text[:120]
            copied["metadata"] = metadata
            return copied

    def _translation_concurrency_limit(self, provider: str) -> int:
        normalized = str(provider or "CLAUDE_CODE").upper()
        if normalized == "OLLAMA":
            return 1
        return max(int(settings.NEWS_TRANSLATION_CONCURRENCY or 1), 1)

    def _should_disable_claude_session_sharing(self, provider: str) -> bool:
        normalized = str(provider or "CLAUDE_CODE").upper()
        return normalized == "CLAUDE_CODE" and not bool(settings.NEWS_CLAUDE_SHARE_SESSION)


news_translation_service = NewsTranslationService()
