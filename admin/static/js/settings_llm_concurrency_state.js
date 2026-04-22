const TIER_CONCURRENCY_COPY = {
  tier1: {
    default: 'Tier1 호출을 동시에 몇 개까지 허용할지 정합니다.',
    codex: 'Codex는 안정성을 위해 실제로 1개씩 직렬 실행됩니다. 이 병렬 값은 Codex 경로에 직접 적용되지 않습니다.',
  },
  tier2: {
    default: 'Tier2 검토 호출의 병렬 실행 상한입니다.',
    codex: 'Codex는 안정성을 위해 실제로 1개씩 직렬 실행됩니다. 이 병렬 값은 Codex 검토 경로에 직접 적용되지 않습니다.',
  },
};

export function buildTierConcurrencyFieldState({ tier, provider }) {
  const normalizedTier = tier === 'tier2' ? 'tier2' : 'tier1';
  const normalizedProvider = String(provider || '').trim().toUpperCase();
  const isCodex = normalizedProvider === 'CODEX';
  const copy = TIER_CONCURRENCY_COPY[normalizedTier];

  return {
    disabled: isCodex,
    helpText: isCodex ? copy.codex : copy.default,
    helpTone: isCodex ? 'warn' : 'neutral',
  };
}

export function buildNewsTranslationConcurrencyFieldState({ provider }) {
  const normalizedProvider = String(provider || '').trim().toUpperCase();
  if (normalizedProvider === 'CODEX') {
    return {
      disabled: true,
      helpText: 'Codex는 안정성을 위해 실제로 1개씩 직렬 실행됩니다. 이 병렬 값은 Codex 뉴스 번역 경로에 직접 적용되지 않습니다.',
      helpTone: 'warn',
    };
  }
  if (normalizedProvider === 'OLLAMA') {
    return {
      disabled: true,
      helpText: 'Ollama는 뉴스 번역을 항상 1개씩 처리합니다. 이 병렬 값은 Ollama 뉴스 번역 경로에 직접 적용되지 않습니다.',
      helpTone: 'warn',
    };
  }
  return {
    disabled: false,
    helpText: '해외 뉴스 번역/감성 분석 동시 처리 수입니다.',
    helpTone: 'neutral',
  };
}
