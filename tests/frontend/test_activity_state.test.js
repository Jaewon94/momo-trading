import { describe, expect, test } from "vitest";

import {
  buildActivityIdentityLabel,
  buildStockMetaSummary,
  normalizeActivitySymbol,
  resolveActivityStockMeta,
} from "../../admin/static/js/activity_state.js";

describe("activity_state", () => {
  test("extracts stock name from summary with symbol suffix", () => {
    expect(resolveActivityStockMeta({
      symbol: "A010170",
      summary: "⚡ 실시간 감지: PRICE_SURGE - 대한광통신(010170) (10,030원, +6.59%)",
    })).toEqual({
      symbol: "010170",
      stockName: "대한광통신",
      summaryText: "",
    });
  });

  test("falls back to detail payload when summary does not include a name", () => {
    expect(resolveActivityStockMeta({
      symbol: "A010170",
      summary: "📈 [010170] Tier2 승인 기반 시그널: BUY 3000주 @10,100원",
      detail: JSON.stringify({ stock_name: "대한광통신" }),
    })).toEqual({
      symbol: "010170",
      stockName: "대한광통신",
      summaryText: "",
    });
  });

  test("builds brief summary from cached holdings metadata", () => {
    expect(resolveActivityStockMeta({
      symbol: "A394420",
      summary: "📊 [A394420] Tier1 분석 시작",
      knownMeta: {
        "394420": {
          stockName: "리센스메디컬",
          currentPrice: 22700,
          pnlRate: 1.69,
          quantity: 1300,
        },
      },
    })).toEqual({
      symbol: "394420",
      stockName: "리센스메디컬",
      summaryText: "22,700원 · +1.69% · 1300주",
    });
  });

  test("normalizes A-prefixed activity symbols", () => {
    expect(normalizeActivitySymbol("A394420")).toBe("394420");
    expect(normalizeActivitySymbol("394420")).toBe("394420");
  });

  test("builds compact stock meta summary", () => {
    expect(buildStockMetaSummary({
      currentPrice: 10120,
      changeRate: 6.62,
      quantity: 4,
    })).toBe("10,120원 · +6.62% · 4주");
  });

  test("builds identity label with name code and compact meta", () => {
    expect(buildActivityIdentityLabel({
      symbol: "A394420",
      stockName: "리센스메디컬",
      summaryText: "22,700원 · +1.69% · 1300주",
    })).toBe("리센스메디컬 (394420) · 22,700원 · +1.69% · 1300주");
  });
});
