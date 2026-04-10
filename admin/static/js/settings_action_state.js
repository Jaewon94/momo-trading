import { getTierModelSettingKey } from "./settings_llm_state.js";

const DIRECT_SETTING_BINDINGS = [
  bindChecked('set-trading', 'TRADING_ENABLED'),
  bindValue('set-mode', 'AUTONOMY_MODE'),
  bindValue('set-risk-appetite', 'RISK_APPETITE'),
  bindValue('set-news-llm-provider', 'NEWS_LLM_PROVIDER'),
  bindValue('set-news-llm-model', 'NEWS_LLM_MODEL'),
  bindValue('set-news-llm-fallback-provider', 'NEWS_LLM_FALLBACK_PROVIDER'),
  bindValue('set-news-llm-fallback-model', 'NEWS_LLM_FALLBACK_MODEL'),
  bindChecked('set-news-llm-enabled', 'NEWS_LLM_ENABLED'),
  bindChecked('set-news-include-foreign', 'NEWS_INCLUDE_FOREIGN'),
  bindChecked('set-news-nasdaq-enabled', 'NEWS_NASDAQ_ENABLED'),
  bindChecked('set-news-domestic-media-enabled', 'NEWS_DOMESTIC_MEDIA_ENABLED'),
  bindChecked('set-news-gate-enabled', 'NEWS_GATE_ENABLED'),
  bindChecked('set-news-poll-enabled', 'NEWS_POLL_ENABLED'),
  bindChecked('set-news-shadow-enabled', 'NEWS_SHADOW_ENABLED'),
  bindValue('set-news-negative-threshold', 'NEWS_NEGATIVE_BLOCK_THRESHOLD'),
  bindValue('set-news-lookback-hours', 'NEWS_LOOKBACK_HOURS'),
  bindValue('set-news-poll-interval-trading', 'NEWS_POLL_INTERVAL_MIN_TRADING'),
  bindValue('set-news-poll-interval-off', 'NEWS_POLL_INTERVAL_MIN_OFF_HOURS'),
  bindValue('set-news-fetch-concurrency', 'NEWS_FETCH_CONCURRENCY'),
  bindValue('set-news-translation-concurrency', 'NEWS_TRANSLATION_CONCURRENCY'),
  bindChecked('set-news-claude-share-session', 'NEWS_CLAUDE_SHARE_SESSION'),
  bindValue('set-news-rollout-min-sample', 'NEWS_ROLLOUT_MIN_SAMPLE_SIZE'),
  bindValue('set-news-rollout-min-pf', 'NEWS_ROLLOUT_MIN_PROFIT_FACTOR'),
  bindValue('set-news-rollout-min-expectancy', 'NEWS_ROLLOUT_MIN_EXPECTANCY'),
  bindValue('set-news-rollout-max-drawdown', 'NEWS_ROLLOUT_MAX_DRAWDOWN_KRW'),
  bindValue('set-ollama-base-url', 'OLLAMA_BASE_URL'),
  bindValue('set-ollama-model', 'OLLAMA_MODEL'),
  bindValue('set-llm-tier1-provider', 'LLM_PROVIDER_TIER1'),
  bindValue('set-llm-tier1-concurrency', 'LLM_TIER1_CONCURRENCY'),
  bindValue('set-llm-tier2-provider', 'LLM_PROVIDER_TIER2'),
  bindValue('set-llm-tier2-concurrency', 'LLM_TIER2_CONCURRENCY'),
  bindValue('set-llm-tier1-fallback', 'LLM_FALLBACK_PROVIDER_TIER1'),
  bindValue('set-llm-tier2-fallback', 'LLM_FALLBACK_PROVIDER_TIER2'),
  bindValue('set-codex-timeout-tier1', 'CODEX_TIMEOUT_SEC_TIER1'),
  bindValue('set-codex-timeout-tier2', 'CODEX_TIMEOUT_SEC_TIER2'),
  bindValue('set-manual-llm-provider', 'MANUAL_LLM_PROVIDER'),
  bindValue('set-manual-llm-model', 'MANUAL_LLM_MODEL'),
  bindValue('set-manual-llm-fallback-provider', 'MANUAL_LLM_FALLBACK_PROVIDER'),
  bindValue('set-manual-llm-fallback-model', 'MANUAL_LLM_FALLBACK_MODEL'),
];

const DIRECT_SETTING_BINDINGS_BY_ID = new Map(
  DIRECT_SETTING_BINDINGS.map((binding) => [binding.elementId, binding]),
);

export function resolveDirectSettingChange(target) {
  const elementId = target?.id;
  if (!elementId) return null;

  const binding = DIRECT_SETTING_BINDINGS_BY_ID.get(elementId);
  if (!binding) return null;

  return {
    key: binding.key,
    value: binding.readValue(target),
  };
}

export function resolveTierModelSettingChange({
  tier,
  provider,
  value,
  mode = "primary",
}) {
  if (!tier) return null;
  const key = getTierModelSettingKey(provider, tier, mode);
  return {
    key,
    value: value ?? "DEFAULT",
  };
}

export { DIRECT_SETTING_BINDINGS };

function bindChecked(elementId, key) {
  return {
    elementId,
    key,
    readValue: (target) => Boolean(target?.checked),
  };
}

function bindValue(elementId, key) {
  return {
    elementId,
    key,
    readValue: (target) => target?.value ?? '',
  };
}
