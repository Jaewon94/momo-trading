import { describe, expect, test } from "vitest";

import {
  SETTINGS_TABS,
  normalizeSettingsTab,
} from "../../admin/static/js/settings_modal_state.js";

describe("settings_modal_state", () => {
  test("keeps tab order stable for settings center", () => {
    expect(SETTINGS_TABS).toEqual(["operating", "strategy", "llm", "system"]);
  });

  test("normalizes unknown tabs to operating", () => {
    expect(normalizeSettingsTab("strategy")).toBe("strategy");
    expect(normalizeSettingsTab("llm")).toBe("llm");
    expect(normalizeSettingsTab("weird")).toBe("operating");
  });
});
