import { describe, expect, test } from "vitest";

import {
  getManualModelSelectorState,
  getTierModelElementIds,
  getTierModelSettingKey,
  getTierProviderElementId,
  resolveTierModelState,
} from "../../admin/static/js/settings_llm_state.js";

describe("settings_llm_state", () => {
  test("resolves provider and model element ids for tier selectors", () => {
    expect(getTierProviderElementId("tier1")).toBe("set-llm-tier1-provider");
    expect(getTierProviderElementId("tier2", "fallback")).toBe("set-llm-tier2-fallback");
    expect(getTierModelElementIds("tier1", "fallback")).toEqual({
      selectId: "set-llm-tier1-fallback-model",
      sourceId: "llm-tier1-fallback-model-source",
      customId: "set-llm-tier1-fallback-model-custom",
    });
  });

  test("maps provider and tier to the correct settings key", () => {
    expect(getTierModelSettingKey("CODEX", "tier1")).toBe("CODEX_MODEL_TIER1");
    expect(getTierModelSettingKey("OLLAMA", "tier2")).toBe("OLLAMA_MODEL_TIER2");
    expect(getTierModelSettingKey("CLAUDE_CODE", "tier2")).toBe("CLAUDE_CODE_MODEL_TIER2");
    expect(getTierModelSettingKey("", "tier1", "fallback")).toBe("LLM_FALLBACK_MODEL_TIER1");
  });

  test("builds tier selector state from runtime settings", () => {
    const state = resolveTierModelState({
      runtimeSettings: {
        CODEX_MODEL_TIER1: "gpt-5.4",
        LLM_FALLBACK_MODEL_TIER1: "qwen2.5:14b",
      },
      tier: "tier1",
      mode: "primary",
      provider: "CODEX",
    });

    expect(state).toMatchObject({
      key: "CODEX_MODEL_TIER1",
      provider: "CODEX",
      currentValue: "gpt-5.4",
      hasProvider: true,
      isFallback: false,
      selectId: "set-llm-tier1-model",
    });
  });

  test("marks fallback selector as unavailable when provider is missing", () => {
    const state = resolveTierModelState({
      runtimeSettings: {},
      tier: "tier2",
      mode: "fallback",
      provider: "",
    });

    expect(state.hasProvider).toBe(false);
    expect(state.currentValue).toBe("DEFAULT");
    expect(state.selectId).toBe("set-llm-tier2-fallback-model");
  });

  test("builds manual selector state with automatic fallback", () => {
    expect(getManualModelSelectorState({}, "")).toMatchObject({
      provider: "AUTOMATIC",
      currentValue: "DEFAULT",
      automatic: true,
    });

    expect(
      getManualModelSelectorState({ MANUAL_LLM_MODEL: "gpt-5.4" }, "CODEX"),
    ).toMatchObject({
      provider: "CODEX",
      currentValue: "gpt-5.4",
      automatic: false,
    });
  });
});
