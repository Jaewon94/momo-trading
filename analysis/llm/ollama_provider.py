"""Ollama HTTP Provider — 로컬 Ollama 서버를 통한 생성."""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import LLMProvider, LLMTier


class OllamaProvider:
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
            configured_model = settings.OLLAMA_MODEL_TIER1 or settings.OLLAMA_MODEL
        else:
            configured_model = settings.OLLAMA_MODEL_TIER2 or settings.OLLAMA_MODEL
        normalized_model = normalize_llm_model_value(configured_model)
        self._configured_model = normalized_model
        self._model = settings.OLLAMA_MODEL if normalized_model == DEFAULT_LLM_MODEL else normalized_model

    @property
    def provider(self) -> LLMProvider:
        return LLMProvider.OLLAMA

    @property
    def tier(self) -> LLMTier:
        return self._tier

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            transport=self._transport,
            timeout=httpx.Timeout(90.0, connect=5.0),
        ) as client:
            response = await client.post("/api/generate", json=payload)
            response.raise_for_status()
            body = response.json()

        result = str(body.get("response", "") or "").strip()
        if not result:
            raise RuntimeError("Ollama 빈 응답")
        return result

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(
                base_url=settings.OLLAMA_BASE_URL,
                transport=self._transport,
                timeout=httpx.Timeout(5.0, connect=2.0),
            ) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.debug("Ollama 사용 불가: {}", str(exc))
            return False

    def status_snapshot(self) -> dict:
        return {
            "available": bool(settings.OLLAMA_BASE_URL),
            "base_url": settings.OLLAMA_BASE_URL,
            "model": self.model_id,
            "cooldown_active": False,
            "disabled_for_sec": 0,
            "last_failure_reason": "",
            "last_failure_kind": "",
            "cli_path": "",
        }
