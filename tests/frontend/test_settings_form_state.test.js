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
      "set-llm-tier1-provider",
      "set-llm-tier2-provider",
      "set-llm-tier1-fallback",
      "set-llm-tier2-fallback",
      "set-manual-llm-provider",
      "set-manual-llm-model",
      "set-news-llm-enabled",
      "set-news-llm-provider",
      "set-news-ollama-model",
      "set-news-include-foreign",
      "set-news-negative-threshold",
      "set-news-poll-interval-trading",
      "set-ollama-base-url",
      "set-ollama-model",
    ]);

    applySettingsToForm(
      {
        TRADING_ENABLED: true,
        AUTONOMY_MODE: "AUTONOMOUS",
        RISK_APPETITE: "AGGRESSIVE",
        LLM_PROVIDER: "CLAUDE_CODE",
        LLM_PROVIDER_TIER1: "CODEX",
        LLM_FALLBACK_PROVIDER_TIER1: "OLLAMA",
        MANUAL_LLM_PROVIDER: "CODEX",
        MANUAL_LLM_MODEL: "gpt-5.4",
        NEWS_LLM_ENABLED: true,
        NEWS_LLM_PROVIDER: "OLLAMA",
        NEWS_OLLAMA_MODEL: "qwen2.5:14b",
        NEWS_INCLUDE_FOREIGN: true,
        NEWS_NEGATIVE_BLOCK_THRESHOLD: 0.65,
        NEWS_POLL_INTERVAL_MIN_TRADING: 3,
        OLLAMA_BASE_URL: "http://127.0.0.1:11434",
        OLLAMA_MODEL: "llama3.1:8b",
      },
      root,
    );

    expect(root.elements["set-trading"].checked).toBe(true);
    expect(root.elements["set-mode"].value).toBe("AUTONOMOUS");
    expect(root.elements["set-risk-appetite"].value).toBe("AGGRESSIVE");
    expect(root.elements["set-llm-tier1-provider"].value).toBe("CODEX");
    expect(root.elements["set-llm-tier2-provider"].value).toBe("CLAUDE_CODE");
    expect(root.elements["set-llm-tier1-fallback"].value).toBe("OLLAMA");
    expect(root.elements["set-llm-tier2-fallback"].value).toBe("");
    expect(root.elements["set-manual-llm-provider"].value).toBe("CODEX");
    expect(root.elements["set-manual-llm-model"].value).toBe("gpt-5.4");
    expect(root.elements["set-news-llm-enabled"].checked).toBe(true);
    expect(root.elements["set-news-llm-provider"].value).toBe("OLLAMA");
    expect(root.elements["set-news-ollama-model"].value).toBe("qwen2.5:14b");
    expect(root.elements["set-news-include-foreign"].checked).toBe(true);
    expect(root.elements["set-news-negative-threshold"].value).toBe("0.65");
    expect(root.elements["set-news-poll-interval-trading"].value).toBe("3");
    expect(root.elements["set-ollama-base-url"].value).toBe("http://127.0.0.1:11434");
    expect(root.elements["set-ollama-model"].value).toBe("llama3.1:8b");
  });

  test("keeps optional values untouched when source value is empty", () => {
    const root = createRoot([
      "set-risk-appetite",
      "set-manual-llm-provider",
    ]);
    root.elements["set-risk-appetite"].value = "MODERATE";
    root.elements["set-manual-llm-provider"].value = "AUTOMATIC";

    applySettingsToForm(
      {
        RISK_APPETITE: "",
        MANUAL_LLM_PROVIDER: "",
      },
      root,
    );

    expect(root.elements["set-risk-appetite"].value).toBe("MODERATE");
    expect(root.elements["set-manual-llm-provider"].value).toBe("AUTOMATIC");
  });
});
