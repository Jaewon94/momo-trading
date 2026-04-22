import { describe, expect, test } from "vitest";

import {
  resolveDirectSettingChange,
  resolveTierModelSettingChange,
} from "../../admin/static/js/settings_action_state.js";

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
    const translateForeignChange = resolveDirectSettingChange({
      id: "set-news-translate-foreign-enabled",
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
    expect(translateForeignChange).toEqual({
      key: "NEWS_TRANSLATE_FOREIGN_ENABLED",
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

  test("maps order submission mode control", () => {
    const change = resolveDirectSettingChange({
      id: "set-order-submission-mode",
      value: "READ_ONLY",
    });

    expect(change).toEqual({
      key: "ORDER_SUBMISSION_MODE",
      value: "READ_ONLY",
    });
  });

  test("returns null for unmanaged controls", () => {
    expect(resolveDirectSettingChange({ id: "trade-center-sort", value: "latest" })).toBeNull();
  });

  test("maps tier model controls using the active provider", () => {
    expect(
      resolveTierModelSettingChange({
        tier: "tier1",
        provider: "CLAUDE_CODE",
        value: "claude-haiku-4-5-20251001",
      }),
    ).toEqual({
      key: "CLAUDE_CODE_MODEL_TIER1",
      value: "claude-haiku-4-5-20251001",
    });

    expect(
      resolveTierModelSettingChange({
        tier: "tier2",
        mode: "fallback",
        provider: "CODEX",
        value: "gpt-5.4",
      }),
    ).toEqual({
      key: "LLM_FALLBACK_MODEL_TIER2",
      value: "gpt-5.4",
    });
  });
});
