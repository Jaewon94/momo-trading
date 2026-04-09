import { describe, expect, test } from "vitest";

import { resolveDirectSettingChange } from "../../admin/static/js/settings_action_state.js";

describe("settings_action_state", () => {
  test("maps checkbox controls to boolean setting updates", () => {
    const change = resolveDirectSettingChange({
      id: "set-news-llm-enabled",
      checked: true,
    });

    expect(change).toEqual({
      key: "NEWS_LLM_ENABLED",
      value: true,
    });
  });

  test("maps new news concurrency controls", () => {
    const fetchChange = resolveDirectSettingChange({
      id: "set-news-fetch-concurrency",
      value: "5",
    });
    const tier1ConcurrencyChange = resolveDirectSettingChange({
      id: "set-llm-tier1-concurrency",
      value: "2",
    });
    const tier1TimeoutChange = resolveDirectSettingChange({
      id: "set-codex-timeout-tier1",
      value: "90",
    });
    const sessionChange = resolveDirectSettingChange({
      id: "set-news-claude-share-session",
      checked: false,
    });

    expect(fetchChange).toEqual({
      key: "NEWS_FETCH_CONCURRENCY",
      value: "5",
    });
    expect(tier1ConcurrencyChange).toEqual({
      key: "LLM_TIER1_CONCURRENCY",
      value: "2",
    });
    expect(tier1TimeoutChange).toEqual({
      key: "CODEX_TIMEOUT_SEC_TIER1",
      value: "90",
    });
    expect(sessionChange).toEqual({
      key: "NEWS_CLAUDE_SHARE_SESSION",
      value: false,
    });
  });

  test("maps text/select controls to string setting updates", () => {
    const primaryChange = resolveDirectSettingChange({
      id: "set-manual-llm-provider",
      value: "CODEX",
    });
    const fallbackChange = resolveDirectSettingChange({
      id: "set-news-llm-fallback-provider",
      value: "OLLAMA",
    });

    expect(primaryChange).toEqual({
      key: "MANUAL_LLM_PROVIDER",
      value: "CODEX",
    });
    expect(fallbackChange).toEqual({
      key: "NEWS_LLM_FALLBACK_PROVIDER",
      value: "OLLAMA",
    });
  });

  test("returns null for unmanaged controls", () => {
    expect(resolveDirectSettingChange({ id: "trade-center-sort", value: "latest" })).toBeNull();
  });
});
