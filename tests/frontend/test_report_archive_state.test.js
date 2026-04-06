import { describe, expect, test } from "vitest";

import { buildReportArchiveCardState } from "../../admin/static/js/report_archive_state.js";

describe("report_archive_state", () => {
  test("builds archive card summary with comparison delta", () => {
    const state = buildReportArchiveCardState({
      report_date: "2026-04-02",
      total_pnl: 17000,
      buy_count: 2,
      sell_count: 2,
      open_position_count: 1,
      trade_comparison: {
        news_enriched: { trade_count: 2, expectancy: 1800, profit_factor: 1.4, total_pnl: 22000 },
        plain: { trade_count: 2, expectancy: 300, profit_factor: 1.1, total_pnl: 4000 },
        delta: { expectancy: 1500, profit_factor: 0.3, net_pnl_after_cost: 16000 },
      },
    });

    expect(state.dateLabel).toBe("2026-04-02");
    expect(state.summaryLabel).toContain("실현손익 +17,000원");
    expect(state.comparison.ready).toBe(true);
    expect(state.comparison.headline).toContain("뉴스 2건 vs 일반 2건");
    expect(state.comparison.deltaLabel).toContain("E +1,500원");
    expect(state.comparison.deltaLabel).toContain("비용차감 +16,000원");
  });

  test("returns collecting label when comparison sample is not ready", () => {
    const state = buildReportArchiveCardState({
      report_date: "2026-04-01",
      trade_comparison: {
        news_enriched: { trade_count: 1 },
        plain: { trade_count: 0 },
        delta: { expectancy: 0, net_pnl_after_cost: 0 },
      },
    });

    expect(state.comparison.ready).toBe(false);
    expect(state.comparison.deltaLabel).toBe("비교 표본 수집 중");
  });
});
