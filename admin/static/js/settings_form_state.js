const SETTINGS_CONTROL_BINDINGS = [
  {
    key: 'TRADING_ENABLED',
    elementId: 'set-trading',
    type: 'checked',
  },
  {
    key: 'AUTONOMY_MODE',
    elementId: 'set-mode',
  },
  {
    key: 'ORDER_SUBMISSION_MODE',
    elementId: 'set-order-submission-mode',
  },
  {
    key: 'RISK_APPETITE',
    elementId: 'set-risk-appetite',
    shouldApply: (value) => Boolean(value),
  },
  {
    elementId: 'set-loss-streak-recovery-mode',
    getValue: (settings) => settings.LOSS_STREAK_RECOVERY_MODE || 'BLOCK_BUY',
  },
  {
    elementId: 'set-loss-streak-max-daily-buys',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS),
  },
  {
    elementId: 'set-loss-streak-max-order',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_MAX_ORDER_KRW),
  },
  {
    elementId: 'set-loss-streak-max-position',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_MAX_POSITION_PCT),
  },
  {
    elementId: 'set-loss-streak-size-multiplier',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER),
  },
  {
    elementId: 'set-loss-streak-min-change',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT),
  },
  {
    elementId: 'set-loss-streak-max-change',
    getValue: (settings) => stringifyNullable(settings.LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT),
  },
  {
    elementId: 'set-llm-tier1-provider',
    getValue: (settings) => settings.LLM_PROVIDER_TIER1 || settings.LLM_PROVIDER || 'CLAUDE_CODE',
  },
  {
    elementId: 'set-llm-tier1-execution-mode',
    getValue: (settings) => settings.LLM_EXECUTION_MODE_TIER1 || 'DISTRIBUTED',
  },
  {
    elementId: 'set-llm-tier1-distributed-profile',
    getValue: (settings) => settings.LLM_DISTRIBUTED_PROFILE_TIER1 || 'FAST',
  },
  {
    elementId: 'set-llm-tier1-concurrency',
    getValue: (settings) => stringifyNullable(settings.LLM_TIER1_CONCURRENCY),
  },
  {
    elementId: 'set-llm-tier2-provider',
    getValue: (settings) => settings.LLM_PROVIDER_TIER2 || settings.LLM_PROVIDER || 'CLAUDE_CODE',
  },
  {
    elementId: 'set-llm-tier2-execution-mode',
    getValue: (settings) => settings.LLM_EXECUTION_MODE_TIER2 || 'DISTRIBUTED',
  },
  {
    elementId: 'set-llm-tier2-distributed-profile',
    getValue: (settings) => settings.LLM_DISTRIBUTED_PROFILE_TIER2 || 'FAST',
  },
  {
    elementId: 'set-llm-tier2-concurrency',
    getValue: (settings) => stringifyNullable(settings.LLM_TIER2_CONCURRENCY),
  },
  {
    elementId: 'set-llm-tier1-fallback',
    getValue: (settings) => settings.LLM_FALLBACK_PROVIDER_TIER1 || '',
  },
  {
    elementId: 'set-llm-tier2-fallback',
    getValue: (settings) => settings.LLM_FALLBACK_PROVIDER_TIER2 || '',
  },
  {
    elementId: 'set-codex-timeout-tier1',
    getValue: (settings) => stringifyNullable(settings.CODEX_TIMEOUT_SEC_TIER1),
  },
  {
    elementId: 'set-codex-timeout-tier2',
    getValue: (settings) => stringifyNullable(settings.CODEX_TIMEOUT_SEC_TIER2),
  },
  {
    elementId: 'set-claude-effort-tier1',
    getValue: (settings) => settings.CLAUDE_CODE_EFFORT_TIER1 || 'low',
  },
  {
    elementId: 'set-claude-effort-tier2',
    getValue: (settings) => settings.CLAUDE_CODE_EFFORT_TIER2 || 'high',
  },
  {
    elementId: 'set-claude-bare-tier1',
    getValue: (settings) => Boolean(settings.CLAUDE_CODE_BARE_TIER1),
    type: 'checked',
  },
  {
    elementId: 'set-claude-bare-tier2',
    getValue: (settings) => Boolean(settings.CLAUDE_CODE_BARE_TIER2),
    type: 'checked',
  },
  {
    elementId: 'set-codex-effort-tier1',
    getValue: (settings) => settings.CODEX_REASONING_EFFORT_TIER1 || 'low',
  },
  {
    elementId: 'set-codex-effort-tier2',
    getValue: (settings) => settings.CODEX_REASONING_EFFORT_TIER2 || 'high',
  },
  {
    key: 'MANUAL_LLM_PROVIDER',
    elementId: 'set-manual-llm-provider',
    shouldApply: (value) => Boolean(value),
  },
  {
    elementId: 'set-manual-llm-execution-mode',
    getValue: (settings) => settings.MANUAL_LLM_EXECUTION_MODE || 'SINGLE',
  },
  {
    key: 'MANUAL_LLM_FALLBACK_PROVIDER',
    elementId: 'set-manual-llm-fallback-provider',
  },
  {
    elementId: 'set-manual-llm-model',
    getValue: (settings) => settings.MANUAL_LLM_MODEL || 'DEFAULT',
  },
  {
    elementId: 'set-manual-llm-fallback-model',
    getValue: (settings) => settings.MANUAL_LLM_FALLBACK_MODEL || 'DEFAULT',
  },
  {
    elementId: 'set-news-llm-enabled',
    getValue: (settings) => Boolean(settings.NEWS_LLM_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-llm-execution-mode',
    getValue: (settings) => settings.NEWS_LLM_EXECUTION_MODE || 'DISTRIBUTED',
  },
  {
    elementId: 'set-news-llm-provider',
    getValue: (settings) => settings.NEWS_LLM_PROVIDER || 'CLAUDE_CODE',
  },
  {
    elementId: 'set-news-llm-model',
    getValue: (settings) => settings.NEWS_LLM_MODEL || 'DEFAULT',
  },
  {
    elementId: 'set-news-llm-fallback-provider',
    getValue: (settings) => settings.NEWS_LLM_FALLBACK_PROVIDER || '',
  },
  {
    elementId: 'set-news-llm-fallback-model',
    getValue: (settings) => settings.NEWS_LLM_FALLBACK_MODEL || 'DEFAULT',
  },
  {
    elementId: 'set-news-include-foreign',
    getValue: (settings) => Boolean(settings.NEWS_INCLUDE_FOREIGN),
    type: 'checked',
  },
  {
    elementId: 'set-news-translate-foreign-enabled',
    getValue: (settings) => Boolean(settings.NEWS_TRANSLATE_FOREIGN_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-nasdaq-enabled',
    getValue: (settings) => Boolean(settings.NEWS_NASDAQ_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-domestic-media-enabled',
    getValue: (settings) => Boolean(settings.NEWS_DOMESTIC_MEDIA_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-gate-rollout-mode',
    getValue: (settings) => settings.NEWS_GATE_ROLLOUT_MODE || '',
  },
  {
    elementId: 'set-news-gate-enabled',
    getValue: (settings) => Boolean(settings.NEWS_GATE_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-poll-enabled',
    getValue: (settings) => Boolean(settings.NEWS_POLL_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-negative-threshold',
    getValue: (settings) => stringifyNullable(settings.NEWS_NEGATIVE_BLOCK_THRESHOLD),
  },
  {
    elementId: 'set-news-lookback-hours',
    getValue: (settings) => stringifyNullable(settings.NEWS_LOOKBACK_HOURS),
  },
  {
    elementId: 'set-news-poll-interval-trading',
    getValue: (settings) => stringifyNullable(settings.NEWS_POLL_INTERVAL_MIN_TRADING),
  },
  {
    elementId: 'set-news-poll-interval-off',
    getValue: (settings) => stringifyNullable(settings.NEWS_POLL_INTERVAL_MIN_OFF_HOURS),
  },
  {
    elementId: 'set-news-fetch-concurrency',
    getValue: (settings) => stringifyNullable(settings.NEWS_FETCH_CONCURRENCY),
  },
  {
    elementId: 'set-news-translation-concurrency',
    getValue: (settings) => stringifyNullable(settings.NEWS_TRANSLATION_CONCURRENCY),
  },
  {
    elementId: 'set-news-claude-share-session',
    getValue: (settings) => Boolean(settings.NEWS_CLAUDE_SHARE_SESSION),
    type: 'checked',
  },
  {
    elementId: 'set-news-shadow-enabled',
    getValue: (settings) => Boolean(settings.NEWS_SHADOW_ENABLED),
    type: 'checked',
  },
  {
    elementId: 'set-news-rollout-min-sample',
    getValue: (settings) => stringifyNullable(settings.NEWS_ROLLOUT_MIN_SAMPLE_SIZE),
  },
  {
    elementId: 'set-news-rollout-min-pf',
    getValue: (settings) => stringifyNullable(settings.NEWS_ROLLOUT_MIN_PROFIT_FACTOR),
  },
  {
    elementId: 'set-news-rollout-min-expectancy',
    getValue: (settings) => stringifyNullable(settings.NEWS_ROLLOUT_MIN_EXPECTANCY),
  },
  {
    elementId: 'set-news-rollout-max-drawdown',
    getValue: (settings) => stringifyNullable(settings.NEWS_ROLLOUT_MAX_DRAWDOWN_KRW),
  },
  {
    elementId: 'set-ollama-base-url',
    getValue: (settings) => settings.OLLAMA_BASE_URL || '',
  },
  {
    elementId: 'set-ollama-model',
    getValue: (settings) => settings.OLLAMA_MODEL || '',
  },
  {
    elementId: 'set-admin-danger-confirmation-required',
    getValue: (settings) => Boolean(settings.ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED),
    type: 'checked',
  },
];

export function applySettingsToForm(settings, root = document) {
  if (!settings || !root?.getElementById) return;

  SETTINGS_CONTROL_BINDINGS.forEach((binding) => {
    const el = root.getElementById(binding.elementId);
    if (!el) return;

    const rawValue = binding.getValue
      ? binding.getValue(settings)
      : settings[binding.key];

    if (binding.shouldApply && !binding.shouldApply(rawValue, settings)) {
      return;
    }

    if (binding.type === 'checked') {
      el.checked = Boolean(rawValue);
      return;
    }

    el.value = rawValue ?? '';
  });
}

export { SETTINGS_CONTROL_BINDINGS };

function stringifyNullable(value) {
  return value == null ? '' : String(value);
}
