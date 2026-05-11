"""Anthropic Claude Messages API Provider."""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import LLMProvider, LLMTier


_DEFAULT_TIER1_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_TIER2_MODEL = "claude-sonnet-4-6"
_MODEL_ALIASES = {
    "haiku": _DEFAULT_TIER1_MODEL,
    "sonnet": _DEFAULT_TIER2_MODEL,
}


class ClaudeApiProvider:
    def __init__(
        self,
        tier: LLMTier = LLMTier.TIER1,
        model_override: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._tier = tier
        self._transport = transport
        if model_override is not None:
            configured_model = model_override
        elif tier == LLMTier.TIER1:
            configured_model = settings.CLAUDE_CODE_MODEL_TIER1 or settings.CLAUDE_CODE_MODEL
        else:
            configured_model = settings.CLAUDE_CODE_MODEL_TIER2 or settings.CLAUDE_CODE_MODEL
        self._configured_model = normalize_llm_model_value(configured_model)
        self._model = self._resolve_model(self._configured_model)

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.CLAUDE_API

    @property
    def tier(self) -> LLMTier:
        return self._tier

    @property
    def model_id(self) -> str:
        return f"claude-api:{self._model}"

    def _resolve_model(self, model: str) -> str:
        if model == DEFAULT_LLM_MODEL:
            return _DEFAULT_TIER1_MODEL if self._tier == LLMTier.TIER1 else _DEFAULT_TIER2_MODEL
        return _MODEL_ALIASES.get(str(model).strip().lower(), model)

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다")

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            transport=self._transport,
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        ) as client:
            response = await client.post("/v1/messages", json=payload)
            response.raise_for_status()
            body = response.json()

        result_parts: list[str] = []
        for item in body.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                result_parts.append(str(item.get("text") or ""))
        result = "\n".join(part.strip() for part in result_parts if part.strip()).strip()
        if not result:
            raise RuntimeError("Claude API 빈 응답")
        return result

    async def is_available(self) -> bool:
        available = bool(settings.ANTHROPIC_API_KEY)
        if not available:
            logger.debug("Claude API 사용 불가: ANTHROPIC_API_KEY 없음")
        return available

    def status_snapshot(self) -> dict:
        return {
            "available": bool(settings.ANTHROPIC_API_KEY),
            "cli_path": "",
            "cooldown_active": False,
            "disabled_for_sec": 0,
            "last_failure_reason": "" if settings.ANTHROPIC_API_KEY else "ANTHROPIC_API_KEY 없음",
            "last_failure_kind": "" if settings.ANTHROPIC_API_KEY else "missing_api_key",
            "model": self.model_id,
        }
