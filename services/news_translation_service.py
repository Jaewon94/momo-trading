"""해외 뉴스 한글 번역/요약 서비스."""
from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger

from analysis.llm.llm_factory import llm_factory
from analysis.llm.selection_policy import resolve_news_selection
from core.config import settings
from core.json_utils import parse_llm_json
from services.error_capture_service import error_capture_service
from trading.enums import LLMTier


class NewsTranslationService:
    async def translate_item(
        self,
        item: dict[str, Any],
        *,
        news_selection=None,
    ) -> dict[str, Any]:
        return await self._translate_item(item, news_selection=news_selection)

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
                if (
                    not settings.NEWS_LLM_ENABLED
                    or not settings.NEWS_TRANSLATE_FOREIGN_ENABLED
                    or language.startswith("ko")
                ):
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
        selected_news = news_selection or resolve_news_selection()
        if not selected_news.enabled or not settings.NEWS_TRANSLATE_FOREIGN_ENABLED:
            return item

        system_prompt = (
            "You are a strict JSON API for Korean financial-news translation. "
            "Return one JSON object only. Do not include markdown, commentary, or thinking tags."
        )
        prompt = f"""Translate the following financial news into Korean for a Korean stock trading dashboard.

Return exactly one minified JSON object with these keys:
{{
  "translated_title": "...",
  "translated_summary": "...",
  "sentiment_label": "POSITIVE|NEUTRAL|NEGATIVE",
  "sentiment_score": 0.72
}}

Rules:
- Output must start with {{ and end with }}.
- Do not wrap the JSON in markdown.
- Do not include <think> blocks or explanations.
- Keep company/product names accurate.
- Write concise Korean suitable for UI.
- translated_summary should be 1-2 Korean sentences.
- sentiment_label must be POSITIVE, NEUTRAL, or NEGATIVE.
- sentiment_score must be a number from 0.0 to 1.0, not a percent string.

Title: {title}
Summary: {summary}
"""

        copied = dict(item)
        metadata = dict(item.get("metadata") or {})
        try:
            result, provider = await llm_factory.generate_news(
                prompt,
                LLMTier.TIER1,
                system_prompt,
                news_selection=selected_news,
            )
            payload = self._parse_translation_payload(result)
            if not payload:
                raise ValueError("translation JSON parse failed")
            translated_title = str(payload.get("translated_title") or "").strip()
            translated_summary = str(payload.get("translated_summary") or "").strip()
            if not translated_title and not translated_summary:
                raise ValueError("translation payload missing translated fields")
            if translated_title:
                metadata["translated_title"] = translated_title
            if translated_summary:
                metadata["translated_summary"] = translated_summary
            metadata["translation_provider"] = provider
            metadata["translation_status"] = "SUCCESS"
            metadata.pop("translation_error", None)
            copied["metadata"] = metadata
            sentiment_label = self._normalize_sentiment_label(payload.get("sentiment_label"))
            sentiment_score = self._normalize_sentiment_score(payload.get("sentiment_score"))
            if sentiment_label:
                copied["sentiment_label"] = sentiment_label
            if sentiment_score is not None:
                copied["sentiment_score"] = sentiment_score
            return copied
        except Exception as exc:
            logger.debug("해외 뉴스 번역 실패: {}", str(exc))
            await error_capture_service.capture_exception(
                component="news_translation",
                operation="translate_item",
                exc=exc,
                provider=str(selected_news.provider or "CLAUDE_CODE").upper(),
                detail={
                    "source_code": str(item.get("source_code") or ""),
                    "language": str(item.get("language") or ""),
                    "title": title[:160],
                },
            )
            metadata["translation_status"] = "FAILED"
            error_text = str(exc).strip() or exc.__class__.__name__
            metadata["translation_error"] = error_text[:120]
            copied["metadata"] = metadata
            return copied

    def _translation_concurrency_limit(self, provider: str) -> int:
        normalized = str(provider or "CLAUDE_CODE").upper()
        if normalized in {"OLLAMA", "CODEX"}:
            return 1
        return max(int(settings.NEWS_TRANSLATION_CONCURRENCY or 1), 1)

    def _should_disable_claude_session_sharing(self, provider: str) -> bool:
        normalized = str(provider or "CLAUDE_CODE").upper()
        return normalized == "CLAUDE_CODE" and not bool(settings.NEWS_CLAUDE_SHARE_SESSION)

    @staticmethod
    def _parse_translation_payload(text: str) -> dict:
        cleaned = _strip_qwen_thinking(text)
        payload = parse_llm_json(cleaned)
        if _looks_like_translation_payload(payload):
            return payload
        for candidate in reversed(_extract_json_object_candidates(cleaned)):
            payload = parse_llm_json(candidate)
            if _looks_like_translation_payload(payload):
                return payload
        return {}

    @staticmethod
    def _normalize_sentiment_label(value: Any) -> str | None:
        normalized = str(value or "").strip().upper()
        if normalized in {"POSITIVE", "BULLISH", "GOOD", "긍정", "호재"}:
            return "POSITIVE"
        if normalized in {"NEGATIVE", "BEARISH", "BAD", "부정", "악재"}:
            return "NEGATIVE"
        if normalized in {"NEUTRAL", "MIXED", "중립"}:
            return "NEUTRAL"
        return None

    @staticmethod
    def _normalize_sentiment_score(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, str):
            raw = value.strip()
            is_percent = raw.endswith("%")
            raw = raw.rstrip("%").strip()
            try:
                score = float(raw)
            except ValueError:
                return None
            if is_percent or score > 1.0:
                score = score / 100.0
        else:
            try:
                score = float(value)
            except (TypeError, ValueError):
                return None
        return min(max(score, 0.0), 1.0)


def _strip_qwen_thinking(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _looks_like_translation_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and (
            "translated_title" in payload
            or "translated_summary" in payload
            or "sentiment_label" in payload
            or "sentiment_score" in payload
        )
    )


def _extract_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape_next = False

    for index, ch in enumerate(text or ""):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:index + 1])
                start = None

    return candidates


news_translation_service = NewsTranslationService()
