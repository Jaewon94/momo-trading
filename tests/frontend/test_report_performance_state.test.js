import { describe, expect, test } from "vitest";

import { buildReportPerformanceState } from "../../admin/static/js/report_performance_state.js";

describe("report_performance_state", () => {
  test("builds comparison rows and deltas for report card", () => {
    const state = buildReportPerformanceState({
      trade_comparison: {
        news_enriched: {
          trade_count: 4,
          expectancy: 1800,
          profit_factor: 1.55,
          total_pnl: 42000,
        },
        plain: {
          trade_count: 3,
          expectancy: 700,
          profit_factor: 1.1,
          total_pnl: 9000,
        },
        delta: {
          expectancy: 1100,
          profit_factor: 0.45,
          net_pnl_after_cost: 28000,
        },
      },
    });

    expect(state.hasContent).toBe(true);
    expect(state.ready).toBe(true);
    expect(state.rows[0]).toMatchObject({
      label: "뉴스 반영 거래",
      tradeCount: "4건",
      expectancy: "+1,800원",
    });
    expect(state.rows[1]).toMatchObject({
      label: "일반 거래",
      tradeCount: "3건",
    });
    expect(state.delta.expectancy).toBe("+1,100원");
    expect(state.delta.netPnlAfterCost).toBe("+28,000원");
  });

  test("returns empty-friendly state when no comparison sample exists", () => {
    const state = buildReportPerformanceState({});

    expect(state.hasContent).toBe(false);
    expect(state.ready).toBe(false);
    expect(state.rows[0].tradeCount).toBe("0건");
    expect(state.emptyLabel).toContain("아직 부족");
  });
});
