import { describe, expect, test } from "vitest";

import {
  buildProviderModelEntries,
  buildProviderModelSourceText,
  getCatalogProvider,
  getProviderModelPlaceholder,
} from "../../admin/static/js/settings_llm_catalog_state.js";

describe("settings_llm_catalog_state", () => {
  test("finds provider catalog by id", () => {
    const catalog = {
      providers: [
        { id: "CLAUDE_CODE", entries: [] },
        { id: "CODEX", entries: [] },
      ],
    };

    expect(getCatalogProvider(catalog, "CODEX")?.id).toBe("CODEX");
    expect(getCatalogProvider(catalog, "OLLAMA")).toBeNull();
  });

  test("builds entries and appends custom current value when missing", () => {
    const entries = buildProviderModelEntries(
      {
        entries: [{ value: "DEFAULT", label: "기본값 사용" }],
      },
      "gpt-5.4",
      "[CLI 기본값]",
    );

    expect(entries[0].suffix).toBe(" [CLI 기본값]");
    expect(entries[1]).toMatchObject({
      value: "gpt-5.4",
      label: "gpt-5.4",
      suffix: "",
    });
  });

  test("builds source text from selected entry and provider metadata", () => {
    const providerCatalog = { cli_version: "1.2.3" };
    const entries = [
      { value: "DEFAULT", source_scope: "manual", stability: "stable" },
      { value: "gpt-5.4", source_scope: "runtime", stability: "snapshot" },
    ];

    expect(buildProviderModelSourceText(providerCatalog, entries, "gpt-5.4")).toBe(
      "출처: runtime · 성격: snapshot · CLI 1.2.3",
    );
  });

  test("returns provider-specific custom placeholders", () => {
    expect(getProviderModelPlaceholder("CODEX")).toContain("gpt-5.4");
    expect(getProviderModelPlaceholder("OLLAMA")).toContain("qwen2.5:14b");
    expect(getProviderModelPlaceholder("CLAUDE_CODE")).toContain("claude-sonnet-4-6");
  });
});
