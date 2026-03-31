from __future__ import annotations

import asyncio
import copy
import re
import subprocess
import time
from datetime import datetime

import httpx
from loguru import logger

from core.config import DEFAULT_LLM_MODEL, settings

_ANTHROPIC_CONFIG_URL = "https://docs.anthropic.com/en/docs/claude-code/model-config"
_ANTHROPIC_MODELS_URL = "https://docs.anthropic.com/en/docs/about-claude/models/overview"
_OPENAI_CODEX_CLI_URL = "https://developers.openai.com/codex/cli/reference"
_OPENAI_CODEX_CONFIG_URL = "https://developers.openai.com/codex/config-reference"
_OPENAI_CODEX_MODEL_URL = "https://developers.openai.com/api/docs/models/gpt-5-codex"
_OPENAI_CODEX_HELP_URL = "https://help.openai.com/en/articles/11369540-codex-in-chatgpt-faq"


class ModelCatalogService:
    TTL_SEC = 3600

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cached_payload: dict | None = None
        self._cached_at = 0.0

    async def get_catalog(self, *, force_refresh: bool = False) -> dict:
        if not force_refresh and self._cached_payload and self._is_cache_fresh():
            return self._decorate(copy.deepcopy(self._cached_payload), stale=False)

        async with self._lock:
            if not force_refresh and self._cached_payload and self._is_cache_fresh():
                return self._decorate(copy.deepcopy(self._cached_payload), stale=False)

            try:
                payload = await self._build_catalog()
                self._cached_payload = payload
                self._cached_at = time.monotonic()
                return self._decorate(copy.deepcopy(payload), stale=False)
            except Exception as exc:
                logger.warning("LLM 카탈로그 동기화 실패: {}", exc)
                if self._cached_payload:
                    fallback = copy.deepcopy(self._cached_payload)
                    fallback["fetch_error"] = str(exc)
                    return self._decorate(fallback, stale=True)

                seed = self._seed_catalog()
                seed["fetch_error"] = str(exc)
                return self._decorate(seed, stale=True)

    def _is_cache_fresh(self) -> bool:
        return (time.monotonic() - self._cached_at) < self.TTL_SEC

    def _decorate(self, payload: dict, *, stale: bool) -> dict:
        payload["stale"] = stale
        payload["cache_age_sec"] = max(0, int(time.monotonic() - self._cached_at)) if self._cached_at else None
        return payload

    async def _build_catalog(self) -> dict:
        fetched_at = datetime.now().astimezone().isoformat()
        claude_catalog, codex_catalog = await asyncio.gather(
            self._build_claude_catalog(),
            self._build_codex_catalog(),
        )
        return {
            "fetched_at": fetched_at,
            "providers": [claude_catalog, codex_catalog],
        }

    async def _fetch_text(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            response = await client.get(url, headers={"User-Agent": "momo-trading/0.1"})
            response.raise_for_status()
            return response.text

    async def _build_claude_catalog(self) -> dict:
        config_html, models_html = await asyncio.gather(
            self._fetch_text(_ANTHROPIC_CONFIG_URL),
            self._fetch_text(_ANTHROPIC_MODELS_URL),
        )
        entries = self._seed_claude_entries()
        seen = {item["value"] for item in entries}
        pattern = re.compile(r"claude-(?:opus|sonnet|haiku)-[0-9](?:-[0-9]+)?(?:-\d{8})?")
        for value in sorted(set(pattern.findall(config_html + "\n" + models_html))):
            if value in seen:
                continue
            seen.add(value)
            entries.append({
                "value": value,
                "label": value,
                "kind": "snapshot" if re.search(r"\d{8}$", value) else "alias",
                "stability": "stable" if re.search(r"\d{8}$", value) else "moving",
                "source_scope": "official-doc",
                "source_url": _ANTHROPIC_MODELS_URL,
            })
        return {
            "id": "CLAUDE_CODE",
            "name": "Claude Code",
            "cli_path": settings._find_claude_path() or "",
            "cli_version": self._get_cli_version(settings._find_claude_path(), ["--version"]),
            "custom_value_supported": True,
            "source_urls": [_ANTHROPIC_CONFIG_URL, _ANTHROPIC_MODELS_URL],
            "entries": entries,
        }

    async def _build_codex_catalog(self) -> dict:
        cli_html, config_html, model_html, help_html = await asyncio.gather(
            self._fetch_text(_OPENAI_CODEX_CLI_URL),
            self._fetch_text(_OPENAI_CODEX_CONFIG_URL),
            self._fetch_text(_OPENAI_CODEX_MODEL_URL),
            self._fetch_text(_OPENAI_CODEX_HELP_URL),
        )
        entries = self._seed_codex_entries()
        seen = {item["value"] for item in entries}
        pattern = re.compile(r"(?:gpt-5(?:\.\d+)?-codex(?:-(?:max|mini))?(?:-\d{4}-\d{2}-\d{2})?|codex-mini-latest)")
        combined = "\n".join([cli_html, config_html, model_html, help_html])
        for value in sorted(set(pattern.findall(combined))):
            if value in seen:
                continue
            seen.add(value)
            entries.append({
                "value": value,
                "label": value,
                "kind": "snapshot" if re.search(r"\d{4}-\d{2}-\d{2}$", value) else "alias",
                "stability": "stable" if re.search(r"\d{4}-\d{2}-\d{2}$", value) else "moving",
                "source_scope": "official-doc",
                "source_url": _OPENAI_CODEX_MODEL_URL if "gpt-5-codex" in value or "codex-mini-latest" in value else _OPENAI_CODEX_HELP_URL,
            })
        warnings: list[str] = []
        if "GPT-5.1-Codex model family" in help_html and "GPT-5-Codex" in model_html:
            warnings.append("OpenAI 공식 문서가 ChatGPT Codex와 개발자 모델 문서를 서로 다른 범위로 설명합니다.")
        return {
            "id": "CODEX",
            "name": "Codex CLI",
            "cli_path": settings._find_codex_path() or "",
            "cli_version": self._get_cli_version(settings._find_codex_path(), ["--version"]),
            "custom_value_supported": True,
            "source_urls": [
                _OPENAI_CODEX_CLI_URL,
                _OPENAI_CODEX_CONFIG_URL,
                _OPENAI_CODEX_MODEL_URL,
                _OPENAI_CODEX_HELP_URL,
            ],
            "warnings": warnings,
            "entries": entries,
        }

    def _seed_catalog(self) -> dict:
        return {
            "fetched_at": None,
            "providers": [
                {
                    "id": "CLAUDE_CODE",
                    "name": "Claude Code",
                    "cli_path": settings._find_claude_path() or "",
                    "cli_version": self._get_cli_version(settings._find_claude_path(), ["--version"]),
                    "custom_value_supported": True,
                    "source_urls": [_ANTHROPIC_CONFIG_URL, _ANTHROPIC_MODELS_URL],
                    "entries": self._seed_claude_entries(),
                },
                {
                    "id": "CODEX",
                    "name": "Codex CLI",
                    "cli_path": settings._find_codex_path() or "",
                    "cli_version": self._get_cli_version(settings._find_codex_path(), ["--version"]),
                    "custom_value_supported": True,
                    "source_urls": [
                        _OPENAI_CODEX_CLI_URL,
                        _OPENAI_CODEX_CONFIG_URL,
                        _OPENAI_CODEX_MODEL_URL,
                        _OPENAI_CODEX_HELP_URL,
                    ],
                    "entries": self._seed_codex_entries(),
                },
            ],
        }

    @staticmethod
    def _seed_claude_entries() -> list[dict]:
        return [
            {
                "value": DEFAULT_LLM_MODEL,
                "label": "기본값 사용",
                "kind": "default",
                "stability": "moving",
                "source_scope": "runtime-default",
                "source_url": "",
            },
            {
                "value": "sonnet",
                "label": "sonnet",
                "kind": "alias",
                "stability": "moving",
                "source_scope": "official-doc",
                "source_url": _ANTHROPIC_CONFIG_URL,
            },
            {
                "value": "opus",
                "label": "opus",
                "kind": "alias",
                "stability": "moving",
                "source_scope": "official-doc",
                "source_url": _ANTHROPIC_CONFIG_URL,
            },
            {
                "value": "haiku",
                "label": "haiku",
                "kind": "alias",
                "stability": "moving",
                "source_scope": "official-doc",
                "source_url": _ANTHROPIC_CONFIG_URL,
            },
        ]

    @staticmethod
    def _seed_codex_entries() -> list[dict]:
        return [
            {
                "value": DEFAULT_LLM_MODEL,
                "label": "기본값 사용",
                "kind": "default",
                "stability": "moving",
                "source_scope": "runtime-default",
                "source_url": "",
            },
            {
                "value": "gpt-5-codex",
                "label": "gpt-5-codex",
                "kind": "alias",
                "stability": "moving",
                "source_scope": "official-doc",
                "source_url": _OPENAI_CODEX_MODEL_URL,
            },
            {
                "value": "codex-mini-latest",
                "label": "codex-mini-latest",
                "kind": "alias",
                "stability": "moving",
                "source_scope": "official-doc",
                "source_url": _OPENAI_CODEX_MODEL_URL,
            },
        ]

    @staticmethod
    def _get_cli_version(path: str | None, args: list[str]) -> str:
        if not path:
            return ""
        try:
            proc = subprocess.run(
                [path, *args],
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            return ""
        output = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0:
            return ""
        return output.splitlines()[0].strip()


model_catalog_service = ModelCatalogService()
