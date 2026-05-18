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

export function getStandaloneModelSelectorState(kind, runtimeSettings, provider, mode = 'primary') {
  const isNews = kind === 'news';
  const providerSuffix = isNews ? 'news' : 'manual';
  const prefix = isNews ? 'NEWS_LLM' : 'MANUAL_LLM';
  const isFallback = mode === 'fallback';

  return {
    key: isFallback ? `${prefix}_FALLBACK_MODEL` : `${prefix}_MODEL`,
    provider: provider || '',
    currentValue: runtimeSettings?.[isFallback ? `${prefix}_FALLBACK_MODEL` : `${prefix}_MODEL`] || 'DEFAULT',
    hasProvider: Boolean(provider),
    selectId: isFallback ? `set-${providerSuffix}-llm-fallback-model` : `set-${providerSuffix}-llm-model`,
    sourceId: isFallback ? `llm-${providerSuffix}-fallback-model-source` : `llm-${providerSuffix}-model-source`,
    customId: isFallback ? `set-${providerSuffix}-llm-fallback-model-custom` : `set-${providerSuffix}-llm-model-custom`,
  };
}

export function normalizeLLMExecutionMode(value, fallback = 'SINGLE') {
  const normalized = String(value || '').trim().toUpperCase();
  if (['SINGLE', 'DISTRIBUTED', 'CONSENSUS'].includes(normalized)) {
    return normalized;
  }
  return fallback;
}

export function getLLMExecutionModeSettingKey(scope) {
  if (scope === 'tier1') return 'LLM_EXECUTION_MODE_TIER1';
  if (scope === 'tier2') return 'LLM_EXECUTION_MODE_TIER2';
  if (scope === 'news') return 'NEWS_LLM_EXECUTION_MODE';
  return 'MANUAL_LLM_EXECUTION_MODE';
}

export function getLLMExecutionModeElementId(scope) {
  if (scope === 'tier1') return 'set-llm-tier1-execution-mode';
  if (scope === 'tier2') return 'set-llm-tier2-execution-mode';
  if (scope === 'news') return 'set-news-llm-execution-mode';
  return 'set-manual-llm-execution-mode';
}

export function getDefaultLLMExecutionMode(scope) {
  if (scope === 'tier1' || scope === 'tier2' || scope === 'news') return 'DISTRIBUTED';
  return 'SINGLE';
}

export function normalizeLLMDistributedProfile(value, fallback = 'FAST') {
  const normalized = String(value || '').trim().toUpperCase();
  if (['FAST', 'FULL'].includes(normalized)) {
    return normalized;
  }
  return fallback;
}

export function getDefaultLLMDistributedProfile(scope) {
  return 'FAST';
}

export function buildLLMExecutionModeState({
  scope,
  mode,
  cliSlots = 0,
  apiSlots = 0,
  distributedProfile,
  claudeCodeAvailable = false,
} = {}) {
  const normalizedScope = ['tier1', 'tier2', 'news', 'manual'].includes(scope) ? scope : 'manual';
  const normalizedMode = normalizeLLMExecutionMode(mode, getDefaultLLMExecutionMode(normalizedScope));
  const normalizedProfile = normalizeLLMDistributedProfile(
    distributedProfile,
    getDefaultLLMDistributedProfile(normalizedScope),
  );
  const rawCliSlots = Math.max(Number(cliSlots) || 0, 0);
  const excludedClaudeCodeSlots = normalizedProfile === 'FAST' && claudeCodeAvailable ? 1 : 0;
  const effectiveCliSlots = Math.max(rawCliSlots - excludedClaudeCodeSlots, 0);
  const effectiveApiSlots = Math.max(Number(apiSlots) || 0, 0);
  const totalSlots = effectiveCliSlots + effectiveApiSlots;
  const labels = {
    SINGLE: '메인+풀백',
    DISTRIBUTED: '분산 처리',
    CONSENSUS: '합의 검증',
  };
  const helpByMode = {
    SINGLE: '메인 provider를 먼저 쓰고 실패하면 fallback으로 넘깁니다.',
    DISTRIBUTED: '등록된 CLI/API worker를 후보 체인에 넣고 작업별로 나눠 처리합니다. CLI worker는 안정성을 위해 각 provider별로 하나씩 순차 실행됩니다.',
    CONSENSUS: '중요 판단을 여러 worker로 교차 검증합니다. 속도보다 판단 안정성을 우선합니다.',
  };
  const recommendationByScope = {
    tier1: 'T1은 종목 수가 많아 분산 처리가 기본 추천입니다.',
    tier2: 'T2는 최종 판단이라 빠른 분산 또는 합의 검증이 적합합니다.',
    news: '뉴스 번역/요약은 독립 작업이 많아 분산 처리와 잘 맞습니다.',
    manual: '수동 Q&A와 리포트는 응답 일관성이 중요해 메인+풀백이 적합합니다.',
  };

  return {
    scope: normalizedScope,
    mode: normalizedMode,
    label: labels[normalizedMode],
    helpText: helpByMode[normalizedMode],
    recommendation: recommendationByScope[normalizedScope],
    totalSlots,
    cliSlots: effectiveCliSlots,
    apiSlots: effectiveApiSlots,
    distributedProfile: normalizedProfile,
    profileText: normalizedProfile === 'FULL'
      ? '전체 워커 구성: Claude Code CLI 포함'
      : '빠른 구성: Claude Code CLI 제외',
    usesSingleSelection: normalizedMode === 'SINGLE',
    usesWorkerPool: normalizedMode !== 'SINGLE',
    workerText: `사용 가능 worker ${totalSlots}개 (CLI ${effectiveCliSlots} · API ${effectiveApiSlots})`,
    warningText: normalizedMode !== 'SINGLE' && totalSlots < 2
      ? '등록된 worker가 2개 미만이면 실제 효과는 메인+풀백과 비슷합니다.'
      : '',
    primarySelectionText: normalizedMode === 'DISTRIBUTED'
      ? '이 provider부터 시작하고, 선택한 worker 구성이 후보 체인으로 뒤따릅니다.'
      : (normalizedMode === 'CONSENSUS'
        ? '이 provider를 기준으로 여러 worker의 판단을 비교합니다.'
        : '이 provider를 먼저 쓰고 실패하면 fallback으로 넘깁니다.'),
  };
}
