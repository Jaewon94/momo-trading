import { describe, expect, test } from "vitest";

import { applySettingsToForm } from "../../admin/static/js/settings_form_state.js";

function createRoot(ids) {
  const elements = Object.fromEntries(
    ids.map((id) => [id, { value: "", checked: false }]),
  );
  return {
    elements,
    getElementById(id) {
      return elements[id] || null;
    },
  };
}

describe("settings_form_state", () => {
  test("applies mapped runtime settings to form controls", () => {
    const root = createRoot([
      "set-trading",
      "set-mode",
      "set-risk-appetite",
      "set-loss-streak-recovery-mode",
      "set-loss-streak-max-daily-buys",
      "set-loss-streak-max-order",
      "set-loss-streak-max-position",
      "set-loss-streak-size-multiplier",
      "set-loss-streak-min-change",
      "set-loss-streak-max-change",
      "set-llm-tier1-provider",
      "set-llm-tier1-execution-mode",
      "set-llm-tier1-distributed-profile",
      "set-llm-tier1-concurrency",
      "set-llm-tier2-provider",
      "set-llm-tier2-execution-mode",
      "set-llm-tier2-distributed-profile",
      "set-llm-tier2-concurrency",
      "set-llm-tier1-fallback",
      "set-llm-tier2-fallback",
      "set-codex-timeout-tier1",
      "set-codex-timeout-tier2",
      "set-claude-effort-tier1",
      "set-claude-effort-tier2",
      "set-claude-bare-tier1",
      "set-claude-bare-tier2",
      "set-codex-effort-tier1",
      "set-codex-effort-tier2",
      "set-manual-llm-provider",
      "set-manual-llm-execution-mode",
      "set-manual-llm-model",
      "set-manual-llm-fallback-provider",
      "set-manual-llm-fallback-model",
      "set-news-llm-enabled",
      "set-news-llm-execution-mode",
      "set-news-llm-provider",
      "set-news-llm-model",
      "set-news-llm-fallback-provider",
      "set-news-llm-fallback-model",
      "set-news-include-foreign",
      "set-news-translate-foreign-enabled",
      "set-news-negative-threshold",
      "set-news-poll-interval-trading",
      "set-news-fetch-concurrency",
      "set-news-translation-concurrency",
      "set-news-claude-share-session",
      "set-ollama-base-url",
      "set-ollama-model",
      "set-admin-danger-confirmation-required",
    ]);

    applySettingsToForm(
      {
        TRADING_ENABLED: true,
        AUTONOMY_MODE: "AUTONOMOUS",
        RISK_APPETITE: "AGGRESSIVE",
        LOSS_STREAK_RECOVERY_MODE: "PROBATION",
        LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS: 1,
        LOSS_STREAK_RECOVERY_MAX_ORDER_KRW: 1_000_000,
        LOSS_STREAK_RECOVERY_MAX_POSITION_PCT: 0.5,
        LOSS_STREAK_RECOVERY_SIZE_MULTIPLIER: 0.2,
        LOSS_STREAK_RECOVERY_MIN_CHANGE_PCT: 2.0,
        LOSS_STREAK_RECOVERY_MAX_CHANGE_PCT: 10.0,
        LLM_PROVIDER: "CLAUDE_CODE",
        LLM_PROVIDER_TIER1: "CODEX",
        LLM_EXECUTION_MODE_TIER1: "DISTRIBUTED",
        LLM_DISTRIBUTED_PROFILE_TIER1: "FAST",
        LLM_TIER1_CONCURRENCY: 2,
        LLM_EXECUTION_MODE_TIER2: "CONSENSUS",
        LLM_DISTRIBUTED_PROFILE_TIER2: "FULL",
        LLM_FALLBACK_PROVIDER_TIER1: "OLLAMA",
        LLM_TIER2_CONCURRENCY: 1,
        CODEX_TIMEOUT_SEC_TIER1: 90,
        CODEX_TIMEOUT_SEC_TIER2: 180,
        CLAUDE_CODE_EFFORT_TIER1: "low",
        CLAUDE_CODE_EFFORT_TIER2: "high",
        CLAUDE_CODE_BARE_TIER1: true,
        CLAUDE_CODE_BARE_TIER2: false,
        CODEX_REASONING_EFFORT_TIER1: "low",
        CODEX_REASONING_EFFORT_TIER2: "high",
        MANUAL_LLM_PROVIDER: "CODEX",
        MANUAL_LLM_EXECUTION_MODE: "SINGLE",
        MANUAL_LLM_MODEL: "gpt-5.4",
        MANUAL_LLM_FALLBACK_PROVIDER: "CLAUDE_CODE",
        MANUAL_LLM_FALLBACK_MODEL: "claude-sonnet-4-6",
        NEWS_LLM_ENABLED: true,
        NEWS_LLM_EXECUTION_MODE: "DISTRIBUTED",
        NEWS_LLM_PROVIDER: "OLLAMA",
        NEWS_LLM_MODEL: "qwen2.5:14b",
        NEWS_LLM_FALLBACK_PROVIDER: "CODEX",
        NEWS_LLM_FALLBACK_MODEL: "gpt-5.4",
        NEWS_INCLUDE_FOREIGN: true,
        NEWS_TRANSLATE_FOREIGN_ENABLED: false,
        NEWS_NEGATIVE_BLOCK_THRESHOLD: 0.65,
        NEWS_POLL_INTERVAL_MIN_TRADING: 3,
        NEWS_FETCH_CONCURRENCY: 5,
        NEWS_TRANSLATION_CONCURRENCY: 2,
        NEWS_CLAUDE_SHARE_SESSION: false,
        OLLAMA_BASE_URL: "http://127.0.0.1:11434",
        OLLAMA_MODEL: "llama3.1:8b",
        ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED: true,
      },
      root,
    );

    expect(root.elements["set-trading"].checked).toBe(true);
    expect(root.elements["set-mode"].value).toBe("AUTONOMOUS");
    expect(root.elements["set-risk-appetite"].value).toBe("AGGRESSIVE");
    expect(root.elements["set-loss-streak-recovery-mode"].value).toBe("PROBATION");
    expect(root.elements["set-loss-streak-max-daily-buys"].value).toBe("1");
    expect(root.elements["set-loss-streak-max-order"].value).toBe("1000000");
    expect(root.elements["set-loss-streak-max-position"].value).toBe("0.5");
    expect(root.elements["set-loss-streak-size-multiplier"].value).toBe("0.2");
    expect(root.elements["set-loss-streak-min-change"].value).toBe("2");
    expect(root.elements["set-loss-streak-max-change"].value).toBe("10");
    expect(root.elements["set-llm-tier1-provider"].value).toBe("CODEX");
    expect(root.elements["set-llm-tier1-execution-mode"].value).toBe("DISTRIBUTED");
    expect(root.elements["set-llm-tier1-distributed-profile"].value).toBe("FAST");
    expect(root.elements["set-llm-tier1-concurrency"].value).toBe("2");
    expect(root.elements["set-llm-tier2-provider"].value).toBe("CLAUDE_CODE");
    expect(root.elements["set-llm-tier2-execution-mode"].value).toBe("CONSENSUS");
    expect(root.elements["set-llm-tier2-distributed-profile"].value).toBe("FULL");
    expect(root.elements["set-llm-tier2-concurrency"].value).toBe("1");
    expect(root.elements["set-llm-tier1-fallback"].value).toBe("OLLAMA");
    expect(root.elements["set-llm-tier2-fallback"].value).toBe("");
    expect(root.elements["set-codex-timeout-tier1"].value).toBe("90");
    expect(root.elements["set-codex-timeout-tier2"].value).toBe("180");
    expect(root.elements["set-claude-effort-tier1"].value).toBe("low");
    expect(root.elements["set-claude-effort-tier2"].value).toBe("high");
    expect(root.elements["set-claude-bare-tier1"].checked).toBe(true);
    expect(root.elements["set-claude-bare-tier2"].checked).toBe(false);
    expect(root.elements["set-codex-effort-tier1"].value).toBe("low");
    expect(root.elements["set-codex-effort-tier2"].value).toBe("high");
    expect(root.elements["set-manual-llm-provider"].value).toBe("CODEX");
    expect(root.elements["set-manual-llm-execution-mode"].value).toBe("SINGLE");
    expect(root.elements["set-manual-llm-model"].value).toBe("gpt-5.4");
    expect(root.elements["set-manual-llm-fallback-provider"].value).toBe("CLAUDE_CODE");
    expect(root.elements["set-manual-llm-fallback-model"].value).toBe("claude-sonnet-4-6");
    expect(root.elements["set-news-llm-enabled"].checked).toBe(true);
    expect(root.elements["set-news-llm-execution-mode"].value).toBe("DISTRIBUTED");
    expect(root.elements["set-news-llm-provider"].value).toBe("OLLAMA");
    expect(root.elements["set-news-llm-model"].value).toBe("qwen2.5:14b");
    expect(root.elements["set-news-llm-fallback-provider"].value).toBe("CODEX");
    expect(root.elements["set-news-llm-fallback-model"].value).toBe("gpt-5.4");
    expect(root.elements["set-news-include-foreign"].checked).toBe(true);
    expect(root.elements["set-news-translate-foreign-enabled"].checked).toBe(false);
    expect(root.elements["set-news-negative-threshold"].value).toBe("0.65");
    expect(root.elements["set-news-poll-interval-trading"].value).toBe("3");
    expect(root.elements["set-news-fetch-concurrency"].value).toBe("5");
    expect(root.elements["set-news-translation-concurrency"].value).toBe("2");
    expect(root.elements["set-news-claude-share-session"].checked).toBe(false);
    expect(root.elements["set-ollama-base-url"].value).toBe("http://127.0.0.1:11434");
    expect(root.elements["set-ollama-model"].value).toBe("llama3.1:8b");
    expect(root.elements["set-admin-danger-confirmation-required"].checked).toBe(true);
  });

  test("applies execution mode defaults when runtime settings are missing", () => {
    const root = createRoot([
      "set-llm-tier1-execution-mode",
      "set-llm-tier1-distributed-profile",
      "set-llm-tier2-execution-mode",
      "set-llm-tier2-distributed-profile",
      "set-manual-llm-execution-mode",
      "set-news-llm-execution-mode",
    ]);

    applySettingsToForm({}, root);

    expect(root.elements["set-llm-tier1-execution-mode"].value).toBe("DISTRIBUTED");
    expect(root.elements["set-llm-tier1-distributed-profile"].value).toBe("FAST");
    expect(root.elements["set-llm-tier2-execution-mode"].value).toBe("SINGLE");
    expect(root.elements["set-llm-tier2-distributed-profile"].value).toBe("FULL");
    expect(root.elements["set-manual-llm-execution-mode"].value).toBe("SINGLE");
    expect(root.elements["set-news-llm-execution-mode"].value).toBe("DISTRIBUTED");
  });

  test("keeps optional values untouched when source value is empty", () => {
    const root = createRoot([
      "set-risk-appetite",
      "set-manual-llm-provider",
      "set-manual-llm-fallback-provider",
    ]);
    root.elements["set-risk-appetite"].value = "MODERATE";
    root.elements["set-manual-llm-provider"].value = "CLAUDE_CODE";
    root.elements["set-manual-llm-fallback-provider"].value = "CODEX";

    applySettingsToForm(
      {
        RISK_APPETITE: "",
        MANUAL_LLM_PROVIDER: "",
      },
      root,
    );

    expect(root.elements["set-risk-appetite"].value).toBe("MODERATE");
    expect(root.elements["set-manual-llm-provider"].value).toBe("CLAUDE_CODE");
    expect(root.elements["set-manual-llm-fallback-provider"].value).toBe("");
  });
});
