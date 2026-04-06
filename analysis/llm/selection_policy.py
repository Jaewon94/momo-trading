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
    fallback_provider: str
    fallback_model: str
    provider_chain: tuple[LLMProvider, ...]
    provider_model_overrides: dict[LLMProvider, str] | None


@dataclass(frozen=True)
class NewsSelection:
    enabled: bool
    provider: str
    model: str
    fallback_provider: str
    fallback_model: str
    provider_chain: tuple[LLMProvider, ...]
    provider_model_overrides: dict[LLMProvider, str] | None


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
    primary_name = (provider_override or settings.MANUAL_LLM_PROVIDER or "CLAUDE_CODE").upper()
    fallback_name = settings.MANUAL_LLM_FALLBACK_PROVIDER
    fallback_model = settings.MANUAL_LLM_FALLBACK_MODEL

    if primary_name == "AUTOMATIC":
        tier_selection = resolve_tier_selection(default_tier)
        primary_name = tier_selection.provider.value
        if not fallback_name:
            fallback_name = tier_selection.fallback_provider
            fallback_model = tier_selection.fallback_model

    return _build_explicit_selection(
        primary_name=primary_name,
        primary_model=model_override or settings.MANUAL_LLM_MODEL,
        fallback_name=fallback_name,
        fallback_model=fallback_model,
        selection_type=ManualSelection,
    )


def resolve_news_selection() -> NewsSelection:
    primary_name = (settings.NEWS_LLM_PROVIDER or "CLAUDE_CODE").upper()
    fallback_name = settings.NEWS_LLM_FALLBACK_PROVIDER
    fallback_model = settings.NEWS_LLM_FALLBACK_MODEL
    if primary_name == "AUTOMATIC":
        tier_selection = resolve_tier_selection(LLMTier.TIER1)
        primary_name = tier_selection.provider.value
        if not fallback_name:
            fallback_name = tier_selection.fallback_provider
            fallback_model = tier_selection.fallback_model

    base_selection = _build_explicit_selection(
        primary_name=primary_name,
        primary_model=settings.NEWS_LLM_MODEL,
        fallback_name=fallback_name,
        fallback_model=fallback_model,
    )
    return NewsSelection(
        enabled=bool(settings.NEWS_LLM_ENABLED),
        provider=base_selection.provider,
        model=base_selection.model,
        fallback_provider=base_selection.fallback_provider,
        fallback_model=base_selection.fallback_model,
        provider_chain=base_selection.provider_chain,
        provider_model_overrides=base_selection.provider_model_overrides,
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


def _build_explicit_selection(
    *,
    primary_name: str,
    primary_model: str | None,
    fallback_name: str | None,
    fallback_model: str | None,
    selection_type=ManualSelection,
):
    provider = provider_from_name(primary_name)
    normalized_model = normalize_llm_model_value(primary_model)
    normalized_fallback_provider = str(fallback_name or "").upper()
    normalized_fallback_model = normalize_llm_model_value(fallback_model)

    chain: list[LLMProvider] = [provider]
    overrides: dict[LLMProvider, str] = {}
    if normalized_model != DEFAULT_LLM_MODEL:
        overrides[provider] = normalized_model

    if normalized_fallback_provider:
        fallback_provider = provider_from_name(normalized_fallback_provider)
        if fallback_provider != provider:
            chain.append(fallback_provider)
            if normalized_fallback_model != DEFAULT_LLM_MODEL:
                overrides[fallback_provider] = normalized_fallback_model
        else:
            normalized_fallback_provider = ""

    return selection_type(
        provider=provider.value,
        model=normalized_model,
        fallback_provider=normalized_fallback_provider,
        fallback_model=normalized_fallback_model if normalized_fallback_provider else DEFAULT_LLM_MODEL,
        provider_chain=tuple(chain),
        provider_model_overrides=overrides or None,
    )
