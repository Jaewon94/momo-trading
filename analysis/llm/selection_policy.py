from __future__ import annotations

from dataclasses import dataclass

from core.config import DEFAULT_LLM_MODEL, normalize_llm_model_value, settings
from trading.enums import LLMProvider, LLMTier


@dataclass(frozen=True)
class TierSelection:
    provider: LLMProvider
    model: str
    fallback_provider: str
    fallback_model: str


@dataclass(frozen=True)
class ManualSelection:
    provider: str
    model: str
    provider_chain: tuple[LLMProvider, ...]
    provider_model_overrides: dict[LLMProvider, str] | None


@dataclass(frozen=True)
class NewsSelection:
    enabled: bool
    provider: str
    model: str | None


def provider_from_name(value: str | None, default: LLMProvider = LLMProvider.CLAUDE_CODE) -> LLMProvider:
    if not value:
        return default
    return LLMProvider(str(value).upper())


def resolve_tier_selection(tier: LLMTier) -> TierSelection:
    primary_default = settings.LLM_PROVIDER or LLMProvider.CLAUDE_CODE.value
    primary_name = (
        settings.LLM_PROVIDER_TIER1 if tier == LLMTier.TIER1 else settings.LLM_PROVIDER_TIER2
    ) or primary_default
    fallback_name = (
        settings.LLM_FALLBACK_PROVIDER_TIER1 if tier == LLMTier.TIER1 else settings.LLM_FALLBACK_PROVIDER_TIER2
    ) or ""
    provider = provider_from_name(primary_name)
    fallback_provider = str(fallback_name).upper()
    fallback_model = normalize_llm_model_value(
        settings.LLM_FALLBACK_MODEL_TIER1 if tier == LLMTier.TIER1 else settings.LLM_FALLBACK_MODEL_TIER2
    )
    model = _model_for_provider(
        provider,
        tier=tier,
    )
    return TierSelection(
        provider=provider,
        model=model,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
    )


def resolve_manual_selection(
    default_tier: LLMTier,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> ManualSelection:
    selection = (provider_override or settings.MANUAL_LLM_PROVIDER or "AUTOMATIC").upper()
    if selection == "AUTOMATIC":
        tier_selection = resolve_tier_selection(default_tier)
        return ManualSelection(
            provider="AUTOMATIC",
            model=normalize_llm_model_value(model_override or settings.MANUAL_LLM_MODEL),
            provider_chain=(tier_selection.provider,)
            if not tier_selection.fallback_provider
            else (tier_selection.provider, provider_from_name(tier_selection.fallback_provider)),
            provider_model_overrides=None,
        )

    provider = provider_from_name(selection)
    normalized_model = normalize_llm_model_value(model_override or settings.MANUAL_LLM_MODEL)
    overrides = None
    if normalized_model != DEFAULT_LLM_MODEL:
        overrides = {provider: normalized_model}
    return ManualSelection(
        provider=selection,
        model=normalized_model,
        provider_chain=(provider,),
        provider_model_overrides=overrides,
    )


def resolve_news_selection() -> NewsSelection:
    provider = (settings.NEWS_LLM_PROVIDER or "AUTOMATIC").upper()
    model = None
    if provider == LLMProvider.OLLAMA.value:
        model = normalize_llm_model_value(settings.NEWS_OLLAMA_MODEL)
    return NewsSelection(
        enabled=bool(settings.NEWS_LLM_ENABLED),
        provider=provider,
        model=model,
    )


def model_for_status(provider_name: str, tier: LLMTier) -> str:
    return _model_for_provider(provider_from_name(provider_name), tier=tier)


def _model_for_provider(provider: LLMProvider, *, tier: LLMTier) -> str:
    if provider == LLMProvider.CODEX:
        value = settings.CODEX_MODEL_TIER1 if tier == LLMTier.TIER1 else settings.CODEX_MODEL_TIER2
        return normalize_llm_model_value(value or settings.CODEX_MODEL)
    if provider == LLMProvider.OLLAMA:
        value = settings.OLLAMA_MODEL_TIER1 if tier == LLMTier.TIER1 else settings.OLLAMA_MODEL_TIER2
        return normalize_llm_model_value(value or settings.OLLAMA_MODEL)
    value = settings.CLAUDE_CODE_MODEL_TIER1 if tier == LLMTier.TIER1 else settings.CLAUDE_CODE_MODEL_TIER2
    return normalize_llm_model_value(value or settings.CLAUDE_CODE_MODEL)
