import { describe, expect, test } from "vitest";

import { resolveActivityStockMeta } from "../../admin/static/js/activity_state.js";

describe("activity_state", () => {
  test("extracts stock name from summary with symbol suffix", () => {
    expect(resolveActivityStockMeta({
      symbol: "010170",
      summary: "⚡ 실시간 감지: PRICE_SURGE - 대한광통신(010170) (10,030원, +6.59%)",
    })).toEqual({
      symbol: "010170",
      stockName: "대한광통신",
    });
  });

  test("falls back to detail payload when summary does not include a name", () => {
    expect(resolveActivityStockMeta({
      symbol: "010170",
      summary: "📈 [010170] Tier2 승인 기반 시그널: BUY 3000주 @10,100원",
      detail: JSON.stringify({ stock_name: "대한광통신" }),
    })).toEqual({
      symbol: "010170",
      stockName: "대한광통신",
    });
  });
});
