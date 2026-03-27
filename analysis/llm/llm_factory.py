"""LLM Factory — Claude Code CLI / Codex CLI 라우팅"""
import asyncio
import time

from loguru import logger

from analysis.llm.codex_provider import CodexProvider
from analysis.llm.claude_code_provider import ClaudeCodeProvider
from core.config import settings
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
            },
            LLMTier.TIER2: {
                LLMProvider.CLAUDE_CODE: ClaudeCodeProvider(LLMTier.TIER2),
                LLMProvider.CODEX: CodexProvider(LLMTier.TIER2),
            },
        }

    @staticmethod
    def _provider_from_name(value: str | None, default: LLMProvider = LLMProvider.CLAUDE_CODE) -> LLMProvider:
        if not value:
            return default
        return LLMProvider(value.upper())

    def _provider_chain(self, tier: LLMTier) -> list[LLMProvider]:
        primary_default = settings.LLM_PROVIDER or LLMProvider.CLAUDE_CODE.value
        primary_name = (
            settings.LLM_PROVIDER_TIER1 if tier == LLMTier.TIER1 else settings.LLM_PROVIDER_TIER2
        ) or primary_default
        fallback_name = (
            settings.LLM_FALLBACK_PROVIDER_TIER1 if tier == LLMTier.TIER1 else settings.LLM_FALLBACK_PROVIDER_TIER2
        )

        chain = [self._provider_from_name(primary_name)]
        if fallback_name:
            fallback = self._provider_from_name(fallback_name)
            if fallback not in chain:
                chain.append(fallback)
        return chain

    def _uses_claude_sessions(self) -> bool:
        for tier in (LLMTier.TIER1, LLMTier.TIER2):
            if LLMProvider.CLAUDE_CODE in self._provider_chain(tier):
                return True
        return False

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
    ) -> tuple[str, str]:
        """텍스트 생성 (최대 2회 시도)

        Returns:
            (생성 텍스트, 사용된 provider 이름)
        """
        provider_chain = self._provider_chain(tier)
        last_error = None

        for provider_key in provider_chain:
            provider = self._providers[tier][provider_key]
            if not await provider.is_available():
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
                    if attempt == 0:
                        logger.warning("{} 호출 실패, 재시도: {}", provider.provider.value, str(e)[:100])
                        await asyncio.sleep(2)
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

    def get_llm_status(self) -> dict:
        """현재 LLM 설정 상태 반환 (Admin API용)"""
        tier1_model = settings.CLAUDE_CODE_MODEL_TIER1 or settings.CLAUDE_CODE_MODEL or "haiku"
        tier2_model = settings.CLAUDE_CODE_MODEL_TIER2 or settings.CLAUDE_CODE_MODEL or "sonnet"
        codex_tier1_model = settings.CODEX_MODEL_TIER1 or settings.CODEX_MODEL or "gpt-5-codex"
        codex_tier2_model = settings.CODEX_MODEL_TIER2 or settings.CODEX_MODEL or "gpt-5-codex"
        tier1_provider = (settings.LLM_PROVIDER_TIER1 or settings.LLM_PROVIDER or "CLAUDE_CODE").upper()
        tier2_provider = (settings.LLM_PROVIDER_TIER2 or settings.LLM_PROVIDER or "CLAUDE_CODE").upper()
        return {
            "tier1": {
                "provider": tier1_provider,
                "fallback_provider": (settings.LLM_FALLBACK_PROVIDER_TIER1 or "").upper(),
                "model": codex_tier1_model if tier1_provider == "CODEX" else tier1_model,
            },
            "tier2": {
                "provider": tier2_provider,
                "fallback_provider": (settings.LLM_FALLBACK_PROVIDER_TIER2 or "").upper(),
                "model": codex_tier2_model if tier2_provider == "CODEX" else tier2_model,
            },
            "available_providers": [
                {
                    "id": "CLAUDE_CODE",
                    "name": "Claude Code (로컬)",
                    "models": {"tier1": tier1_model, "tier2": tier2_model},
                    "has_key": True,
                },
                {
                    "id": "CODEX",
                    "name": "Codex CLI (로컬)",
                    "models": {"tier1": codex_tier1_model, "tier2": codex_tier2_model},
                    "has_key": True,
                },
            ],
        }


llm_factory = LLMFactory()
