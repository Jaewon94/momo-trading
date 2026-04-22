import { describe, expect, test } from "vitest";

import {
  buildMergedSettings,
  buildSettingsApplyViewModel,
  reconcileSettingsDraft,
  updateSettingsDraft,
} from "../../admin/static/js/settings_apply_state.js";

describe("settings_apply_state", () => {
  test("tracks only real draft changes against runtime settings", () => {
    const baseSettings = {
      LLM_TIER1_CONCURRENCY: 3,
      NEWS_LLM_ENABLED: true,
      NEWS_LLM_PROVIDER: "CLAUDE_CODE",
    };

    const draft1 = updateSettingsDraft({}, { key: "LLM_TIER1_CONCURRENCY", value: "3" }, baseSettings);
    const draft2 = updateSettingsDraft({}, { key: "LLM_TIER1_CONCURRENCY", value: "2" }, baseSettings);
    const draft3 = updateSettingsDraft(draft2, { key: "NEWS_LLM_ENABLED", value: false }, baseSettings);
    const draft4 = updateSettingsDraft(draft3, { key: "NEWS_LLM_PROVIDER", value: "CLAUDE_CODE" }, baseSettings);

    expect(draft1).toEqual({});
    expect(draft2).toEqual({ LLM_TIER1_CONCURRENCY: "2" });
    expect(draft3).toEqual({
      LLM_TIER1_CONCURRENCY: "2",
      NEWS_LLM_ENABLED: false,
    });
    expect(draft4).toEqual({
      LLM_TIER1_CONCURRENCY: "2",
      NEWS_LLM_ENABLED: false,
    });
  });

  test("reconciles draft entries after runtime settings refresh", () => {
    const draft = {
      LLM_PROVIDER_TIER1: "CODEX",
      NEWS_POLL_ENABLED: false,
    };
    const baseSettings = {
      LLM_PROVIDER_TIER1: "CODEX",
      NEWS_POLL_ENABLED: true,
    };

    expect(reconcileSettingsDraft(baseSettings, draft)).toEqual({
      NEWS_POLL_ENABLED: false,
    });
  });

  test("builds merged settings view for form rendering", () => {
    expect(
      buildMergedSettings(
        {
          LLM_PROVIDER_TIER1: "CLAUDE_CODE",
          NEWS_POLL_ENABLED: true,
        },
        {
          LLM_PROVIDER_TIER1: "CODEX",
        },
      ),
    ).toEqual({
      LLM_PROVIDER_TIER1: "CODEX",
      NEWS_POLL_ENABLED: true,
    });
  });

  test("builds apply bar copy for clean, dirty, and applying states", () => {
    const clean = buildSettingsApplyViewModel({ draft: {}, applying: false });
    const dirty = buildSettingsApplyViewModel({
      draft: {
        LLM_PROVIDER_TIER1: "CODEX",
        LLM_TIER1_CONCURRENCY: "2",
      },
      applying: false,
    });
    const applying = buildSettingsApplyViewModel({
      draft: {
        LLM_PROVIDER_TIER1: "CODEX",
      },
      applying: true,
    });

    expect(clean).toMatchObject({
      dirtyCount: 0,
      saveDisabled: true,
      resetDisabled: true,
      saveLabel: "저장",
    });
    expect(clean.summaryText).toContain("저장되지 않은 변경 없음");

    expect(dirty).toMatchObject({
      dirtyCount: 2,
      saveDisabled: false,
      resetDisabled: false,
      saveLabel: "변경 2건 저장",
    });
    expect(dirty.detailText).toContain("현재 작업이 끝난 뒤");

    expect(applying).toMatchObject({
      dirtyCount: 1,
      saveDisabled: true,
      resetDisabled: true,
      closeDisabled: true,
      saveLabel: "저장 중...",
    });
    expect(applying.summaryText).toContain("설정 적용 중");
  });
});
