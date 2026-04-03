import { describe, expect, test } from "vitest";

import {
  buildCatalogErrorCopy,
  buildCatalogMetaText,
} from "../../admin/static/js/llm_catalog_state.js";

describe("llm_catalog_state", () => {
  test("includes stale and fetch error details in catalog meta text", () => {
    const text = buildCatalogMetaText({
      fetched_at: "2026-04-03T09:40:35+09:00",
      stale: true,
      fetch_error: "upstream timeout",
    });

    expect(text).toContain("동기화");
    expect(text).toContain("stale");
    expect(text).toContain("동기화 실패: upstream timeout");
  });

  test("builds user-facing error copy for refresh failures", () => {
    expect(buildCatalogErrorCopy(new Error("network down"))).toBe(
      "공식 모델 목록 새로고침 실패: network down",
    );
  });
});
