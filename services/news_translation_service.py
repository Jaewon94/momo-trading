"""해외 뉴스 한글 번역/요약 서비스."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from analysis.llm.llm_factory import llm_factory
from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import LLMTier


class NewsTranslationService:
    @staticmethod
    def _news_ollama_model_override() -> str | None:
        if (settings.NEWS_LLM_PROVIDER or "AUTOMATIC").upper() != "OLLAMA":
            return None
        normalized = normalize_llm_model_value(settings.NEWS_OLLAMA_MODEL)
        if normalized == DEFAULT_LLM_MODEL:
            return None
        return normalized

    async def translate_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        for item in items:
            language = str(item.get("language") or "").lower()
            if not settings.NEWS_LLM_ENABLED or language.startswith("ko"):
                translated.append(item)
                continue
            translated.append(await self._translate_item(item))
        return translated

    async def _translate_item(self, item: dict[str, Any]) -> dict[str, Any]:
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
        try:
            result, provider = await llm_factory.generate_manual(
                prompt,
                default_tier=LLMTier.TIER1,
                manual_provider_override=(settings.NEWS_LLM_PROVIDER or "AUTOMATIC"),
                manual_model_override=self._news_ollama_model_override(),
            )
            start = result.find("{")
            end = result.rfind("}") + 1
            payload = json.loads(result[start:end]) if start >= 0 and end > start else {}
            translated_title = str(payload.get("translated_title") or "").strip()
            translated_summary = str(payload.get("translated_summary") or "").strip()
            if translated_title:
                metadata["translated_title"] = translated_title
            if translated_summary:
                metadata["translated_summary"] = translated_summary
            metadata["translation_provider"] = provider
            metadata["translation_status"] = "SUCCESS"
            copied["metadata"] = metadata
            if payload.get("sentiment_label"):
                copied["sentiment_label"] = str(payload["sentiment_label"]).upper()
            if payload.get("sentiment_score") is not None:
                copied["sentiment_score"] = float(payload["sentiment_score"])
            return copied
        except Exception as exc:
            logger.debug("해외 뉴스 번역 실패: {}", str(exc))
            metadata["translation_status"] = "FAILED"
            metadata["translation_error"] = str(exc)[:120]
            copied["metadata"] = metadata
            return copied


news_translation_service = NewsTranslationService()
