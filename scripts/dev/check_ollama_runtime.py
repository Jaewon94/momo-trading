#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from analysis.llm.ollama_provider import OllamaProvider
from core.config import settings
from services.runtime_settings_service import runtime_settings_service
from trading.enums import LLMTier


def _requires_ollama() -> bool:
    candidates = [
        settings.LLM_PROVIDER_TIER1,
        settings.LLM_PROVIDER_TIER2,
        settings.LLM_FALLBACK_PROVIDER_TIER1,
        settings.LLM_FALLBACK_PROVIDER_TIER2,
        settings.MANUAL_LLM_PROVIDER,
        settings.MANUAL_LLM_FALLBACK_PROVIDER,
        settings.NEWS_LLM_PROVIDER,
        settings.NEWS_LLM_FALLBACK_PROVIDER,
    ]
    return any(str(value or "").upper() == "OLLAMA" for value in candidates)


def _platform_name() -> str:
    return str(os.environ.get("MOMO_PLATFORM") or sys.platform).lower()


def _can_autostart_ollama() -> bool:
    platform_name = _platform_name()
    return platform_name.startswith("darwin") or platform_name == "macos"


def _open_binary() -> str:
    return str(os.environ.get("MOMO_OPEN_BIN") or "open")


async def _wait_until_available(provider: OllamaProvider, *, retries: int, delay_sec: float) -> bool:
    for _ in range(max(retries, 1)):
        if await provider.is_available():
            return True
        await asyncio.sleep(max(delay_sec, 0.1))
    return False


def _start_ollama_app() -> bool:
    try:
        result = subprocess.run(
            [_open_binary(), "-a", "Ollama"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


async def _main() -> int:
    await runtime_settings_service.apply_persisted_settings()

    if not _requires_ollama():
        return 0

    provider = OllamaProvider(LLMTier.TIER1)
    available = await provider.is_available()
    if available:
        print(f"🦙 Ollama 연결 확인: {settings.OLLAMA_BASE_URL}")
        return 0

    ensure_started = "--ensure-started" in sys.argv[1:]
    if ensure_started and _can_autostart_ollama():
        print("🦙 Ollama 미기동 감지 → 앱 실행 시도")
        started = _start_ollama_app()
        if started:
            retries = int(os.environ.get("MOMO_OLLAMA_START_RETRIES") or "20")
            delay_sec = float(os.environ.get("MOMO_OLLAMA_START_WAIT_SEC") or "1")
            if await _wait_until_available(provider, retries=retries, delay_sec=delay_sec):
                print(f"🦙 Ollama 연결 확인: {settings.OLLAMA_BASE_URL}")
                return 0
        else:
            print("⚠️  Ollama 앱 실행 요청에 실패했습니다.")

    print("⚠️  Ollama가 설정에 포함되어 있지만 현재 연결되지 않습니다.")
    print(f"   Base URL: {settings.OLLAMA_BASE_URL}")
    if ensure_started and not _can_autostart_ollama():
        print("   현재 플랫폼에서는 자동 실행을 지원하지 않습니다. Ollama를 직접 실행하세요.")
    else:
        print("   Ollama 앱/서버를 실행하거나, LLM 설정에서 다른 Provider를 선택하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
