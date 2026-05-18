import { describe, expect, test } from "vitest";

import {
  buildLLMExecutionModeState,
  getDefaultLLMDistributedProfile,
  getStandaloneModelSelectorState,
  getDefaultLLMExecutionMode,
  getLLMExecutionModeElementId,
  getLLMExecutionModeSettingKey,
  getTierModelElementIds,
  getTierModelSettingKey,
  getTierProviderElementId,
  normalizeLLMExecutionMode,
  normalizeLLMDistributedProfile,
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

  test("builds standalone selector state for primary and fallback", () => {
    expect(getStandaloneModelSelectorState("manual", {}, "CODEX")).toMatchObject({
      key: "MANUAL_LLM_MODEL",
      provider: "CODEX",
      currentValue: "DEFAULT",
      hasProvider: true,
      selectId: "set-manual-llm-model",
    });

    expect(
      getStandaloneModelSelectorState(
        "news",
        { NEWS_LLM_FALLBACK_MODEL: "qwen2.5:14b" },
        "OLLAMA",
        "fallback",
      ),
    ).toMatchObject({
      key: "NEWS_LLM_FALLBACK_MODEL",
      provider: "OLLAMA",
      currentValue: "qwen2.5:14b",
      hasProvider: true,
      selectId: "set-news-llm-fallback-model",
    });
  });

  test("normalizes execution modes and falls back on invalid values", () => {
    expect(normalizeLLMExecutionMode(" distributed ")).toBe("DISTRIBUTED");
    expect(normalizeLLMExecutionMode("Consensus")).toBe("CONSENSUS");
    expect(normalizeLLMExecutionMode("", "DISTRIBUTED")).toBe("DISTRIBUTED");
    expect(normalizeLLMExecutionMode("parallel", "SINGLE")).toBe("SINGLE");
  });

  test("maps execution mode settings and element ids by scope", () => {
    expect(getLLMExecutionModeSettingKey("tier1")).toBe("LLM_EXECUTION_MODE_TIER1");
    expect(getLLMExecutionModeSettingKey("tier2")).toBe("LLM_EXECUTION_MODE_TIER2");
    expect(getLLMExecutionModeSettingKey("news")).toBe("NEWS_LLM_EXECUTION_MODE");
    expect(getLLMExecutionModeSettingKey("manual")).toBe("MANUAL_LLM_EXECUTION_MODE");
    expect(getLLMExecutionModeSettingKey("unknown")).toBe("MANUAL_LLM_EXECUTION_MODE");

    expect(getLLMExecutionModeElementId("tier1")).toBe("set-llm-tier1-execution-mode");
    expect(getLLMExecutionModeElementId("tier2")).toBe("set-llm-tier2-execution-mode");
    expect(getLLMExecutionModeElementId("news")).toBe("set-news-llm-execution-mode");
    expect(getLLMExecutionModeElementId("manual")).toBe("set-manual-llm-execution-mode");
  });

  test("uses scope-specific execution mode defaults", () => {
    expect(getDefaultLLMExecutionMode("tier1")).toBe("DISTRIBUTED");
    expect(getDefaultLLMExecutionMode("news")).toBe("DISTRIBUTED");
    expect(getDefaultLLMExecutionMode("tier2")).toBe("DISTRIBUTED");
    expect(getDefaultLLMExecutionMode("manual")).toBe("SINGLE");
  });

  test("builds distributed execution state from available worker slots", () => {
    const state = buildLLMExecutionModeState({
      scope: "tier1",
      mode: "distributed",
      cliSlots: 2,
      apiSlots: 3,
      distributedProfile: "FULL",
      claudeCodeAvailable: true,
    });

    expect(state).toMatchObject({
      scope: "tier1",
      mode: "DISTRIBUTED",
      label: "분산 처리",
      totalSlots: 5,
      cliSlots: 2,
      apiSlots: 3,
      usesSingleSelection: false,
      usesWorkerPool: true,
      warningText: "",
    });
    expect(state.workerText).toContain("worker 5개");
    expect(state.helpText).toContain("후보 체인");
    expect(state.primarySelectionText).toContain("후보 체인");
  });

  test("fast distributed profile excludes Claude Code from effective worker count", () => {
    const state = buildLLMExecutionModeState({
      scope: "tier1",
      mode: "DISTRIBUTED",
      cliSlots: 2,
      apiSlots: 1,
      distributedProfile: "FAST",
      claudeCodeAvailable: true,
    });

    expect(state.distributedProfile).toBe("FAST");
    expect(state.totalSlots).toBe(2);
    expect(state.cliSlots).toBe(1);
    expect(state.apiSlots).toBe(1);
    expect(state.profileText).toContain("Claude Code CLI 제외");
  });

  test("normalizes distributed profiles and scope defaults", () => {
    expect(normalizeLLMDistributedProfile(" full ")).toBe("FULL");
    expect(normalizeLLMDistributedProfile("bad", "FAST")).toBe("FAST");
    expect(getDefaultLLMDistributedProfile("tier1")).toBe("FAST");
    expect(getDefaultLLMDistributedProfile("tier2")).toBe("FAST");
  });

  test("warns when pool modes have fewer than two workers", () => {
    const state = buildLLMExecutionModeState({
      scope: "tier2",
      mode: "CONSENSUS",
      cliSlots: 1,
      apiSlots: 0,
    });

    expect(state.warningText).toContain("2개 미만");
    expect(state.usesWorkerPool).toBe(true);
  });

  test("clamps invalid worker counts and unknown scopes", () => {
    const state = buildLLMExecutionModeState({
      scope: "unknown",
      mode: "invalid",
      cliSlots: -2,
      apiSlots: Number.NaN,
    });

    expect(state.scope).toBe("manual");
    expect(state.mode).toBe("SINGLE");
    expect(state.totalSlots).toBe(0);
    expect(state.cliSlots).toBe(0);
    expect(state.apiSlots).toBe(0);
    expect(state.usesSingleSelection).toBe(true);
    expect(state.warningText).toBe("");
  });
});
