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
    const sessionChange = resolveDirectSettingChange({
      id: "set-news-claude-share-session",
      checked: false,
    });

    expect(fetchChange).toEqual({
      key: "NEWS_FETCH_CONCURRENCY",
      value: "5",
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
