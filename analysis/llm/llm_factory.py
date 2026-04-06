"""LLM Factory — Claude Code CLI / Codex CLI 라우팅"""
import asyncio
import time

from loguru import logger

from analysis.llm.claude_code_provider import ClaudeCodeProvider
from analysis.llm.codex_provider import CodexProvider
from analysis.llm.ollama_provider import OllamaProvider
from analysis.llm.selection_policy import (
    model_for_status,
    provider_from_name,
    resolve_manual_selection,
    resolve_news_selection,
    resolve_tier_selection,
)
from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import ActivityPhase, ActivityType, LLMProvider, LLMTier


class LLMFactory:
    """CLI 기반 LLM 라우팅

    - Tier 1 (빠름): 스캔, 선별, 기술분석 해석
    - Tier 2 (프리미엄): 최종 검토, 매매 결정
    """

    def __init__(self):
        self._providers = {
            LLMTier.TIER1: {
                LLMProvider.CLAUDE_CODE: ClaudeCodeProvider(LLMTier.TIER1),
                LLMProvider.CODEX: CodexProvider(LLMTier.TIER1),
                LLMProvider.OLLAMA: OllamaProvider(LLMTier.TIER1),
            },
            LLMTier.TIER2: {
                LLMProvider.CLAUDE_CODE: ClaudeCodeProvider(LLMTier.TIER2),
                LLMProvider.CODEX: CodexProvider(LLMTier.TIER2),
                LLMProvider.OLLAMA: OllamaProvider(LLMTier.TIER2),
            },
        }

    def _provider_chain(self, tier: LLMTier) -> list[LLMProvider]:
        selection = resolve_tier_selection(tier)
        chain = [selection.provider]
        if selection.fallback_provider:
            fallback = provider_from_name(selection.fallback_provider)
            if fallback not in chain:
                chain.append(fallback)
        return chain

    def _manual_provider_chain(
        self,
        default_tier: LLMTier,
        manual_provider_override: str | None = None,
    ) -> list[LLMProvider]:
        return list(resolve_manual_selection(default_tier, provider_override=manual_provider_override).provider_chain)

    @staticmethod
    def _fallback_model_for_tier(tier: LLMTier) -> str:
        value = (
            settings.LLM_FALLBACK_MODEL_TIER1
            if tier == LLMTier.TIER1
            else settings.LLM_FALLBACK_MODEL_TIER2
        )
        return normalize_llm_model_value(value)

    def _build_provider(
        self,
        tier: LLMTier,
        provider_key: LLMProvider,
        model_override: str | None = None,
    ):
        normalized_override = normalize_llm_model_value(model_override) if model_override is not None else None
        if normalized_override in (None, DEFAULT_LLM_MODEL):
            existing = self._providers.get(tier, {}).get(provider_key)
            if existing is not None:
                return existing
        if provider_key == LLMProvider.CLAUDE_CODE:
            return ClaudeCodeProvider(tier, model_override=normalized_override)
        if provider_key == LLMProvider.OLLAMA:
            return OllamaProvider(tier, model_override=normalized_override)
        return CodexProvider(tier, model_override=normalized_override)

    def _uses_claude_sessions(self) -> bool:
        for tier in (LLMTier.TIER1, LLMTier.TIER2):
            if LLMProvider.CLAUDE_CODE in self._provider_chain(tier):
                return True
        return False

    def _provider_runtime_status(self, provider_key: LLMProvider) -> dict:
        provider = self._providers.get(LLMTier.TIER1, {}).get(provider_key)
        if provider is None:
            provider = self._build_provider(LLMTier.TIER1, provider_key)
        if hasattr(provider, "status_snapshot"):
            return provider.status_snapshot()
        return {
            "available": True,
            "cli_path": "",
            "cooldown_active": False,
            "disabled_for_sec": 0,
            "last_failure_reason": "",
            "last_failure_kind": "",
        }

    def start_session(self) -> str | None:
        if self._uses_claude_sessions():
            return ClaudeCodeProvider.start_session()
        return None

    def pause_session(self) -> str | None:
        if self._uses_claude_sessions():
            return ClaudeCodeProvider.pause_session()
        return None

    def resume_session(self, session_id: str | None) -> None:
        if session_id and self._uses_claude_sessions():
            ClaudeCodeProvider.resume_session(session_id)

    def end_session(self) -> str | None:
        if self._uses_claude_sessions():
            return ClaudeCodeProvider.end_session()
        return None

    async def generate(
        self, prompt: str, tier: LLMTier = LLMTier.TIER1, system_prompt: str = "",
        *, symbol: str | None = None, cycle_id: str | None = None,
        provider_chain: list[LLMProvider] | None = None,
        provider_model_overrides: dict[LLMProvider, str] | None = None,
    ) -> tuple[str, str]:
        """텍스트 생성 (최대 2회 시도)

        Returns:
            (생성 텍스트, 사용된 provider 이름)
        """
        provider_chain = provider_chain or self._provider_chain(tier)
        last_error = None

        for index, provider_key in enumerate(provider_chain):
            fallback_model = self._fallback_model_for_tier(tier) if index > 0 else None
            explicit_model_override = None
            if provider_model_overrides:
                explicit_model_override = provider_model_overrides.get(provider_key)
            provider = self._build_provider(
                tier,
                provider_key,
                explicit_model_override if explicit_model_override is not None else fallback_model,
            )
            if not await provider.is_available():
                runtime = provider.status_snapshot() if hasattr(provider, "status_snapshot") else {}
                if runtime.get("cooldown_active"):
                    last_error = RuntimeError(
                        f"{provider.provider.value} 최근 호출 실패로 비활성화 "
                        f"({runtime.get('disabled_for_sec', 0)}s 남음): "
                        f"{runtime.get('last_failure_reason', 'unknown')}"
                    )
                    logger.warning(
                        "{} 사용 불가 (cooldown {}s, reason: {}), 다음 provider 확인",
                        provider.provider.value,
                        runtime.get("disabled_for_sec", 0),
                        runtime.get("last_failure_reason", "unknown"),
                    )
                else:
                    last_error = RuntimeError(f"{provider.provider.value} CLI를 찾을 수 없습니다 (PATH 확인)")
                    logger.warning("{} 사용 불가, 다음 provider 확인", provider.provider.value)
                continue

            for attempt in range(2):
                try:
                    start = time.time()
                    result = await provider.generate(prompt, system_prompt)
                    elapsed_ms = int((time.time() - start) * 1000)
                    provider_name = provider.provider.value
                    model_id = provider.model_id

                    logger.debug(
                        "LLM 생성 완료: {} / {} ({}ms)",
                        provider_name, model_id, elapsed_ms,
                    )

                    await self._log_llm_conversation(
                        tier=tier,
                        provider=provider_name,
                        model=model_id,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        response=result,
                        elapsed_ms=elapsed_ms,
                        symbol=symbol,
                        cycle_id=cycle_id,
                    )

                    return result, provider_name
                except Exception as e:
                    last_error = e
                    should_retry = attempt == 0 and await provider.is_available()
                    if should_retry:
                        logger.warning("{} 호출 실패, 재시도: {}", provider.provider.value, str(e)[:100])
                        await asyncio.sleep(2)
                        continue
                    break
            logger.warning("{} 호출 실패, fallback provider 확인", provider.provider.value)

        raise last_error or RuntimeError("사용 가능한 LLM provider가 없습니다")

    async def _log_llm_conversation(
        self, *, tier: LLMTier, provider: str, model: str,
        system_prompt: str, prompt: str, response: str, elapsed_ms: int,
        symbol: str | None = None, cycle_id: str | None = None,
    ) -> None:
        """LLM 프롬프트/응답을 activity log에 기록"""
        try:
            from services.activity_logger import activity_logger
            await activity_logger.log(
                ActivityType.LLM_CALL, ActivityPhase.COMPLETE,
                f"[{tier.value}] {provider} ({model}) — {elapsed_ms/1000:.1f}초",
                detail={
                    "llm_system_prompt": system_prompt[:2000] if system_prompt else "",
                    "llm_prompt": prompt[:5000],
                    "llm_response": response[:5000],
                    "llm_model": model,
                },
                llm_provider=provider,
                llm_tier=tier.value,
                execution_time_ms=elapsed_ms,
                symbol=symbol,
                cycle_id=cycle_id,
            )
        except Exception as e:
            logger.debug("LLM 대화 로깅 실패 (무시): {}", str(e))

    async def generate_tier1(
        self, prompt: str, system_prompt: str = "",
        *, symbol: str | None = None, cycle_id: str | None = None,
    ) -> tuple[str, str]:
        """Tier 1 (빠른 분석용)"""
        return await self.generate(prompt, LLMTier.TIER1, system_prompt, symbol=symbol, cycle_id=cycle_id)

    async def generate_tier2(
        self, prompt: str, system_prompt: str = "",
        *, symbol: str | None = None, cycle_id: str | None = None,
    ) -> tuple[str, str]:
        """Tier 2 (프리미엄 분석용)"""
        return await self.generate(prompt, LLMTier.TIER2, system_prompt, symbol=symbol, cycle_id=cycle_id)

    async def generate_manual(
        self,
        prompt: str,
        system_prompt: str = "",
        *,
        default_tier: LLMTier = LLMTier.TIER1,
        symbol: str | None = None,
        cycle_id: str | None = None,
        manual_provider_override: str | None = None,
        manual_model_override: str | None = None,
    ) -> tuple[str, str]:
        """수동 작업용 LLM 생성.

        수동 작업 전용 primary/fallback 설정을 사용하고,
        provider/model override가 주어지면 primary만 덮어쓴다.
        """
        selection = resolve_manual_selection(
            default_tier,
            provider_override=manual_provider_override,
            model_override=manual_model_override,
        )
        return await self.generate(
            prompt,
            default_tier,
            system_prompt,
            symbol=symbol,
            cycle_id=cycle_id,
            provider_chain=list(selection.provider_chain),
            provider_model_overrides=selection.provider_model_overrides,
        )

    def get_llm_status(self) -> dict:
        """현재 LLM 설정 상태 반환 (Admin API용)"""
        tier1_selection = resolve_tier_selection(LLMTier.TIER1)
        tier2_selection = resolve_tier_selection(LLMTier.TIER2)
        manual_selection = resolve_manual_selection(LLMTier.TIER1)
        news_selection = resolve_news_selection()
        tier1_model = model_for_status("CLAUDE_CODE", LLMTier.TIER1)
        tier2_model = model_for_status("CLAUDE_CODE", LLMTier.TIER2)
        codex_tier1_model = model_for_status("CODEX", LLMTier.TIER1)
        codex_tier2_model = model_for_status("CODEX", LLMTier.TIER2)
        ollama_tier1_model = model_for_status("OLLAMA", LLMTier.TIER1)
        ollama_tier2_model = model_for_status("OLLAMA", LLMTier.TIER2)
        return {
            "tier1": {
                "provider": tier1_selection.provider.value,
                "fallback_provider": tier1_selection.fallback_provider,
                "fallback_model": tier1_selection.fallback_model if tier1_selection.fallback_provider else "",
                "fallback_model_mode": (
                    "default" if tier1_selection.fallback_provider and tier1_selection.fallback_model == DEFAULT_LLM_MODEL
                    else "explicit" if tier1_selection.fallback_provider
                    else ""
                ),
                "model": tier1_selection.model,
                "model_mode": "default" if tier1_selection.model == DEFAULT_LLM_MODEL else "explicit",
            },
            "tier2": {
                "provider": tier2_selection.provider.value,
                "fallback_provider": tier2_selection.fallback_provider,
                "fallback_model": tier2_selection.fallback_model if tier2_selection.fallback_provider else "",
                "fallback_model_mode": (
                    "default" if tier2_selection.fallback_provider and tier2_selection.fallback_model == DEFAULT_LLM_MODEL
                    else "explicit" if tier2_selection.fallback_provider
                    else ""
                ),
                "model": tier2_selection.model,
                "model_mode": "default" if tier2_selection.model == DEFAULT_LLM_MODEL else "explicit",
            },
            "available_providers": [
                {
                    "id": "CLAUDE_CODE",
                    "name": "Claude Code (로컬)",
                    "models": {"tier1": tier1_model, "tier2": tier2_model},
                    "has_key": True,
                    "runtime": self._provider_runtime_status(LLMProvider.CLAUDE_CODE),
                },
                {
                    "id": "CODEX",
                    "name": "Codex CLI (로컬)",
                    "models": {"tier1": codex_tier1_model, "tier2": codex_tier2_model},
                    "has_key": True,
                    "runtime": self._provider_runtime_status(LLMProvider.CODEX),
                },
                {
                    "id": "OLLAMA",
                    "name": "Ollama (로컬)",
                    "models": {"tier1": ollama_tier1_model, "tier2": ollama_tier2_model},
                    "has_key": False,
                    "runtime": self._provider_runtime_status(LLMProvider.OLLAMA),
                },
            ],
            "manual_selection": {
                "provider": manual_selection.provider,
                "model": manual_selection.model,
                "fallback_provider": manual_selection.fallback_provider,
                "fallback_model": manual_selection.fallback_model if manual_selection.fallback_provider else "",
                "options": ["CLAUDE_CODE", "CODEX", "OLLAMA"],
            },
            "news_selection": {
                "enabled": news_selection.enabled,
                "provider": news_selection.provider,
                "model": news_selection.model,
                "fallback_provider": news_selection.fallback_provider,
                "fallback_model": news_selection.fallback_model if news_selection.fallback_provider else "",
                "options": ["CLAUDE_CODE", "CODEX", "OLLAMA"],
            },
        }


llm_factory = LLMFactory()
