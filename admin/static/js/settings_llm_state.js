export function getTierProviderElementId(tier, mode = 'primary') {
  if (mode === 'fallback') {
    return tier === 'tier1' ? 'set-llm-tier1-fallback' : 'set-llm-tier2-fallback';
  }
  return tier === 'tier1' ? 'set-llm-tier1-provider' : 'set-llm-tier2-provider';
}

export function getTierModelSettingKey(provider, tier, mode = 'primary') {
  if (mode === 'fallback') {
    return tier === 'tier1' ? 'LLM_FALLBACK_MODEL_TIER1' : 'LLM_FALLBACK_MODEL_TIER2';
  }
  if (provider === 'CODEX') {
    return tier === 'tier1' ? 'CODEX_MODEL_TIER1' : 'CODEX_MODEL_TIER2';
  }
  if (provider === 'OLLAMA') {
    return tier === 'tier1' ? 'OLLAMA_MODEL_TIER1' : 'OLLAMA_MODEL_TIER2';
  }
  return tier === 'tier1' ? 'CLAUDE_CODE_MODEL_TIER1' : 'CLAUDE_CODE_MODEL_TIER2';
}

export function getTierModelElementIds(tier, mode = 'primary') {
  const isFallback = mode === 'fallback';
  return {
    selectId: isFallback
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback-model' : 'set-llm-tier2-fallback-model')
      : (tier === 'tier1' ? 'set-llm-tier1-model' : 'set-llm-tier2-model'),
    sourceId: isFallback
      ? (tier === 'tier1' ? 'llm-tier1-fallback-model-source' : 'llm-tier2-fallback-model-source')
      : (tier === 'tier1' ? 'llm-tier1-model-source' : 'llm-tier2-model-source'),
    customId: isFallback
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback-model-custom' : 'set-llm-tier2-fallback-model-custom')
      : (tier === 'tier1' ? 'set-llm-tier1-model-custom' : 'set-llm-tier2-model-custom'),
  };
}

export function resolveTierModelState({ runtimeSettings, tier, mode = 'primary', provider }) {
  const key = getTierModelSettingKey(provider, tier, mode);
  const ids = getTierModelElementIds(tier, mode);
  const isFallback = mode === 'fallback';
  return {
    key,
    provider: isFallback ? (provider || '') : (provider || 'CLAUDE_CODE'),
    currentValue: runtimeSettings?.[key] || 'DEFAULT',
    hasProvider: !isFallback || Boolean(provider),
    isFallback,
    ...ids,
  };
}

export function getManualModelSelectorState(runtimeSettings, provider) {
  return {
    provider: provider || 'AUTOMATIC',
    currentValue: runtimeSettings?.MANUAL_LLM_MODEL || 'DEFAULT',
    selectId: 'set-manual-llm-model',
    sourceId: 'llm-manual-model-source',
    customId: 'set-manual-llm-model-custom',
    automatic: !provider || provider === 'AUTOMATIC',
  };
}
