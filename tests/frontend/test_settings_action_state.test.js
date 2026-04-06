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

  test("maps text/select controls to string setting updates", () => {
    const change = resolveDirectSettingChange({
      id: "set-manual-llm-provider",
      value: "CODEX",
    });

    expect(change).toEqual({
      key: "MANUAL_LLM_PROVIDER",
      value: "CODEX",
    });
  });

  test("returns null for unmanaged controls", () => {
    expect(resolveDirectSettingChange({ id: "trade-center-sort", value: "latest" })).toBeNull();
  });
});
